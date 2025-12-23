import os
from dotenv import load_dotenv


load_dotenv()

# --- Model Configuration ---
MODEL_NAME = os.getenv("MODEL")
API_BASE = os.getenv("API_BASE")
API_KEY = os.getenv("API_KEY")
MAX_TOKENS = 500
TEMPERATURE = 0.0
CACHE_ENABLED = True

# --- Paths ---
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
INITIAL_SET_PATH    = os.path.join(PROJECT_ROOT, "data", "sets", "initial_set.json")
EXAMPLES_SET_PATH   = os.path.join(PROJECT_ROOT, "data", "sets", "examples_set.json")
EVALUATION_SET_PATH = os.path.join(PROJECT_ROOT, "data", "sets", "evaluation_set.json")

# --- Embedding Model ---
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# --- Hyperparameters ---
KNN_K = 4       # Number of examples for KNNFewShot
RANDOM_K = 4    # Number of examples for LabeledFewShot