from .utils.parseArgument import parseArg
from .utils.config import config
from .utils.log import get_logger
from .utils.file import read_txt_file, read_csv_file
from .slicer import Slicer
from .promptgen.generator import PromptGenerator
import os

logger = get_logger("INFO", "main")

def main():
    args = parseArg()
    result_path = os.path.join("result", args.exp_name)
    if not os.path.exists(result_path):
        os.makedirs(result_path)

    config.read_config(args.config_path)
    config.load_data_and_keyword_path(args.data_path, args.keyword_path)
    config.update_path(args.exp_name)

    logger.info("Start running task: {exp}".format(exp=args.exp_name))
    logger.info("Config:\n{config}".format(config=config))

    keyword_df = read_csv_file(config["EXPERIMENT"]["KEYWORDS_PATH"])
    keywords = keyword_df["keyword"].tolist()
    data = read_csv_file(config["EXPERIMENT"]["DATA_PATH"])

    logger.info("Keywords: {keywords}".format(keywords=keywords))

    if args.task == "find_prompts":
        promptGen = PromptGenerator(
            model_name=config["MODEL"]["CREATOR"],
            instruction_source=config["INSTRUCTION"]["SOURCE"],
            refine_flag=config["INSTRUCTION"]["REFINE"],
        )
        promptGen.find_prompts_list(keyword_df)
    elif args.task == "slicing":
        slicer = Slicer(student_model=config["MODEL"]["STUDENT"], 
            teacher_model=config["MODEL"]["TEACHER"],
            batch_size=config["SLICING"]["BATCH_SIZE"])
        if config["SLICING"]["SAMPLING"]:
            data = data.sample(n=config["SLICING"]["SAMPLE_SIZE"], random_state=42)
        slicer.annotate_batch(data, keywords, 
            use_calibrate=config["SLICING"]["CALIBRATE"], 
            add_few_shot=config["EXAMPLES"]["USE_FEW_SHOT"],)
            # use_cache=True)


if __name__ == "__main__":
    main()