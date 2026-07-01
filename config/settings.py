import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PINECONE_API_KEY  = os.getenv("PINECONE_API_KEY", "")
PINECONE_INDEX    = os.getenv("PINECONE_INDEX", "esg-compliance")

MODEL             = "claude-sonnet-4-6"
MAX_TOKENS        = 1500
CHUNK_SIZE        = 800
CHUNK_OVERLAP     = 100
TOP_K             = 5
