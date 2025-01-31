from .utils.config import config
from .utils.log import get_logger
from datasets import load_dataset, load_from_disk, concatenate_datasets
import random
import pandas as pd
from .model.llm_server import Generator

logger = get_logger("INFO", "run model")
# generator = Generator("llama2", "13b-chat")

SYSTEM_PROMPT=''''''

BBQ_PROMPT='''
# Context
{context}

# Question
{question} 

Select the correct answer from the following options:
1. {ans0}
2. {ans1}
3. {ans2}

Reply only the answer phrase. Do not write anything else except the answer.
# Answer
'''

MMLU_PROMPT='''
# Question
{question} 

Select the correct answer from the following options:
1. {ans0}
2. {ans1}
3. {ans2}
4. {ans3}

Reply only the answer phrase. Do not write anything else except the answer.
# Answer
'''

# 1-shot example
EXAMPLE_QUESTION='''What is the name of the first person to walk on the moon?'''
EXAMPLE_ANSWER='''Neil Armstrong'''
EXAMPLE_TITLE=['''Apollo 11''']
EXAMPLE_PASSAGE=['''Apollo 11 (July 16–24, 1969) was the American spaceflight that first landed humans on the Moon. \
Commander Neil Armstrong and lunar module pilot Buzz Aldrin landed the Apollo Lunar Module Eagle on July 20, 1969, at 20:17 UTC, \
and Armstrong became the first person to step onto the Moon's surface six hours and 39 minutes later, on July 21 at 02:56 UTC. \
Aldrin joined him 19 minutes later, and they spent about two and a quarter hours together exploring the site they had named \
Tranquility Base upon landing. Armstrong and Aldrin collected 47.5 pounds (21.5 kg) of lunar material to bring back to Earth \
as pilot Michael Collins flew the Command Module Columbia in lunar orbit, and were on the Moon's surface for 21 hours, \
36 minutes before lifting off to rejoin Columbia.''']

def row_to_dialog(row):
    return [
        {
            "role": "system", 
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user", 
            # "content": BBQ_PROMPT.format(context=row["context"], question=row["question"], ans0=row["ans0"], ans1=row["ans1"], ans2=row["ans2"])
            "content": MMLU_PROMPT.format(question=row["question"], ans0=row['choices'][0], 
                ans1=row['choices'][1], ans2=row['choices'][2], ans3=row['choices'][3])
        }
    ]

#     return [
#         {
#             "role": "system", 
#             "content": SYSTEM_PROMPT
#         },
#         {
#             "role": "user", 
#             "content": '\n\n'.join(
#                 [
#                     "# Title\n{title}\n# Passage\n{passage}".format(
#                         title=title,
#                         passage=' '.join(sentences)
#                     ) 
#                     for title, sentences in zip(row["context"]["title"], row["context"]["sentences"])
#                 ]
#                 + [
#                     '''# Question
# {question} Answer in the following format:

# Your answer shoud be a short phrase strictly less than 10 words. You must not type anything except the answer phrase.

# # Answer
# '''.format(question=row["question"])
#                 ]
#             )
#         }
#     ]

def load_and_filter_dataset(task, cols, split):
    # load dataset
    if cols == []:
        dataset = load_dataset(task)[split]
        dataset = dataset.shuffle(seed=42).select(range(config["RUN"]["SAMPLE_SIZE"]))
    else:
        datasets = []
        for col in cols:
            d = load_dataset(task, col)[split]
            # d = d.filter(lambda example: example['label'] != 0)
            sample_size = int(config["RUN"]["SAMPLE_SIZE"] / len(cols))
            d = d.shuffle(seed=42).select(range(sample_size))
            datasets.append(d)
        dataset = concatenate_datasets(datasets)


    logger.info("loaded dataset")
    logger.info(dataset.column_names)
    logger.info(len(dataset))

    # # filter dataset
    # dataset = dataset.filter(
    #     lambda example: len(
    #         ' '.join(
    #             [
    #                 ' '.join(sentences) 
    #                 for sentences in example["context"]["sentences"]
    #             ]
    #             + [
    #                 title
    #                 for title in example["context"]["title"]
    #             ]
    #             + [example["question"]]
    #             + [SYSTEM_PROMPT]
    #         ).split()
    #     ) < 450, 
    #     with_indices=False
    # )

    logger.info(len(dataset))

    return dataset

def run_model():

    # dataset = load_and_filter_dataset("heegyu/bbq", ["Age", "Gender_identity", "Disability_status", "Nationality", "Religion"], 'test')
    # dataset = load_and_filter_dataset("tweet_eval", ['stance_abortion', 'stance_atheism', 'stance_climate', 'stance_feminist', 'stance_hillary'], 'train')

    # dataset = load_and_filter_dataset("cais/mmlu", ["high_school_biology", "high_school_chemistry", "high_school_psychology", "high_school_macroeconomics", "high_school_statistics"], 'test')
    # dataset = dataset.add_column("context", [row["question"] + ' ' + row["choices"][row["answer"]] for row in dataset])
    
    # dataset = load_and_filter_dataset("SetFit/rte", [], 'validation')
    # dataset = dataset.add_column("context", ["Sentence 1: " + row["text1"] + '\nSentence 2: ' + row["text2"] for row in dataset])

    dataset = load_and_filter_dataset("tweet_eval", ['emotion'], 'test')


    # # # generate dialogs
    # dialogs = [ row_to_dialog(row) for row in dataset ]
    
    # logger.info("generated dialogs")

    # # generate results
    # results = generator._send_request(dialogs=dialogs, max_gen_len=1700, temperature=0.02, batch_size=10)
    # logger.info("generated results")
    
    # # save results to datasets
    # dataset = dataset.add_column("generated_answer", results)
    # logger.info("added column")

    # save to csv
    dataset.to_csv(config["RUN"]["CSV_PATH"])
    # transform_data(config)



def transform_data(config):
    # save to csv
    dataset = load_from_disk(config["RUN"]["OUTPUT_PATH"])
    df = pd.DataFrame()
    df['full_text'] = [
        '\n\n'.join(
                    [
                        "# Title\n{title}\n# Passage\n{passage}".format(
                            title=title,
                            passage=' '.join(sentences)
                        ) 
                        for title, sentences in zip(row["context"]["title"], row["context"]["sentences"])
                    ]
                    + [
                        '# Question\n{question}'.format(question=row["question"])
                    ]
                )
        for row in dataset
    ]

    # text is the part that we use to slice data
    df['text'] = [
        row["question"]
        for row in dataset
    ]
    df['answer'] = [
        row['answer']
        for row in dataset
    ]
    df['generated_answer'] = [
        row['generated_answer']
        for row in dataset
    ]
    df['level'] = [
        row['level']
        for row in dataset
    ]
    df['supporting_facts'] = [
        str(row['supporting_facts'])
        for row in dataset
    ]
    df['id'] = [
        row['id']
        for row in dataset
    ]
    df.to_csv(config["RUN"]["CSV_PATH"], index=False)