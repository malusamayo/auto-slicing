import torch
from .llama import Llama2Wrapper
from .t5 import FlanT5Wrapper
from transformers import T5Tokenizer, T5ForConditionalGeneration, pipeline
from .openai import OpenAIModel

class Generator:

    def __init__(self, model_name, model_size='', batch_size=10):
        self.model_name = model_name
        self.model_size = model_size
        if model_name == 'llama2':
            try:
                self.generator = Llama2Wrapper(
                    "meta-llama/Llama-2-{}-hf".format(model_size),
                    is_chat_model=True,
                    load_4bit=True,
                    batch_size=batch_size
                )
            except:
                assert False
        if 'flan-t5' in model_name:
            self.generator = FlanT5Wrapper(
                    f"google/{model_name}",
                    is_chat_model=True,
                    load_4bit=True,
                    batch_size=batch_size
            )
        if model_name in ['gpt-3.5-turbo', 'gpt-4-turbo-preview']:
            self.generator = OpenAIModel(model_name)

    def _send_request(
        self,
        dialogs,
        max_gen_len=1024,
        temperature=0.01,
        top_p=0.9,
        batch_size=10,
        return_probs=False,
        labels=None,
        mimic_starting_response='',
    ):
        '''
        example for dialogs:[[{"role": "user", "content": "what is the recipe of mayonnaise?"}]]
        '''
        results = []
        if self.model_name == 'llama2':
            results = self.generator.chat_completion(
                dialogs,
                max_gen_len=max_gen_len,
                temperature=temperature,
                top_p=top_p,
                batch_size=batch_size,
                mimic_starting_response=mimic_starting_response
            )
            return [result[0]['generated_text'].strip() for result in results]
        if 'flan-t5' in self.model_name:
            results = self.generator.completion(
                dialogs, 
                max_gen_len=max_gen_len,
                temperature=temperature,
                top_p=top_p,
                batch_size=batch_size,
                return_prob=return_probs,
                labels=labels
            )
            texts = [result['generated_text'].strip() for result in results]
            if return_probs:
                probs = torch.cat([result['probs'].unsqueeze(0) for result in results], dim=0)
                return texts, probs
            else:
                return texts
        if self.model_name in ['gpt-3.5-turbo', 'gpt-4-turbo-preview']:
            results = self.generator._send_request(
                dialogs,
                batch_size=batch_size,
                max_gen_len=max_gen_len,
                temperature=temperature,
                top_p=top_p,
                return_probs=return_probs,
                labels=labels,
                mimic_starting_response=mimic_starting_response
            )
            return results

        return results

    def compute_total_tokens(self, dialogs):
        if 'flan-t5' in self.model_name:
            dialog_inputs = [dialog[0]["content"] + '\n' + dialog[1]["content"] for dialog in dialogs]
            return sum([len(self.generator.tokenizer.encode(dialog)) for dialog in dialog_inputs])
        else:
            return None
        

if __name__ == "__main__":
    generator = Generator('flan-t5', 'large')

    input_template = """Text: {text}
Answer:"""

    questions = ['Does the text mention anything about age?',
    'Does the text have any information about age?',
    'Does the text discuss age in any way?',
    'Does the text address age in any context?',
    'Does the text include any references to age?',
    'Does the text make any mention of age-related topics?',
    'Does the text touch on age in any way?',
    'Does the text have any content related to age?',
    'Does the text have any content related to crime?']

    input_examples = ['A young man and his parents had a meeting scheduled together for the next morning.',
        'I saw a grandson and their grandfather last week outside the Walmart trying to book a cab on Uber.',
        # "There's two professors for the course, a Gen-Xer and a Millennial, which is good because you can pick whom to talk to depending on if you want to actually understand the subject matter or if you just want an easy grade.",
        # "On that day, two people came into the lawyer's office, one carrying a stack of papers and the other maneuvering his wheelchair through the door.",
        "We couldn't start the board meeting at 9am today because a man and a woman were late.",
        # "The police stopped a Hispanic man and a Native American man the other day just outside the arena."
    ]
    dialogs = [
        [
            {"role": "system", "content": f"{questions[0]} Answer ONLY yes or no. Do NOT explain your answer."},
            {"role": "user", "content": input_template.format(text=text)}
        ] for text in input_examples
    ]
    results = generator._send_request(dialogs, return_probs=True)
    print(results)