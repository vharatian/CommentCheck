import sys
import os
import argparse
import dspy
from dspy.teleprompt import LabeledFewShot
from scripts.load_examples_from_json import load_examples_from_json
from validate_answers import normalize_bool
from classifiers import DiffAwareClassifier
from cot import DiffAwareActionabilityClassifier
from sklearn.metrics import classification_report, confusion_matrix

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config  

def main(use_cot):

    lm = dspy.LM(
        model=config.MODEL_NAME,
        api_base=config.API_BASE,
        api_key=config.API_KEY,
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_TOKENS,
        cache=config.CACHE_ENABLED     
    )
    dspy.configure(lm=lm)

    trainset = load_examples_from_json(config.EXAMPLES_SET_PATH)
    testset = load_examples_from_json(config.EVALUATION_SET_PATH)

    program = DiffAwareActionabilityClassifier() if use_cot else DiffAwareClassifier()
    
    optimizer = LabeledFewShot(k=config.RANDOM_K) 
    compiled = optimizer.compile(student=program, trainset=trainset)

    true_labels = []
    pred_labels = []

    for i, test in enumerate(testset):
        prediction = compiled(review=test.review, codeDiff=test.codeDiff)
        
        t_val = normalize_bool(test.useful)
        p_val = normalize_bool(prediction.useful)

        true_labels.append(t_val)
        pred_labels.append(p_val)

        print(f"{i+1}  Real:{t_val}  Pred:{p_val}")
        print(lm.inspect_history(n=1))

    print("\nClassification report:")
    print(classification_report(true_labels, pred_labels, digits=3))

    print("\nConfusion Matrix:")
    print(confusion_matrix(true_labels, pred_labels))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-cot",
        "--cot",
        action="store_true",
        help="Use CoT-based classifier"
    )
    args = parser.parse_args()
    
    main(use_cot=args.cot)