# CommentCheck

CommentCheck is a research replication package for evaluating the actionability of code review comments. Given a review comment and its corresponding code diff, the system predicts whether the comment is actionable or 
non-actionable.

The project reproduces the experimental setup from the paper by implementing classifiers powered by large language models using DSPy, and relies on few-shot to guide model behavior through labeled examples. The framework supports both:

- Standard prompting
- Chain-of-Thought prompting

The goal is to analyze how incorporating code diffs and explicit reasoning affects the accuracy of actionability classification in code review scenarios.

## Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/vharatian/CommentCheck.git
    cd CommentCheck
    ```

2.  **Install dependencies:**
    
    Ensure you have Python installed. 
    
    Install the required Python packages using `pip` and the `requirements.txt` file found in the root of the project:

    ```bash
    pip install -r requirements.txt
    ```

## Configuration

### Environment Variables (`.env`)

You need to set up a `.env` file in the root directory to manage sensitive configuration such as API keys and model names.

Create a file named `.env` in the project root and populate it with the following variables:

```ini
MODEL=<your_model_name>
API_BASE=<your_api_base_url>
API_KEY=<your_api_key>
```

The application uses `python-dotenv` to load these variables.

### Config File (`config.py`)

The `config.py` file manages the configuration for the project. Key parameters include:

-   **Model Configuration**:
    -   `MODEL_NAME`: The name of the LLM to use (loaded from `.env`).
    -   `API_BASE`: The base URL for the API (loaded from `.env`).
    -   `API_KEY`: The API key (loaded from `.env`).
    -   `MAX_TOKENS`: Maximum number of tokens to generate (default: `500`).
    -   `TEMPERATURE`: Sampling temperature (default: `0.0` for deterministic results).
    -   `CACHE_ENABLED`: Whether to cache DSPy calls (default: `True`).

-   **Paths**:
    -   `INITIAL_SET_PATH`: Path to the initial dataset.
    -   `EXAMPLES_SET_PATH`: Path to the few-shot examples dataset.
    -   `EVALUATION_SET_PATH`: Path to the evaluation dataset.

-   **Hyperparameters**:
    -   `EMBEDDING_MODEL`: The model used for embeddings (default: `all-MiniLM-L6-v2`).
    -   `RANDOM_K`: Number of examples to use for few-shot (default: `4`).


## Language Models Used

The experiments are conducted using multiple LLaMA-family language models to analyze the impact of model size and capacity on code review comment actionability classification.

Specifically, the following models are used:

- LLaMA 3.2 (3B)
- LLaMA 3.2 (1B)
- LLaMA 2 (7B)

All models are accessed through a unified API interface and are interchangeable within the same experimental pipeline.

## Language Model Configuration

### Running Models Locally with Ollama

The experiments can be run using Ollama to serve LLaMA models locally.

To install Ollama, follow the official instructions for your operating system:

👉 https://ollama.com/download

After installation, download the required models, for example:

```bash
ollama pull llama3.2:1b
```

Before running any experiment script, make sure that Ollama is running and listening for requests. (default port: `11434`).


### Environment Variable Setup

Model selection is controlled via environment variables and the centralized configuration file.

To switch between models, update the `MODEL` and `API_BASE` variable in the `.env` file:

Example configuration of `.env` file.

```ini
MODEL=ollama_chat/llama3.2:1b
API_BASE=http://localhost:11434
```
Note: When running models locally via Ollama, an `API_KEY` is typically not required.


## Usage

This package includes two main scripts found in the `prompts/` directory to replicate the experiments. Both scripts must be run from the root of the project.

### Few-Shot Prompting

Both commands below run the labeled few-shot prompting experiment. The difference is whether the model is allowed to produce explicit Chain-of-Thought reasoning.

**Few-Shot Prompting (Without Chain-of-Thought)**

Runs the labeled few-shot classifier without explicit reasoning:

```bash
python prompts/labeled_few_shot.py
```

**Chain of Thought (CoT)**

Runs the same labeled few-shot setup, but enables Chain-of-Thought prompting, allowing the model to reason explicitly before predicting:

```bash
python prompts/labeled_few_shot.py --cot
```

### Outputs

Both scripts will yield the following results.


-   Per-example prediction status (Real vs. Prediction).
-   Model trace (history).
-   Final classification report.
-   Final confusion matrix.
