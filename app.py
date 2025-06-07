from flask import Flask, request, render_template, jsonify
from dotenv import load_dotenv
import os
import requests
from table2ascii import table2ascii as t2a, PresetStyle
from collections import defaultdict
import json

load_dotenv()
API_KEY = os.getenv("API_KEY")

app = Flask(__name__)

# Helper Functions - reusing your existing code
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
    # Handle draw case where faction_id is empty string
    if not faction_id or faction_id == "":
        return "Draw"
    
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
        key=lambda x: (role_order.get(x["player_stats"]["Role"], 3), x["name"])
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
        # Handle missing 'Winner' key or empty winner
        winner_faction = round_data["round_stats"].get("Winner", "")
        winner = get_team_name(winner_faction, match_data)
        
        result = {
            "match_round": i,
            "mode": round_data["round_stats"]["OW2 Mode"],
            "map": get_map_name(round_data["round_stats"]["Map"], match_data),
            "winner": winner,
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

def generate_ascii_table_for_match_rounds(match_summary, side_by_side=False):
    output = []
    for match_round in match_summary:
        round_info = f"Map {match_round['match_round'] + 1}: {match_round['mode']} - {match_round['map']}"
        
        score_summary = f"{match_round['teams'][0]['name']} {match_round['map_score']} {match_round['teams'][1]['name']}"
        
        output.append(round_info)
        output.append(score_summary)
        output.append("")  # Empty line

        if side_by_side and len(match_round['teams']) == 2:
            # Side by side display for exactly 2 teams
            team_tables = []
            for team in match_round['teams']:
                team_name = team['name']            
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
                
                team_table = t2a(
                    header=headers,
                    body=rows,
                    style=PresetStyle.double
                )
                team_tables.append(team_table)
            
            # Split tables into lines and combine side by side
            table1_lines = team_tables[0].split('\n')
            table2_lines = team_tables[1].split('\n')
            
            max_lines = max(len(table1_lines), len(table2_lines))
            combined_table = []
            
            for i in range(max_lines):
                line1 = table1_lines[i] if i < len(table1_lines) else " " * len(table1_lines[0])
                line2 = table2_lines[i] if i < len(table2_lines) else " " * len(table2_lines[0])
                combined_table.append(f"{line1}    {line2}")
                
            output.append('\n'.join(combined_table))
            output.append("")  # Empty line
        else:
            # Default vertical display
            for team in match_round['teams']:
                team_name = team['name']            
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
                
                table = t2a(
                    header=headers,
                    body=rows,
                    style=PresetStyle.double
                )
                output.append(table)
                output.append("")  # Empty line
    
    return "\n".join(output)

def generate_ascii_table_for_match(scores, side_by_side=False):
    output = []
    
    if side_by_side and len(scores) == 2:
        # Side by side display for exactly 2 teams
        team1_name = list(scores[0].keys())[0]
        team1_players = scores[0][team1_name]
        team2_name = list(scores[1].keys())[0]
        team2_players = scores[1][team2_name]
        
        # Generate tables
        table1_data = [[team1_name, "Score"]]
        for player, score in team1_players.items():
            table1_data.append([player, f"{score:.1f}"])
            
        table2_data = [[team2_name, "Score"]]
        for player, score in team2_players.items():
            table2_data.append([player, f"{score:.1f}"])
            
        table1 = t2a(
            header=table1_data[0],
            body=table1_data[1:],
            style=PresetStyle.double
        )
        
        table2 = t2a(
            header=table2_data[0],
            body=table2_data[1:],
            style=PresetStyle.double
        )
        
        # Split tables into lines and combine side by side
        table1_lines = table1.split('\n')
        table2_lines = table2.split('\n')
        
        max_lines = max(len(table1_lines), len(table2_lines))
        combined_table = []
        
        for i in range(max_lines):
            line1 = table1_lines[i] if i < len(table1_lines) else " " * len(table1_lines[0])
            line2 = table2_lines[i] if i < len(table2_lines) else " " * len(table2_lines[0])
            combined_table.append(f"{line1}    {line2}")
            
        output.append('\n'.join(combined_table))
        output.append("")  # Empty line
    else:
        # Default vertical display
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
                output.append(table)
                output.append("")  # Empty line
    
    return "\n".join(output)

def generate_match_result(match_data):
    team1 = match_data["teams"]["faction1"]["name"]
    team1_score = match_data["results"]["score"]["faction1"]
    team2 = match_data["teams"]["faction2"]["name"]
    team2_score = match_data["results"]["score"]["faction2"]
    competition_name = match_data["competition_name"]
    
    # Overall match result - no draw indication needed
    return f"{competition_name}\n{team1} {team1_score} - {team2} {team2_score}\n\n"

def process_match(match_url, side_by_side=False):
    try:
        match_id = match_url.split("/")[-1]
        match_data = get_match_data(match_id, API_KEY)
        match_stats = get_match_stats(match_id, API_KEY)
        
        # Generate the match report
        report = generate_match_result(match_data)
        
        # Calculate scores and generate tables
        scores = calculate_player_scores_for_match(match_data, match_stats, API_KEY)
        report += generate_ascii_table_for_match(scores, side_by_side)
        
        match_summary = calculate_player_scores_for_each_map(match_data, match_stats, API_KEY)
        report += generate_ascii_table_for_match_rounds(match_summary, side_by_side)
        
        return report
    except Exception as e:
        return f"Error processing match: {str(e)}"

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    match_url = request.form.get('match_url')
    side_by_side = request.form.get('side_by_side') == 'true'
    
    if not match_url:
        return jsonify({"error": "No match URL provided"}), 400
    
    try:
        report = process_match(match_url, side_by_side)
        return jsonify({"report": report})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True)