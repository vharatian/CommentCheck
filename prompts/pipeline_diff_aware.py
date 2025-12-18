import sys
import os
from dotenv import load_dotenv
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import dspy
from scripts.load_examples_from_json import load_examples_from_json
from validate_answers import normalize_bool
from classifiers import DiffAwareClassifier
from sklearn.metrics import classification_report, confusion_matrix

if __name__ == "__main__":

    load_dotenv()

    lm = dspy.LM(
        model=os.getenv("MODEL"),
        api_base=os.getenv("API_BASE"),
        # api_key=os.getenv("API_KEY"),
        temperature=0.0,
        max_tokens=120,
        cache=True     
    )
    dspy.configure(lm=lm)

    data_path = os.path.join(os.path.dirname(__file__), "../data/ground_truth.json")
    dataset = load_examples_from_json(data_path)
    testset = dataset[10:]
 
    program = DiffAwareClassifier()
    compiled = program 

    predictions = []
    true_labels = []
    pred_labels = []

    for i, test in enumerate(testset):
        prediction = compiled(review=test.review, codeDiff=test.codeDiff)
        predictions.append(prediction)    

        t_val = normalize_bool(test.useful)
        p_val = normalize_bool(prediction.useful)

        true_labels.append(t_val)
        pred_labels.append(p_val)

        print(f"{i+1}  Real:{t_val}  Pred:{p_val}")


    print("\nClassification report:")
    print(classification_report(true_labels, pred_labels, digits=3))

    print("\nConfusion Matrix:")
    print(confusion_matrix(true_labels, pred_labels))

    print("\nDetailed Predictions:")
    for prediction in predictions:
        print(prediction)
