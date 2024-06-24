# Fantasy OWCS Score Calc

Generate a match report from a link to a FACEIT Overwatch match that also contains scores for the [Fantasy OWCS web app](https://owcsfantasy.web.app/).

## Installation

1. **Clone the repository:**

    ```sh
    git clone git@github.com:UmarUMahmood/fantasy-owcs-score-calc.git
    cd fantasy-owcs-score-calc
    ```

2. **Create a virtual environment:**

    ```sh
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3. **Install the required packages:**

    ```sh
    pip install -r requirements.txt
    ```

## Configuration

1. **Create a `.env` file with your FACEIT API key:**

    ```sh
    echo "API_KEY=api-key-here" > .env
    ```

    Replace `api-key-here` with your actual FACEIT API key. You can obtain an API key from the [FACEIT Developer Portal](https://developers.faceit.com/).

## Usage

1. **Run the script:**

    ```sh
    python3 main.py
    ```

2. **Copy/Paste the link to the match from FACEIT:**

    For example: `https://www.faceit.com/en/ow2/room/1-d260e7c6-0235-417e-80bf-40b41a0e6f60`

3. **Copy/Paste the output:**

    After running the script, copy the output from the generated .md file in the `output` directory and paste it into Discord or wherever.
