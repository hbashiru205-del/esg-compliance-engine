import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

MODEL             = "gemini-3.1-flash-lite"
MAX_TOKENS        = 2000
CHUNK_SIZE        = 800
CHUNK_OVERLAP     = 100
TOP_K             = 8
