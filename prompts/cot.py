import dspy
from signatures import ReviewActionabilityFromComment, ReviewActionabilityWithDiff

class CommentOnlyActionabilityClassifier(dspy.Module):
    def __init__(self):
        super().__init__()
        self.cot = dspy.ChainOfThought(
            ReviewActionabilityFromComment,
            instructions=(
                "Reason step by step about whether the review comment is actionable.\n"
                "Mark useful=True if:\n"
                "- The comment identifies a concrete issue (bug, risk, performance, edge case, or maintainability concern), AND\n"
                "- The author could reasonably act on it.\n"
                "Mark useful=False if:\n"
                "- The comment is vague, generic, purely stylistic, praise, or meta discussion."
            )
        )

    def forward(self, review: str):
        return self.cot(review=review)


class DiffAwareActionabilityClassifier(dspy.Module):
    def __init__(self):
        super().__init__()
        self.cot = dspy.ChainOfThought(
            ReviewActionabilityWithDiff,
            instructions=(
                "Reason step by step about the relationship between the code diff and the review comment.\n"
                "Mark useful=True if:\n"
                "- The comment refers to something present or implied in the diff, AND\n"
                "- It identifies a concrete issue (bug, risk, performance, edge case, or maintainability concern), AND\n"
                "- The author could reasonably act on the comment given the diff.\n"
                "Mark useful=False if:\n"
                "- The comment is generic or not grounded in the diff,\n"
                "- It is vague, subjective, or purely stylistic without guidance,\n"
                "- It is praise or meta discussion,\n"
                "- Or it refers to code not shown in the diff."
            )
        )

    def forward(self, review: str, codeDiff: str):
        return self.cot(review=review, codeDiff=codeDiff)
