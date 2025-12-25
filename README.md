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


# Data collection

A collection of tools for analyzing GitHub repositories and their code review comments.

## Setup

### Prerequisites

- Python 3.x
- Git (if using git-based diff fetching)
- GitHub Personal Access Token with appropriate permissions

### Installation

1. **Create and activate virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   .venv/bin/pip install -r requirements.txt
   ```

3. **Create `.env` file** in the project root with your GitHub token:
   ```
   GITHUB_TOKEN=your_github_token_here
   ```
   
   **Note**: All tools in this project require a GitHub token. Create one at [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens) with appropriate permissions (at minimum: `public_repo` scope for public repositories).

### Project Structure

```
CommentCheck/
├── .venv/              # Virtual environment (created during setup)
├── .env                # GitHub token (create this)
├── files/
│   ├── repos.txt       # Repository list (create for comment scraper)
│   ├── comments/       # Output directory for comment scraper
│   ├── clones/         # Cloned git repositories (created automatically)
│   └── validation.csv  # Output for validation dataset creation
├── queries/            # GraphQL query templates
├── comment_scraper.py
├── find_python_repos.py
├── create_validation_dataset.py
└── requirements.txt
```

## Comment Scraper (`comment_scraper.py`)

Collects code review comments from GitHub pull requests, extracting detailed information about comments placed on specific lines of code in merged PRs.

### What it does

- Processes multiple repositories in parallel
- Collects review comments from merged pull requests only
- Extracts comments placed on specific code lines (not general thread comments)
- Gathers comprehensive metadata including PR info, diffs, linked issues, and comment threads
- Writes data incrementally to JSONL files (one per repository)
- Automatically manages GitHub API rate limits (4800 requests/hour)
- Supports two methods for fetching PR diffs: local git repositories or REST API

### How it works

1. **Reads repository list** from `files/repos.txt` (one `owner/repo` per line)
2. **Processes repositories in parallel** using multiple worker threads
3. **For each repository**:
   - Fetches merged pull requests using GitHub GraphQL API
   - Extracts review threads with comments on specific code lines
   - Collects PR metadata, diffs, and linked issues
   - Writes comments incrementally to JSONL file
4. **Rate limiting**: Automatically throttles requests to stay under 4800/hour limit
5. **Progress tracking**: Shows real-time progress bars for each repository

### Configuration

All configuration parameters are defined at the top of `comment_scraper.py`:

- **`REPOS_LIST_PATH`**: Path to file containing repository list (default: `files/repos.txt`)
- **`OUTPUT_DIR`**: Directory for output JSONL files (default: `files/comments`)
- **`CLONES_DIR`**: Directory for cloned git repositories (default: `files/clones`)
- **`MAX_COMMENTS_PER_REPO`**: Maximum comments to collect per repo (default: 100, set to `None` for all)
- **`PR_CREATED_BEFORE_ISO`**: Only process PRs created before this date (default: `2025-12-01T00:00:00Z`)
- **`MAX_WORKERS`**: Number of parallel workers (default: 4)
- **`USE_GIT_FOR_DIFFS`**: Use local git (`True`) or REST API (`False`) for diffs (default: `False`)
- **`MAX_REQUESTS_PER_HOUR`**: Rate limit threshold (default: 4800)

### Setup

1. **Follow the general setup instructions above** (install requirements, create `.env` file)

2. **Create repository list** in `files/repos.txt` (one `owner/repo` per line):
   ```
   owner1/repo1
   owner2/repo2
   ```

3. **Run the script**:
   ```bash
   .venv/bin/python comment_scraper.py
   ```

### Output

The script creates one JSONL file per repository in the `files/comments/` directory:
- Format: `{owner}_{name}_comments.jsonl`
- Each line is a JSON object containing:
  - Comment text and metadata
  - PR information (number, title, description, commits)
  - File path and code diff hunk
  - Full PR diff and per-file diffs
  - Comment thread (all replies)
  - Linked issues
  - Timestamps and resolution status

### Features

- **Incremental writing**: Comments are written as they're found, so data is preserved even if the script fails
- **Rate limit management**: Automatic throttling prevents exceeding GitHub's API limits
- **Parallel processing**: Multiple repositories processed simultaneously
- **Two diff methods**: Choose between local git (faster, no API cost) or REST API (no cloning needed)
- **Progress tracking**: Real-time progress bars show status for each repository
- **Retry logic**: Automatic retries for failed API calls with exponential backoff

## Repository Finder (`find_python_repos.py`)

Searches GitHub for Python repositories that meet specific criteria using the GitHub GraphQL API. The script filters repositories based on Python language percentage, stars, issues, and pull requests, then exports the results to a timestamped CSV file.

### What it does

- Searches GitHub repositories sorted by popularity (stars)
- Filters repositories that are ≥95% Python (configurable)
- Checks minimum requirements for stars, issues, and PRs
- Determines if repositories are actively using GitHub issues
- Exports results to a timestamped CSV file

### Configuration

All configuration parameters are defined at the top of `find_python_repos.py`:

- **`PYTHON_PERCENTAGE_THRESHOLD`**: Minimum Python code percentage (default: 95.0)
- **`REPOSITORY_THRESHOLD`**: Number of repositories to find before stopping (default: 20)
- **`REPOSITORIES_PER_PAGE`**: Repositories per GraphQL query (default: 50)
- **`MIN_STARS`**: Minimum star count (default: 1000)
- **`MIN_ISSUES`**: Minimum number of issues required (default: 5000)
- **`MIN_PRS`**: Minimum number of PRs required (default: 5000)
- **`ISSUE_ACTIVITY_MONTHS`**: Consider issues "active" if updated within this period (default: 24 months)
- **`OUTPUT_CSV_BASE_PATH`**: Base path for output CSV files (timestamp is automatically appended)

### Setup

1. **Follow the general setup instructions above** (install requirements, create `.env` file)

2. **Run the script**:
   ```bash
   .venv/bin/python find_python_repos.py
   ```

### Output

The script creates a timestamped CSV file in the `files/repos/` directory with the following columns:

- **Repository**: Full repository name (owner/repo)
- **Stars**: Number of stars
- **Python_Percentage**: Percentage of Python code
- **PR_Count**: Total number of pull requests
- **Issue_Count**: Total number of issues
- **Issues_Active**: Whether issues are actively used (Yes/No)
- **Last_Issue_Updated**: Timestamp of most recent issue update

Example filename: `repos_20251220_143530.csv`

Each run creates a new CSV file, preserving previous results.

## Validation Dataset Creation (`create_validation_dataset.py`)

Creates a balanced validation dataset from comment files by randomly sampling equal numbers of resolved and unresolved comments from each repository.

### What it does

- Analyzes all comment JSON files in the `files/comments/` directory
- Provides an overview of resolved vs unresolved comment statistics per repository
- Creates a balanced dataset by randomly sampling a specified number of comments from each repository
- Ensures equal representation of resolved and unresolved comments (e.g., 8 resolved + 8 unresolved per repository)
- Exports the balanced dataset to a CSV file for validation purposes

### Configuration

All configuration parameters are defined at the top of `create_validation_dataset.py`:

- **`COMMENTS_DIR`**: Directory containing comment JSON files (default: `files/comments`)
- **`OUTPUT_CSV`**: Path to output CSV file (default: `files/validation.csv`)
- **`SAMPLES_PER_DATASET`**: Total number of samples per repository (default: 16, meaning 8 resolved + 8 unresolved)
- **`RANDOM_SEED`**: Random seed for reproducible sampling (default: 42)

### Setup

1. **Follow the general setup instructions above** (install requirements, create `.env` file)

2. **Ensure you have comment JSONL files** in the `files/comments/` directory (created by `comment_scraper.py`)

3. **Run the script**:
   ```bash
   .venv/bin/python create_validation_dataset.py
   ```

### Sampling Process

The script uses a stratified random sampling approach:

1. **Per-Repository Analysis**: For each repository, the script counts total resolved and unresolved comments
2. **Balanced Sampling**: Randomly selects an equal number of resolved and unresolved comments from each repository
3. **Random Selection**: Uses a fixed random seed to ensure reproducibility while maintaining randomness
4. **Fallback Handling**: If a repository has fewer comments of one type than required, it uses all available comments and displays a warning

The resulting dataset maintains equal representation across repositories and comment resolution status, making it suitable for validation and evaluation tasks.

### Output

The script creates a CSV file with the following columns:

- **`reponame`**: Repository name in `owner/repo` format
- **`PR_link`**: URL to the pull request
- **`comment_link`**: URL to the specific comment
- **`resolved`**: Boolean indicating whether the comment was resolved (`True`) or not (`False`)

The output file also includes a summary printed to the console showing:
- Overall statistics (total resolved vs unresolved comments)
- Per-repository breakdown
- Final dataset statistics (total samples, repositories, resolved/unresolved counts)
