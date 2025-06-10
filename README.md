# Fantasy OWCS Dashboard

A web app for Fantasy OWCS that provides match points calculation, leaderboard tracking and player transfer analysis. Users can generate match reports that contain the match stats with fantasy scores for each player and explore statistics from each week about the Fantasy OWCS leaderboard and Player Transfers.

## Features

### Match Calculator

- Enter a FACEIT Match URL
- Fetches match data using the FACEIT API
- Generates ASCII tables showing player stats, fantasy points, map results and the match result

### Leaderboards

- View the Fantasy OWCS leaderboard for each individual Gameweek
- Access additional information such as change in rank and which transfers are being made
- Filter the leaderboards using a combination of players
- Find out the average points for each gameweek and average points for filtered rosters

### Player Transfers

- Track which players are being transferred in/out (only after the deadline for that gameweek)
- Filter by Role
- Compare trends across different weeks

## Local Development

### Prerequisites

- Python 3.8
- FACEIT API key ([Get one here](https://developers.faceit.com/))

### Setup

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
    pip install -r requirements.txt
    ```

4. **Create a `.env` file with your FACEIT API key:**

    ```sh
    echo "API_KEY=your-api-key-here" > .env
    ```

    Replace `your-api-key-here` with your actual FACEIT API key from the [FACEIT Developer Portal](https://developers.faceit.com/).

5. **Run the application:**

    ```bash
    python app.py
    ```

6. **Access the application:** Open your browser and navigate to `http://127.0.0.1:5000`

## Deployment

### Deploy to Vercel

1. **Install Vercel CLI:**

    ```bash
    npm i -g vercel
    ```

2. **Deploy:**

    ```bash
    vercel --prod
    ```

3. **Set environment variables:** In your Vercel dashboard, add your `API_KEY` environment variable.

## Acknowledgements

- [Fantasy OWCS](https://owfantasy.com/) for making the actual fantasy game this is entirely based on
- [FACEIT](https://www.faceit.com/) for hosting the Overwatch Esports games and providing data through their API
