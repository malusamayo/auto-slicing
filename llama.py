import logging
import os
import os.path as osp
import torch
import torch.cuda
import torch.backends.cudnn
import argparse
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    pipeline,
)
from typing import List, Dict
import time
import concurrent.futures

logger = logging.getLogger(__name__)

def _divide_list_into_sublists(input_list, num_sublists):
    avg_len = int(len(input_list) / num_sublists) + 1

    sublists = [input_list[min(i * avg_len, len(input_list)): min((i + 1) * avg_len, len(input_list))] for i in range(num_sublists)]
    
    return sublists

B_INST, E_INST = "[INST]", "[/INST]"
B_SYS, E_SYS = "<<SYS>>\n", "\n<</SYS>>\n\n"
DEFAULT_SYSTEM_PROMPT = """\
You are a helpful, respectful and honest assistant. Always answer as helpfully as possible, while being safe. Your answers should not include any harmful, unethical, racist, sexist, toxic, dangerous, or illegal content. Please ensure that your responses are socially unbiased and positive in nature.

If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. If you don't know the answer to a question, please don't share false information."""


class Llama2Wrapper:
    def __init__(
        self,
        model_name,
        is_chat_model,
        debug_mode=False,
        load_4bit=False,
    ):
        self.model_name = model_name
        self.no_cuda = (os.environ["CUDA_VISIBLE_DEVICES"] == "")
        self.use_cuda = not self.no_cuda
        START_TIME = time.perf_counter()
        logger.info("Start loading {}...".format(model_name))
        if self.use_cuda:
            from transformers import BitsAndBytesConfig
            quantization_config = BitsAndBytesConfig(
                load_in_4bit=load_4bit,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
            )
        else:
            quantization_config = None
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            cache_dir="./hf-models-cache/",
            use_auth_token="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",
        )
        device_map = {
            'model.embed_tokens': "nan", 
            'model.layers.0': "nan", 
            'model.layers.1': "nan", 
            'model.layers.2': "nan", 
            'model.layers.3': "nan", 
            'model.layers.4': "nan", 
            'model.layers.5': "nan", 
            'model.layers.6': "nan", 
            'model.layers.7': "nan", 
            'model.layers.8': "nan", 
            'model.layers.9': "nan", 
            'model.layers.10': "nan", 
            'model.layers.11': "nan", 
            'model.layers.12': "nan", 
            'model.layers.13': "nan", 
            'model.layers.14': "nan", 
            'model.layers.15': "nan", 
            'model.layers.16': "nan", 
            'model.layers.17': "nan", 
            'model.layers.18': "nan", 
            'model.layers.19': "nan", 
            'model.layers.20': "nan", 
            'model.layers.21': "nan", 
            'model.layers.22': "nan", 
            'model.layers.23': "nan", 
            'model.layers.24': "nan", 
            'model.layers.25': "nan", 
            'model.layers.26': "nan", 
            'model.layers.27': "nan", 
            'model.layers.28': "nan", 
            'model.layers.29': "nan", 
            'model.layers.30': "nan", 
            'model.layers.31': "nan", 
            'model.norm': "nan", 
            'lm_head': 'nan'
        }
        self.device_count = torch.cuda.device_count()
        self.model = []
        for item in range(self.device_count):
            for layer in device_map:
                device_map[layer] = item
            self.model.append(
                AutoModelForCausalLM.from_pretrained(
                    model_name,
                    cache_dir="./hf-models-cache/",
                    device_map=device_map,
                    quantization_config=quantization_config,
                    use_auth_token="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"
                )
            )
            self.model[-1].eval()
        logger.info("Done with {:.2f} seconds.".format(time.perf_counter() - START_TIME))
        self.debug_mode = debug_mode
        self.is_chat_model = is_chat_model
        self.pipeline = [
            pipeline(
                "text-generation",
                model=model,
                tokenizer=self.tokenizer,
                device=device
            ) for device, model in enumerate(self.model)
        ]

    @torch.no_grad()
    def chat_completion(
        self, dialogs, max_gen_len,
        temperature, top_p,
        return_prob=False,
        calc_str=None
    ) -> List[
        List[Dict[str, str]]
    ]:  # [batch_size, sampled_num], {"generated_text": "xxx"}
        assert self.is_chat_model
        prompt_tokens = []
        for dialog in dialogs:
            if dialog[0]["role"] != "system":
                dialog = [
                    {
                        "role": "system",
                        "content": DEFAULT_SYSTEM_PROMPT,
                    }
                ] + dialog
            dialog = [
                {
                    "role": dialog[1]["role"],
                    "content": B_SYS
                    + dialog[0]["content"]
                    + E_SYS
                    + dialog[1]["content"],
                }
            ] + dialog[2:]
            dialog_tokens: str = "".join(
                [
                    f"{B_INST} {(prompt['content']).strip()} {E_INST} {(answer['content']).strip()} "
                    for prompt, answer in zip(
                        dialog[::2],
                        dialog[1::2],
                    )
                ]
            )
            dialog_tokens += f"{B_INST} {(dialog[-1]['content']).strip()} {E_INST}"
            assert all([msg["role"] == "user" for msg in dialog[::2]]) and all(
                [msg["role"] == "assistant" for msg in dialog[1::2]]
            ), (
                "model only supports 'system', 'user' and 'assistant' roles, "
                "starting with 'system', then 'user' and alternating (u/a/u/a/u...)"
            )
            assert (
                dialog[-1]["role"] == "user"
            ), f"Last message must be from user, got {dialog[-1]['role']}"
            prompt_tokens.append(dialog_tokens)
            logger.debug(dialog_tokens)
        if return_prob:
            raise("Not implemented yet")
            assert calc_str is not None
            input_ids = self.tokenizer.encode(
                prompt_tokens[0] + " " + calc_str,
                return_tensors="pt")
            str_encoded = self.tokenizer.encode(
                calc_str, return_tensors="pt")[0]
            if self.use_cuda:
                input_ids = input_ids.cuda(0)
                str_encoded = str_encoded.cuda(0)
            res = self.model(input_ids).logits[0][-1-len(str_encoded):-1]
            res = torch.gather(torch.softmax(res, dim=-1), 1, str_encoded.unsqueeze(1))
            res = torch.sum(torch.log(res)) / len(str_encoded)
            return res.cpu().item()
        else:
            prompt_token_list = _divide_list_into_sublists(prompt_tokens, self.device_count)
            generated_results = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.device_count) as executor:
                futures = []
                for i in range(self.device_count):
                    if len(prompt_token_list[i]) > 0:
                        futures.append(
                            executor.submit(
                                self.pipeline[i], 
                                prompt_token_list[i], 
                                temperature=temperature, 
                                top_p=top_p, 
                                max_length=max_gen_len, 
                                return_full_text=False
                            )
                        )
                for future in concurrent.futures.as_completed(futures):
                    generated_results += future.result()
            return generated_results


