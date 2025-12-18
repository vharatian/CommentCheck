import json
import dspy


def load_examples_from_json(json_path):
    examples = []

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        resolved = item.get("resolved")

        if isinstance(resolved, str):
            resolved = resolved.lower() == "true"

        ex = dspy.Example(
            codeDiff=item.get("diffHunk", ""),
            review=item.get("commentText", ""),
            useful=resolved,
        ).with_inputs("codeDiff", "review")

        examples.append(ex)

    return examples
