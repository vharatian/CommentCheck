import sys, os
from dotenv import load_dotenv
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import dspy
from dspy.teleprompt import KNNFewShot
from sentence_transformers import SentenceTransformer
from scripts.load_examples_from_json import load_examples_from_json
from validate_answers import normalize_bool
from cot import DiffAwareActionabilityClassifier  
from sklearn.metrics import classification_report, confusion_matrix


if __name__ == "__main__":
    
    load_dotenv()

    lm = dspy.LM(
        model=os.getenv("MODEL"),
        api_base=os.getenv("API_BASE"),
        # api_key=os.getenv("API_KEY"),
        temperature=0.0,
        max_tokens=200,
        cache=True
    )
    dspy.configure(lm=lm)

    sentence_model = SentenceTransformer("all-MiniLM-L6-v2")

    data_path = os.path.join(os.path.dirname(__file__), "../data/ground_truth.json")
    dataset = load_examples_from_json(data_path)

    trainset = dataset[:10]
    testset = dataset[10:20]

    program = DiffAwareActionabilityClassifier() 

    knn_optimizer = KNNFewShot(
        k=4,  
        trainset=trainset,
        vectorizer=dspy.Embedder(sentence_model.encode)
    )

    compiled_program = knn_optimizer.compile(program)

    predictions = []
    true_labels = []
    pred_labels = []

    for i, test in enumerate(testset):
        pred = compiled_program(review=test.review, codeDiff=test.codeDiff)
        predictions.append(pred)

        t_val = normalize_bool(test.useful)
        p_val = normalize_bool(pred.useful)

        true_labels.append(t_val)
        pred_labels.append(p_val)

        print(f"{i+1} Real: {t_val} Pred: {p_val}")


    print("\nClassification report:")
    print(classification_report(true_labels, pred_labels, digits=3))

    print("\nConfusion Matrix:")
    print(confusion_matrix(true_labels, pred_labels))

    if hasattr(lm, "inspect_history"):
        print("\nLast LM call history:")
        print(lm.inspect_history(n=1))
