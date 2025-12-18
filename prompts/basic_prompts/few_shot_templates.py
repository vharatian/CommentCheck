def few_shot_classification(code, comment):
    return f"""
Classify the usefulness of the code review comment.
Output 'useful' if the comment helps improve code quality (bugs, logic, perf). Output 'not useful' if it is trivial, vague, or incorrect.

---
Example 1
Code:
`for i in range(len(arr)):`
`    if arr[i] == target:`
`        return True`
Comment: "You can use 'if target in arr:' for better readability and performance."

Reasoning: The comment suggests a Pythonic optimization that replaces a manual loop with a built-in operator. This improves readability and potentially speed.
Label: useful

---
Example 2
Code: 
`def calculate_total(a, b):`
`    return a + b`
Comment: "I don't like this function name."

Reasoning: The comment expresses a subjective preference ("I don't like") without suggesting a better alternative or explaining why the current name is misleading. It is not actionable.
Label: not useful

---
Example 3
Code:
`user_input = request.args.get('id')`
`query = "SELECT * FROM users WHERE id = " + user_input`
Comment: "This is vulnerable to SQL injection. Use parameterized queries."

Reasoning: The comment correctly identifies a critical security vulnerability (SQL injection) caused by direct string concatenation of user input. It provides the correct solution.
Label: useful

---
Current Task
Code: {code}
Comment: {comment}

Output Format:
Reasoning: <concise reasoning>
Label: <useful|not useful> 
"""

# ==================================================================================================================================================

def few_shot_analysis(code, comment):
    return f"""
You are an expert code reviewer. Analyze the code and comment to determine usefulness.

Example 1:
Code: `if (arr.length == 0) return null;`
Comment: "Check for null before checking length to avoid NPE."
Analysis: The code accesses `arr.length` immediately. If `arr` is null, this throws an exception. The comment identifies a valid bug (NullPointerException).
Conclusion: Useful.

Example 2:
Code: `int x = 5;`
Comment: "I think `val` would be a cooler name."
Analysis: The comment suggests a rename based on "coolness" (subjective preference). It offers no objective improvement to clarity or logic.
Conclusion: Not Useful.

Example 3:
Code: `for (int i=0; i < list.size(); i++) get(i)`
Comment: "Use an enhanced for-loop here for cleaner syntax."
Analysis: The suggestion replaces a manual index loop with a standard iterator loop. This improves readability and reduces boilerplate without changing logic.
Conclusion: Useful.

Task:
Code: {code}
Comment: {comment}

Output Format:
Analysis: <concise analysis>
"""

# Input of this methods is the output of the above prompt.
def classifier_decision(analysis):
   return f"""
You are a classifier. Read the analysis below and determine the final classification.

Input Context:
{analysis}

Rules:
- If the analysis concludes the comment is valid/useful/actionable, output 'useful'.
- If the analysis concludes the comment is subjective/incorrect/trivial, output 'not useful'.

Output Format:
Label: <useful|not useful> 
"""

# ==================================================================================================================================================

def generate_guidelines(gold_dataset_str):
    return f"""
You are an expert AI Data Analyst specializing in Code Review Quality Assurance. 

I am going to provide you with a training dataset of code reviews. Each entry contains a code snippet, a review comment, and a classification ("useful" or "not useful").

Your task is to:
1. Analyze the examples to understand the implicit logic used to classify them.
2. Abstract the specific code issues into broader Software Engineering categories (e.g., instead of "removing print statements", identify "Removing Debugging Artifacts").
3. Generate a "Code Review Quality Guideline" that applies these general categories.

Here is the Training Data:
{gold_dataset_str}

Output Requirement:
Generate a concise set of rules titled "Review Utility Guidelines". 
- The rules must be GENERALIZABLE. Do not mention specific variable names or specific syntax in the rule definitions. 
- Focus on the intent and impact of the review (e.g., Correctness, Maintainability, Style).

Output Format: 
Review Utility Guidelines
- [Category Name]: [One single sentence explanation of the rule]

(Strict Constraints: Do not use emojis. Do not use introductory text. Ensure every explanation is exactly one sentence long.)
"""

REVIEW_UTILITY_GUIDELINES = """
Review Utility Guidelines
Correctness and Logic Validation: A review is useful when it identifies potential logical errors, incorrect operations, or missing edge-case handling that could affect program behavior.
Maintainability and Code Structure: A review is useful when it recommends restructuring code to improve clarity, reduce complexity, or promote modular design.
Naming and Readability Standards: A review is useful when it highlights naming or readability issues that hinder understanding or violate established conventions.
Coding Style Consistency: A review is useful when it points out deviations from agreed style guidelines that materially improve consistency or clarity.
Removal of Debugging or Temporary Artifacts: A review is useful when it identifies leftover debugging or temporary code that should not persist in production.
Avoidance of Non-Impactful Preferences: A review is not useful when it suggests stylistic alternatives that do not materially improve correctness, clarity, or maintainability.
Avoidance of Trivial or Low-Value Feedback: A review is not useful when it flags issues that have negligible impact on code quality or do not meaningfully guide improvement.
"""

# Input of this methods is the output of the above prompt.
def classify_with_guidelines(code, comment, guidelines_text=REVIEW_UTILITY_GUIDELINES):
    return f"""
You are a Code Review Classification Bot. You must decide if a new code review comment is "useful" based strictly on the guidelines provided below.

Reference Guidelines
{guidelines_text}

Task
Analyze the following new input and classify it as "useful" or "not useful". Provide a brief reasoning based on the Reference Guidelines.

New Input
Review: {comment}
Code: {code}

Output Format:
Reasoning: <concise reasoning>
Label: <useful|not useful> 
"""
