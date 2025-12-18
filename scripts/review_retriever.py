import numpy as np
import pickle
import json
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDINGS_FILE = "review_embeddings.pkl"

def embed_and_store(json_file_path):
    """Reads a JSON file, embeds the 'commentText' and stores embeddings + metadata on disk."""
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    with open(json_file_path, 'r') as f:
        data = json.load(f)

    valid_data = [item for item in data if "commentText" in item]
    comments = [item["commentText"] for item in valid_data]
    
    if not comments:
        print("No valid commentTexts found to embed.")
        return

    print(f"Embedding {len(comments)} comments.")
    embeddings = model.encode(comments, normalize_embeddings=True)

    stored_data = []
    for item in valid_data:
        stored_data.append({
            "commentText": item.get("commentText"),
            "diffHunk": item.get("diffHunk"),
            "resolved": item.get("resolved") 
        })

    payload = {
        "embeddings": embeddings,
        "data": stored_data
    }

    with open(EMBEDDINGS_FILE, "wb") as f:
        pickle.dump(payload, f)

    print(f"Saved {len(stored_data)} embeddings to {EMBEDDINGS_FILE}")


def retrieve_top_k(new_comment_text, k=3):
    """Embeds a new comment text and retrieves the top-k most similar stored examples."""
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)

    try:
        with open(EMBEDDINGS_FILE, "rb") as f:
            payload = pickle.load(f)
    except FileNotFoundError:
        print(f"Error: {EMBEDDINGS_FILE} not found. Run embed_and_store() first.")
        return []

    stored_embeddings = payload["embeddings"]
    stored_data = payload["data"]

    query_embedding = model.encode(
        [new_comment_text],
        normalize_embeddings=True
    )

    similarities = cosine_similarity(query_embedding, stored_embeddings)[0]
    top_k_indices = np.argsort(similarities)[::-1][:k]

    results = []
    for idx in top_k_indices:
        item = stored_data[idx]
        results.append({
            "commentText": item["commentText"],
            "diffHunk": item["diffHunk"],
            "resolved": item["resolved"],
            "similarity": float(similarities[idx])
        })

    return results
