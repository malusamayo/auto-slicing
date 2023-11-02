import os
import os.path as osp
import torch
import torch.cuda
import torch.backends.cudnn
import torch.nn.functional as F
import argparse
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    pipeline,
)
from typing import List, Dict
import time
import concurrent.futures
from utils.log import get_logger
from transformers import T5Tokenizer, T5ForConditionalGeneration, pipeline


logger = get_logger("INFO", "t5")

def _divide_list_into_sublists(input_list, num_sublists, batch_size):
    avg_len = int(len(input_list) / num_sublists) + 1
    if avg_len >= batch_size:
        sublists = [input_list[min(i * avg_len, len(input_list)): min((i + 1) * avg_len, len(input_list))] for i in range(num_sublists)]
    else:
        sublists = []
        i = 0
        while i < len(input_list):
            sublists.append(input_list[i:min(i + batch_size, len(input_list))])
            i += batch_size
        if len(sublists) < num_sublists:
            sublists += [[] for _ in range(num_sublists - len(sublists))]
    return sublists


class FlanT5Wrapper:
    def __init__(
        self,
        model_name,
        is_chat_model,
        debug_mode=False,
        load_4bit=False,
        batch_size=40,
    ):
        self.model_name = model_name
        self.no_cuda = (os.environ["CUDA_VISIBLE_DEVICES"] == "")
        self.use_cuda = not self.no_cuda
        START_TIME = time.perf_counter()
        logger.info("Start loading {}...".format(model_name))
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir="./hf-models-cache/"
        )
        self.tokenizer = T5Tokenizer.from_pretrained(model_name)
        # device_map = {
        #     'model.shared': "nan",
        #     'model.encoder': "nan", 
        #     'model.decoder': "nan",
        #     'model.lm_head': "nan",
        # }
        # for i in range(40):
        #     device_map[f'model.layers.{i}'] = "nan"
        self.device_count = torch.cuda.device_count()
        logger.info(f"Using {self.device_count} GPUs")
        self.model = []
        for item in range(self.device_count):
            # for layer in device_map:
            #     device_map[layer] = item
            self.model.append(
                T5ForConditionalGeneration.from_pretrained(
                    model_name, 
                    cache_dir="./hf-models-cache/", 
                    device_map=item, 
                    load_in_8bit=True
                )
            )
            self.model[-1].eval()
        logger.info("Done with {:.2f} seconds.".format(time.perf_counter() - START_TIME))
        self.debug_mode = debug_mode
        
        self.pipeline = [
            pipeline(
                "text2text-generation",
                model=model,
                tokenizer=self.tokenizer,
                batch_size=batch_size,
            ) for device, model in enumerate(self.model)
        ]

    @torch.no_grad()
    def complete_with_probs(self, input_text, batch_size, i, labels):
        input_ids = self.tokenizer(input_text, return_tensors="pt", padding=True)
        label_ids = self.tokenizer(labels, return_tensors="pt")["input_ids"].t()[0]

        print(self.tokenizer.pad_token_id)
        decoder_input_ids = torch.tensor([[self.tokenizer.pad_token_id]] * len(input_text)) 
        logits = self.model[i](**input_ids, decoder_input_ids=decoder_input_ids)[0]
        selected_logits = logits[:, :, label_ids].to(torch.float32)
        probs = F.softmax(selected_logits, dim=2).squeeze()
        tokens = torch.argmax(logits, dim=2)
        outputs = self.tokenizer.batch_decode(tokens)
        return outputs, probs

    @torch.no_grad()
    def completion(
        self, dialogs, max_gen_len,
        temperature, top_p,
        return_prob=False,
        calc_str=None,
        batch_size=40,
        labels=None,
    ) -> List[
        List[Dict[str, str]]
    ]:  
        divided_dialogs = _divide_list_into_sublists(dialogs, self.device_count, batch_size)
        dialog_input = []
        for dialogs in divided_dialogs:
            prompt_tokens = []
            for dialog in dialogs:
                dialog_tokens = dialog[1]["content"]
                prompt_tokens.append(dialog_tokens)
                logger.debug(dialog_tokens)
            dialog_input.append(prompt_tokens)
        if return_prob and labels is not None:
            generated_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.device_count) as executor:
                futures = []
                for i in range(self.device_count):
                    if len(dialog_input[i]) > 0:
                        futures.append(
                            executor.submit(
                                self.complete_with_probs, 
                                dialog_input[i],
                                batch_size=batch_size,
                                i=i,
                                labels=labels,
                            )
                        )
                for future in futures:
                    generated_results += future.result()
            return generated_results
        else:
            generated_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.device_count) as executor:
                futures = []
                for i in range(self.device_count):
                    if len(dialog_input[i]) > 0:
                        futures.append(
                            executor.submit(
                                self.pipeline[i], 
                                dialog_input[i],
                                batch_size=batch_size,
                            )
                        )
                for future in futures:
                    generated_results += future.result()
            for pipeline in self.pipeline:
                pipeline.call_count=0
            return generated_results