def test_llama_2(args):
    max_gen_len = args.max_gen_len
    temperature = 0.0
    top_p = 0.9
    load_in_4bits = args.load_in_4bits
    dialogs = [
        [{"role": "user", "content": "what is the recipe of mayonnaise?"}],
        [
            {"role": "user", "content": "I am going to Paris, what should I see?"},
            {
                "role": "assistant",
                "content": """\
Paris, the capital of France, is known for its stunning architecture, art museums, historical landmarks, and romantic atmosphere. Here are some of the top attractions to see in Paris:

1. The Eiffel Tower: The iconic Eiffel Tower is one of the most recognizable landmarks in the world and offers breathtaking views of the city.
2. The Louvre Museum: The Louvre is one of the world's largest and most famous museums, housing an impressive collection of art and artifacts, including the Mona Lisa.
3. Notre-Dame Cathedral: This beautiful cathedral is one of the most famous landmarks in Paris and is known for its Gothic architecture and stunning stained glass windows.

These are just a few of the many attractions that Paris has to offer. With so much to see and do, it's no wonder that Paris is one of the most popular tourist destinations in the world.""",
            },
            {"role": "user", "content": "What is so great about #1?"},
        ],
        [
            {"role": "system", "content": "Always answer with Haiku"},
            {"role": "user", "content": "I am going to Paris, what should I see?"},
        ],
        [
            {
                "role": "system",
                "content": "Always answer with emojis",
            },
            {"role": "user", "content": "How to go from Beijing to NY?"},
        ],
        [
            {
                "role": "system",
                "content": "You are a helpful programming assistant.",
            },
            {
                "role": "user",
                "content": "How to use multiprocessing to accelerate my code in Python? Show me an example code.",
            },
        ],
    ]
    try:
        generator = Llama2Wrapper(
            "/home/yiningho/workspace/datadisk/llama/llama-2-{}".format(args.model_size),
            is_chat_model=True,
            load_4bit=load_in_4bits,
        )
    except:
        logger.info(
            "Loading from /home/yiningho/workspace/datadisk/llama/llama-2-{} failed. Using huggingface hub.".format(
                args.model_size
            )
        )
        generator = Llama2Wrapper(
            "meta-llama/Llama-2-{}-hf".format(args.model_size),
            is_chat_model=True,
            load_4bit=load_in_4bits,
        )
    if args.check_index is not None:
        dialogs = [dialogs[args.check_index]]
    results = generator.chat_completion(
        dialogs,  # type: ignore
        max_gen_len=max_gen_len,
        temperature=temperature,
        top_p=top_p,
    )
    for result in results:
        logger.info(result)
    # for dialog in dialogs:
    #     result = generator.chat_completion(
    #         [dialog],  # type: ignore
    #         max_gen_len=max_gen_len,
    #         temperature=temperature,
    #         top_p=top_p,
    #     )[0]
    #     for msg in dialog:
    #         logger.info(f"{msg['role'].capitalize()}: {msg['content']}\n")
    #     logger.info(f"> Assistant: {result[0]['generated_text']}")
    #     logger.info("\n==================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--load_in_4bits", default=False)
    parser.add_argument(
        "--model_size",
        choices=["7b", "7b-chat", "13b", "13b-chat", "70b", "70b-chat"],
        default="7b-chat",
    )
    parser.add_argument("--max_gen_len", type=int, default=512)
    parser.add_argument("--check_index", type=int)
    args = parser.parse_args()
    if not args.load_in_4bits:
        torch.set_default_tensor_type(torch.cuda.HalfTensor)
    test_llama_2(args)
