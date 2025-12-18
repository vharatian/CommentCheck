import dspy
from signatures import ReviewActionabilityFromComment, ReviewActionabilityWithDiff

class CommentOnlyClassifier(dspy.Module):
    def __init__(self):
        super().__init__()
        self.prog = dspy.Predict(ReviewActionabilityFromComment)

    def forward(self, review):
        return self.prog(review=review)
    
class DiffAwareClassifier(dspy.Module):
    def __init__(self):
        super().__init__()
        self.prog = dspy.Predict(ReviewActionabilityWithDiff)

    def forward(self, review, codeDiff):
        return self.prog(review=review, codeDiff=codeDiff)
