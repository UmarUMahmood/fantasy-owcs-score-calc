from dotenv import load_dotenv
import os
import requests
from flask import Flask, request, jsonify
from table2ascii import table2ascii as t2a, PresetStyle
from collections import defaultdict
import json

load_dotenv()
API_KEY = os.getenv("API_KEY")

app = Flask(__name__)

# Constants
VALID_TOURNAMENTS = [
    "S1 EMEA Master: Road to Esports World Cup Central - Playoffs",
    "S1 NA Master: Road to Esports World Cup Central - Playoffs"
]

# Ensure output directory exists
os.makedirs("./output", exist_ok=True)

# Helper Functions
def fetch_data_from_api(endpoint, api_key):
    url = f"https://open.faceit.com/data/v4/{endpoint}"
    headers = {"accept": "application/json", "Authorization": f"Bearer {api_key}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def get_match_data(match_id, api_key):
    return fetch_data_from_api(f"matches/{match_id}", api_key)

def get_match_stats(match_id, api_key):
    return fetch_data_from_api(f"matches/{match_id}/stats", api_key)

def get_player_details(player_id, api_key):
    return fetch_data_from_api(f"players/{player_id}", api_key)

def get_team_name(faction_id, match_data):
    return next(
        (team["name"] for team in match_data["teams"].values() if team["faction_id"] == faction_id),
        "Failed to get Team Name"
    )

def get_map_name(map_id, match_data):
    return next(
        (map_entity["name"] for map_entity in match_data["voting"]["map"]["entities"] if map_entity["game_map_id"] == map_id),
        "Failed to get Map Name"
    )

def get_player_name(player_id, match_data, api_key):
    for team in match_data["teams"].values():
        for player in team["roster"]:
            if player["player_id"] == player_id:
                return player["game_player_name"]
    return get_player_details(player_id, api_key)["games"]["ow2"]["game_player_name"]

def get_team_stats(team_index, map_index, match_stats, match_data, api_key):
    role_order = {"Tank": 0, "Damage": 1, "Support": 2}
    players = match_stats["rounds"][map_index]["teams"][team_index]["players"]
    return sorted(
        [
            {
                "name": get_player_name(player_data["player_id"], match_data, api_key),
                "player_stats": player_data["player_stats"],
            }
            for player_data in players
        ],
        key=lambda x: (role_order[x["player_stats"]["Role"]], x["name"])
    )

def calculate_score(eliminations, deaths, damage, healing):
    elimination_points = eliminations // 3
    death_points = deaths * -1
    damage_points = (damage // 2000) * 0.5
    healing_points = (healing // 2000) * 0.5
    return elimination_points + death_points + damage_points + healing_points


def calculate_player_scores_for_each_map(match_data, match_stats, api_key):
    match_summary = []
    for i, round_data in enumerate(match_stats["rounds"]):
        result = {
            "match_round": i,
            "mode": round_data["round_stats"]["OW2 Mode"],
            "map": get_map_name(round_data["round_stats"]["Map"], match_data),
            "winner": get_team_name(round_data["round_stats"]["Winner"], match_data),
            "map_score": round_data["round_stats"]["Score Summary"],
            "teams": []
        }
        match_summary.append(result)

        for team_index in range(2):
            team_name = get_team_name(round_data["teams"][team_index]["team_id"], match_data)
            team = {"name": team_name, "players": []}
            result["teams"].append(team)

            team_stats = get_team_stats(team_index, i, match_stats, match_data, api_key)
            for player in team_stats:
                player_stats = player["player_stats"]
                score = calculate_score(
                    int(player_stats["Eliminations"]),
                    int(player_stats["Deaths"]),
                    int(player_stats["Damage Dealt"]),
                    int(player_stats["Healing Done"])
                )
                player_summary = {
                    "role": player_stats["Role"],
                    "name": player["name"],
                    "eliminations": player_stats["Eliminations"],
                    "deaths": player_stats["Deaths"],
                    "damage": player_stats["Damage Dealt"],
                    "healing": player_stats["Healing Done"],
                    "score": score
                }
                team["players"].append(player_summary)
    return match_summary

def calculate_player_scores_for_match(match_data, match_stats, api_key):
    match_summary = calculate_player_scores_for_each_map(match_data, match_stats, api_key)
    team_player_scores = defaultdict(lambda: defaultdict(int))
    for map_summary in match_summary:
        for team in map_summary["teams"]:
            team_name = team["name"]
            for player in team["players"]:
                player_name = player["name"]
                player_score = player["score"]
                team_player_scores[team_name][player_name] += player_score
    return [{team: dict(scores)} for team, scores in team_player_scores.items()]

def generate_ascii_table_for_match_rounds(match_data, file):
    for match_round in match_data:
        round_info = f"Map {match_round['match_round'] + 1}: {match_round['mode']} - {match_round['map']}\n"
        score_summary = f"{match_round['teams'][0]['name']} {match_round['map_score']} {match_round['teams'][1]['name']}\n\n"
        
        file.write(round_info)
        file.write(score_summary)

        for team in match_round['teams']:
            team_name = team['name']            
            # Prepare table data for each team
            headers = [team_name, "Eliminations", "Deaths", "Damage", "Healing", "Score"]
            rows = [
                [
                    player["name"], 
                    player["eliminations"], 
                    player["deaths"], 
                    player["damage"], 
                    player["healing"], 
                    f"{player['score']:.1f}"
                ]
                for player in team["players"]
            ]
            
            # Write the table for the team
            table = t2a(
                header=headers,
                body=rows,
                style=PresetStyle.double
            )
            file.write(f"{table}\n\n")

def generate_ascii_table_for_match(scores, file):
    for team_scores in scores:
        for team, players in team_scores.items():
            table_data = [
                [team, "Score"]
            ]
            for player, score in players.items():
                table_data.append([player, f"{score:.1f}"])
            table = t2a(
                header=table_data[0],
                body=table_data[1:],
                style=PresetStyle.double
            )
            file.write(f"{table}\n\n")

def generate_match_result(file, match_data):
    team1 = match_data["teams"]["faction1"]["name"]
    team1_score = match_data["results"]["score"]["faction1"]
    team2 = match_data["teams"]["faction2"]["name"]
    team2_score = match_data["results"]["score"]["faction2"]
    competition_name = match_data["competition_name"]
    file.write(f"{competition_name}\n{team1} {team1_score} - {team2} {team2_score}\n\n")

# Sample data loading for testing
# with open("./sample_data/match_data.json", "r") as file:
#     match_data = json.load(file)

# with open("./sample_data/match_stats.json", "r") as file:
#     match_stats = json.load(file)


def input_match_url():
    match_url = input("Enter the match URL: ")
    match_id = match_url.split("/")[-1]
    return match_id

match_id = input_match_url()
match_data = get_match_data(match_id, API_KEY)
match_stats = get_match_stats(match_id, API_KEY)

with open("./output/match_report.txt", "w") as file:
    generate_match_result(file, match_data)

    scores = calculate_player_scores_for_match(match_data, match_stats, API_KEY)
    generate_ascii_table_for_match(scores, file)

    match_summary = calculate_player_scores_for_each_map(match_data, match_stats, API_KEY)
    generate_ascii_table_for_match_rounds(match_summary, file)
