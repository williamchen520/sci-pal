"""
Sci-Pal Configuration Settings
"""
import os
from pathlib import Path

# Project root directory
BASE_DIR = Path(__file__).parent.parent

# Database config
DATABASE_PATH = os.path.join(BASE_DIR, "data", "research.db")

# AI config
AI_MODEL = os.getenv("AI_MODEL", "qwen-plus")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")

# Server config
HOST = "0.0.0.0"
PORT = 5000
DEBUG = False

# Upload config
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB

# Parser config
PARSER_CONFIG = {
    "primary": "mineru",  # mineru / docling
    "use_grobid": True,
    "use_pdfplumber": True,
}

# Retrieval config
RETRIEVAL_CONFIG = {
    "top_k": 10,
    "recursive_depth": 2,
    "cache_ttl": 3600,  # 1 hour
}

# Logging config
LOG_LEVEL = "INFO"
LOG_DIR = os.path.join(BASE_DIR, "logs")
