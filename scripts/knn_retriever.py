import dspy
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from scripts.load_examples_from_json import load_examples_from_json

class KNN:
    def __init__(self, k, trainset, vectorizer):
        self.k = k
        self.trainset = trainset
        self.vectorizer = vectorizer
        
        self.train_vectors = []
        for example in self.trainset:
            text_to_embed = f"{example.diffHunk} {example.commentText}"
            self.train_vectors.append(self.vectorizer(text_to_embed))
        
        self.train_vectors = np.array(self.train_vectors)

    def __call__(self, **kwargs):
        input_diff = kwargs.get('diffHunk', '')
        input_comment = kwargs.get('commentText', '')

        query_text = f"{input_diff} {input_comment}"    
        query_vector = np.array([self.vectorizer(query_text)])

        scores = cosine_similarity(query_vector, self.train_vectors)[0]
        top_k_indices = scores.argsort()[-self.k:][::-1]

        return [self.trainset[i] for i in top_k_indices]
