def zero_shot_classification(code, comment):
    return f"""
You are an expert code review assistant. Your task is to classify whether an inline review comment is useful.

Definitions:
- Useful: Identifies bugs, performance issues, security risks, edge cases, or significant readability improvements.
- Not Useful: Vague, subjective nitpicking, incorrect claims, trivial formatting or non-actionable compliments.

Input:
- Code: {code}
- Comment: {comment}

Instructions:
1. Analyze the relationship between the code and the comment.
2. Think step-by-step: Is the comment factually correct? Is the suggestion actionable? Does it improve quality?
3. Conclude with the final classification.

Output Format:
Reasoning: <concise reasoning>
Label: <useful|not useful> 
"""

# ==================================================================================================================================================

def chain_of_thought_analysis(code, comment):
    return f"""
You are an expert code reviewer. Analyze the following code snippet and review comment to determine if the comment is useful or not useful.

Definitions:
- Useful: Actionable, fixes bugs, improves performance/security, or objectively improves readability.
- Not Useful: Subjective, vague, incorrect, or trivial.

Input:
Code: {code}
Comment: {comment}

Instruction: Let's think step by step. Analyze the code logic, the comment's validity, and whether it provides objective value. Do not output the final label yet.

Output Format:
Reasoning: <concise reasoning>
"""


# Input of this methods is the output of the above prompt.
def boolean_decision(analysis):
    return f"""
You are a data classifier. Your task is to output a final boolean label based on the provided analysis.

Input Context:
Analysis: {analysis}

Task: Based strictly on the analysis above, is the comment useful?

Output Format:
Label: <useful|not useful> 
"""

# ==================================================================================================================================================

def analyze_code_technical(code):
    return f"""
You are a senior software engineer. Analyze the code snippet below.

1. Summarize what the code does in one sentence.
2. List any objective technical defects (bugs, security risks, performance issues, or logical errors) present in the code.

Code: {code}

Output Format:
Summary: <concise summary>
Defects: <concise defects>
"""

# Input of this methods is the output of the above prompt.
def classify_with_knowledge(code_analysis, comment):
    return f"""
You are a data classifier. Determine if the review comment is useful or not useful using the provided code analysis.

Context (Code Analysis):
{code_analysis}

Review Comment:
{comment}

Rules:
- If the comment points out a defect listed in the Context, output 'true'.
- If the comment offers a valid optimization mentioned in the Context, output 'true'.
- If the comment contradicts the Context or is subjective/vague, output 'false'.

Output Format:
Label: <useful|not useful> 
"""

# ==================================================================================================================================================

GOLD_STANDARD_CRITERIA = """
1. Objectivity: The comment is grounded in observable facts about the code (behavior, style violations, logical issues) rather than personal preference or vague opinions.
2. Actionability: The comment includes a clear, implementable suggestion or identifies a concrete issue that the author can directly address.
3. Technical Accuracy and Value: The comment identifies a real technical concern—such as a bug, security flaw, performance issue, incorrect assumption, or standards violation.
4. Improvement to Code Quality: The comment meaningfully contributes to improving readability, maintainability, modularity, or consistency in the codebase.
5. Relevance and Specificity: The comment directly pertains to the code segment under review and is specific enough to guide the developer without requiring guesswork.
"""

def evaluate_against_gold_standard(code, comment, gold_standard_criteria=GOLD_STANDARD_CRITERIA):
    return f"""
You are an automated quality gate for code reviews.

The Standard (Criteria for Usefulness):
{gold_standard_criteria}

Input Data:
Code Snippet: {code}
Review Comment: {comment}

Instructions:
1. Analyze the Code Snippet to understand its functionality.
2. Evaluate the Review Comment against The Standard provided above.
3. If the comment satisfies at least one of the criteria in The Standard and is factually correct, the class is 'useful'.
4. If the comment fails The Standard (is subjective, incorrect, or trivial), the class is 'not useful'.

Output Format:
Label: <useful|not useful> 
"""

# ==================================================================================================================================================

def token_usage_minimized(code, comment):
    return f"""
Code:{code}
Review:{comment}
Output Format:"useful" or "not useful"(nothing else)
"""
