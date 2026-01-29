import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

MEMORY_FILE = DATA_DIR / "memory.json"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL_MAIN = os.getenv("OPENAI_MODEL_MAIN")
OPENAI_BASE_URL = os.getenv("BASE_URL")

# 隐私 / 合规模块简单开关
ENABLE_PERSIST_RAW_PDF_TEXT = False  # True 则在 memory 中保存原始文本（不推荐）
