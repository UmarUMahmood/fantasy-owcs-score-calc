# Fantasy OWCS Score Calculator - Web Application

This web application allows users to easily generate Fantasy OWCS score reports by simply pasting a FACEIT match URL. The application processes the match data and displays a formatted report directly in the browser, which can be easily copied to share on Discord or other platforms.

## Features

- Simple web interface for inputting FACEIT match URLs
- Automatic processing of match data using the FACEIT API
- Formatted display of match results and player scores
- Copy to clipboard functionality for easy sharing
- No installation required for end users

## Installation

1. **Clone the repository:**

    ```sh
    git clone git@github.com:YourUsername/fantasy-owcs-webapp.git
    cd fantasy-owcs-webapp
    ```

2. **Create a virtual environment:**

    ```sh
    python3 -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```

3. **Install the required packages:**

    ```sh
    pip install flask dotenv requests table2ascii
    ```

4. **Create a `.env` file with your FACEIT API key:**

    ```sh
    echo "API_KEY=your-api-key-here" > .env
    ```

    Replace `your-api-key-here` with your actual FACEIT API key from the [FACEIT Developer Portal](https://developers.faceit.com/).

5. **Create the templates directory and add the HTML template:**

    ```sh
    mkdir -p templates
    # Copy the index.html file into this directory
    ```

## Running the Application Locally

1. **Start the Flask app:**

    ```sh
    python app.py
    ```

2. **Access the application:**
   Open your browser and navigate to `http://127.0.0.1:5000`
