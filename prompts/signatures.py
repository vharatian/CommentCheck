import dspy

class ReviewActionabilityFromComment(dspy.Signature):
    """
    Assess whether a code review comment is actionable/useful
    based only on the comment text.
    """

    review: str = dspy.InputField(
        desc="The natural language code review comment."
    )

    useful: bool = dspy.OutputField(
        desc=(
            "true if the comment identifies a concrete issue "
            "(bug, risk, inefficiency, edge case, or maintainability problem) "
            "and provides enough guidance to act; otherwise false"
        )
    )


class ReviewActionabilityWithDiff(dspy.Signature):
    """
    Assess whether a code review comment is actionable/useful
    given the associated code diff.
    """

    review: str = dspy.InputField(
        desc="The natural language code review comment."
    )

    codeDiff: str = dspy.InputField(
        desc=(
            "The code diff or patch the review comment refers to, "
            "including added (+) and removed (-) lines."
        )
    )

    useful: bool = dspy.OutputField(
        desc=(
            "true if the comment identifies a concrete issue "
            "(bug, risk, inefficiency, edge case, or maintainability problem) "
            "and provides enough guidance to act in the context of the diff; "
            "otherwise false"
        )
    )
