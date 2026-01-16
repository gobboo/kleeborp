from email import charset
import logging
import os

logger = logging.getLogger()

current_dir = os.path.dirname(os.path.abspath(__file__))

PROMPT_DIR = current_dir
UTIL_PROMPT_DIR = os.path.join(PROMPT_DIR, "texts")


def _load_prompt_from_file(file_path: str):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    encodings = ["utf-8", "utf-8-sig", "gbk", "gb2312", "ascii"]

    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as file:
                return file.read()
        except UnicodeDecodeError:
            continue

    # If all common encodings fail, try to detect encoding
    try:
        with open(file_path, "rb") as file:
            raw_data = file.read()
        detected = charset.detect(raw_data)
        detected_encoding = detected["encoding"]

        if detected_encoding:
            try:
                return raw_data.decode(detected_encoding)
            except UnicodeDecodeError:
                pass
    except Exception as e:
        logger.error(f"Error detecting encoding for {file_path}: {e}")

    raise UnicodeError(f"Failed to decode {file_path} with any encoding")


def load_prompt(prompt_name: str) -> str:
    """Load the content of a specific utility prompt file."""
    util_file_path = os.path.join(UTIL_PROMPT_DIR, f"{prompt_name}.txt")
    try:
        return _load_prompt_from_file(util_file_path)
    except Exception as e:
        logger.error(f"Error loading util {prompt_name}: {e}")
        raise
