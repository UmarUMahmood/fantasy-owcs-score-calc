from flask import Flask, request, render_template, jsonify
from dotenv import load_dotenv
import os
import requests
from table2ascii import table2ascii as t2a, PresetStyle
from collections import defaultdict
import json
from typing import Dict, List, Set, Tuple

load_dotenv()
API_KEY = os.getenv("API_KEY")

app = Flask(__name__)

# Helper Functions for match processing (keeping your existing code)
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
        output.append("")

        if side_by_side and len(match_round['teams']) == 2:
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
            
            table1_lines = team_tables[0].split('\n')
            table2_lines = team_tables[1].split('\n')
            
            max_lines = max(len(table1_lines), len(table2_lines))
            combined_table = []
            
            for i in range(max_lines):
                line1 = table1_lines[i] if i < len(table1_lines) else " " * len(table1_lines[0])
                line2 = table2_lines[i] if i < len(table2_lines) else " " * len(table2_lines[0])
                combined_table.append(f"{line1}    {line2}")
                
            output.append('\n'.join(combined_table))
            output.append("")
        else:
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
                output.append("")
    
    return "\n".join(output)

def generate_ascii_table_for_match(scores, side_by_side=False):
    output = []
    
    if side_by_side and len(scores) == 2:
        team1_name = list(scores[0].keys())[0]
        team1_players = scores[0][team1_name]
        team2_name = list(scores[1].keys())[0]
        team2_players = scores[1][team2_name]
        
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
        
        table1_lines = table1.split('\n')
        table2_lines = table2.split('\n')
        
        max_lines = max(len(table1_lines), len(table2_lines))
        combined_table = []
        
        for i in range(max_lines):
            line1 = table1_lines[i] if i < len(table1_lines) else " " * len(table1_lines[0])
            line2 = table2_lines[i] if i < len(table2_lines) else " " * len(table2_lines[0])
            combined_table.append(f"{line1}    {line2}")
            
        output.append('\n'.join(combined_table))
        output.append("")
    else:
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
                output.append("")
    
    return "\n".join(output)

def generate_match_result(match_data):
    team1 = match_data["teams"]["faction1"]["name"]
    team1_score = match_data["results"]["score"]["faction1"]
    team2 = match_data["teams"]["faction2"]["name"]
    team2_score = match_data["results"]["score"]["faction2"]
    competition_name = match_data["competition_name"]
    
    return f"{competition_name}\n{team1} {team1_score} - {team2} {team2_score}\n\n"

def process_match(match_url, side_by_side=False):
    try:
        match_id = match_url.split("/")[-1]
        match_data = get_match_data(match_id, API_KEY)
        match_stats = get_match_stats(match_id, API_KEY)
        
        report = generate_match_result(match_data)
        
        scores = calculate_player_scores_for_match(match_data, match_stats, API_KEY)
        report += generate_ascii_table_for_match(scores, side_by_side)
        
        match_summary = calculate_player_scores_for_each_map(match_data, match_stats, API_KEY)
        report += generate_ascii_table_for_match_rounds(match_summary, side_by_side)
        
        return report
    except Exception as e:
        return f"Error processing match: {str(e)}"

# New functions for leaderboard analysis
def load_json_files(directory: str) -> Dict[str, List[Dict]]:
    """Load all JSON files from a directory, with the filename as the key."""
    gameweek_data = {}
    
    try:
        for filename in os.listdir(directory):
            if filename.endswith('.json'):
                file_path = os.path.join(directory, filename)
                try:
                    with open(file_path, 'r') as file:
                        gameweek_data[filename] = json.load(file)
                except json.JSONDecodeError:
                    print(f"Error: {filename} is not a valid JSON file")
                except Exception as e:
                    print(f"Error loading {filename}: {str(e)}")
    except FileNotFoundError:
        print(f"Directory '{directory}' not found")
    
    return gameweek_data

def get_user_roster(roster: Dict) -> Set[str]:
    """Extract all players from a user's roster."""
    players = set()
    players.add(roster.get("tank", "Unknown"))
    players.add(roster.get("dpsOne", "Unknown"))
    players.add(roster.get("dpsTwo", "Unknown"))
    players.add(roster.get("supportOne", "Unknown"))
    players.add(roster.get("supportTwo", "Unknown"))
    return players

def calculate_transfers(current_gw_data: List[Dict], previous_gw_data: List[Dict]) -> Dict[str, Dict]:
    """Calculate transfer in/out data by comparing gameweeks."""
    previous_rosters = {roster["username"]: roster for roster in previous_gw_data}
    
    transfer_stats = {}
    existing_users = 0
    
    for current_roster in current_gw_data:
        username = current_roster["username"]
        
        if username in previous_rosters:
            existing_users += 1
            previous_roster = previous_rosters[username]
            
            current_players = get_user_roster(current_roster)
            previous_players = get_user_roster(previous_roster)
            
            transferred_in = current_players - previous_players
            transferred_out = previous_players - current_players
            
            for player in transferred_in:
                if player not in transfer_stats:
                    transfer_stats[player] = {"transferred_in": 0, "transferred_out": 0}
                transfer_stats[player]["transferred_in"] += 1
                
            for player in transferred_out:
                if player not in transfer_stats:
                    transfer_stats[player] = {"transferred_in": 0, "transferred_out": 0}
                transfer_stats[player]["transferred_out"] += 1
    
    return transfer_stats, existing_users

def analyze_player_frequency(rosters: List[Dict], transfer_data: Dict = None, existing_users: int = 0) -> List[Dict]:
    """Analyze player selection frequency in rosters with optional transfer data."""
    player_stats = {}
    total_teams = len(rosters)
    
    for roster in rosters:
        tank_player = roster.get("tank", "Unknown")
        if tank_player not in player_stats:
            player_stats[tank_player] = {"role": "tank", "count": 0}
        player_stats[tank_player]["count"] += 1
        
        for dps_key in ["dpsOne", "dpsTwo"]:
            dps_player = roster.get(dps_key, "Unknown")
            if dps_player not in player_stats:
                player_stats[dps_player] = {"role": "dps", "count": 0}
            player_stats[dps_player]["count"] += 1
        
        for support_key in ["supportOne", "supportTwo"]:
            support_player = roster.get(support_key, "Unknown")
            if support_player not in player_stats:
                player_stats[support_player] = {"role": "support", "count": 0}
            player_stats[support_player]["count"] += 1
    
    result = []
    for player_name, stats in player_stats.items():
        percentage = (stats["count"] / total_teams) * 100
        
        player_data = {
            "name": player_name,
            "role": stats["role"],
            "count": stats["count"],
            "percentage": round(percentage, 1)
        }
        
        if transfer_data and player_name in transfer_data:
            transfers = transfer_data[player_name]
            player_data["transferred_in"] = transfers["transferred_in"]
            player_data["transferred_out"] = transfers["transferred_out"]
            player_data["net_transfers"] = transfers["transferred_in"] - transfers["transferred_out"]
            
            if existing_users > 0:
                player_data["transfer_in_pct"] = round((transfers['transferred_in'] / existing_users) * 100, 1)
                player_data["transfer_out_pct"] = round((transfers['transferred_out'] / existing_users) * 100, 1)
            else:
                player_data["transfer_in_pct"] = 0.0
                player_data["transfer_out_pct"] = 0.0
        else:
            if transfer_data is not None:
                player_data.update({
                    "transferred_in": 0,
                    "transferred_out": 0,
                    "net_transfers": 0,
                    "transfer_in_pct": 0.0,
                    "transfer_out_pct": 0.0
                })
        
        result.append(player_data)
    
    result.sort(key=lambda x: (-x["count"], x["name"]))
    
    return result

def generate_leaderboard(current_gw_data: List[Dict], previous_gw_data: List[Dict] = None, gameweek_name: str = "") -> List[Dict]:
    """Generate leaderboard with weekly points, overall positions, and position changes."""
    leaderboard = []
    
    previous_rosters = {}
    previous_total_positions = {}
    
    if previous_gw_data:
        previous_rosters = {roster["username"]: roster for roster in previous_gw_data}
        
        previous_total_leaderboard = sorted(previous_gw_data, key=lambda x: float(x.get("score", 0)), reverse=True)
        previous_total_positions = {roster["username"]: i + 1 for i, roster in enumerate(previous_total_leaderboard)}
    
    current_total_leaderboard = sorted(current_gw_data, key=lambda x: float(x.get("score", 0)), reverse=True)
    current_total_positions = {roster["username"]: i + 1 for i, roster in enumerate(current_total_leaderboard)}
    
    for roster in current_gw_data:
        username = roster["username"]
        current_total_score = float(roster.get("score", 0))
        
        weekly_points = current_total_score
        if username in previous_rosters:
            previous_total_score = float(previous_rosters[username].get("score", 0))
            weekly_points = current_total_score - previous_total_score
        
        leaderboard_entry = {
            "username": username,
            "weekly_points": round(weekly_points, 1),
            "current_total_score": round(current_total_score, 1),
            "current_overall_position": current_total_positions[username],
            "transferred_in": [],
            "transferred_out": [],
            "tank": roster.get("tank", "Unknown"),
            "dpsOne": roster.get("dpsOne", "Unknown"),
            "dpsTwo": roster.get("dpsTwo", "Unknown"),
            "supportOne": roster.get("supportOne", "Unknown"),
            "supportTwo": roster.get("supportTwo", "Unknown")
        }
        
        if username in previous_rosters:
            previous_total_score = float(previous_rosters[username].get("score", 0))
            previous_overall_position = previous_total_positions.get(username)
            
            leaderboard_entry["previous_total_score"] = round(previous_total_score, 1)
            leaderboard_entry["previous_overall_position"] = previous_overall_position
            
            if previous_overall_position is not None:
                overall_position_change = previous_overall_position - leaderboard_entry["current_overall_position"]
                leaderboard_entry["overall_position_change"] = overall_position_change
            else:
                leaderboard_entry["overall_position_change"] = 0
            
            current_players = get_user_roster(roster)
            previous_players = get_user_roster(previous_rosters[username])
            
            transferred_in = current_players - previous_players
            transferred_out = previous_players - current_players
            
            leaderboard_entry["transferred_in"] = list(transferred_in)
            leaderboard_entry["transferred_out"] = list(transferred_out)
        else:
            leaderboard_entry["previous_total_score"] = None
            leaderboard_entry["previous_overall_position"] = None
            leaderboard_entry["overall_position_change"] = 0
        
        leaderboard.append(leaderboard_entry)
    
    leaderboard.sort(key=lambda x: x["weekly_points"], reverse=True)
    
    for i, entry in enumerate(leaderboard, 1):
        entry["weekly_position"] = i
    
    return leaderboard

def process_all_gameweeks():
    """Process all gameweek data and return structured data for the web interface."""
    directory = "leaderboard-data"
    gameweek_data = load_json_files(directory)
    
    if not gameweek_data:
        return {"leaderboards": {}, "transfers": {}, "stages": {}}
    
    # Sort gameweeks to ensure proper order
    sorted_gameweeks = sorted(gameweek_data.items(), key=lambda x: x[0])
    previous_gw_data = None
    
    leaderboards = {}
    transfers = {}
    stages = {}
    
    for i, (gameweek_file, rosters) in enumerate(sorted_gameweeks):
        gameweek_name = gameweek_file.split('.')[0]
        
        # Determine stage (you can modify this logic based on your naming convention)
        if 'playoff' in gameweek_name.lower():
            stage = "Stage 2 Playoffs"
        else:
            stage = "Stage 2 Regular Season"
        
        if stage not in stages:
            stages[stage] = []
        stages[stage].append(gameweek_name)
        
        # Calculate transfers if we have previous gameweek data
        transfer_data = None
        existing_users = 0
        new_users = 0
        if previous_gw_data is not None:
            transfer_data, existing_users = calculate_transfers(rosters, previous_gw_data)
            new_users = len(rosters) - existing_users
        else:
            new_users = len(rosters)
        
        # Analyze player frequency for transfers
        player_analysis = analyze_player_frequency(rosters, transfer_data, existing_users)
        transfers[gameweek_name] = player_analysis
        
        # Generate leaderboard
        leaderboard = generate_leaderboard(rosters, previous_gw_data, gameweek_name)
        
        # Calculate average points
        total_points = sum(entry["weekly_points"] for entry in leaderboard)
        average_points = round(total_points / len(leaderboard), 1) if leaderboard else 0
        
        leaderboards[gameweek_name] = {
            "data": leaderboard,
            "total_participants": len(leaderboard),
            "new_users": new_users,
            "existing_users": existing_users,
            "average_points": average_points
        }
        
        # Store current gameweek data for next iteration
        previous_gw_data = rosters
    
    return {
        "leaderboards": leaderboards,
        "transfers": transfers,
        "stages": stages
    }

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/leaderboards')
def leaderboards():
    return render_template('leaderboards.html')

@app.route('/transfers')
def transfers():
    return render_template('transfers.html')

@app.route('/api/leaderboard-data')
def get_leaderboard_data():
    """API endpoint to get all processed leaderboard data."""
    try:
        data = process_all_gameweeks()
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
    os.makedirs('templates', exist_ok=True)
    os.makedirs('leaderboard-data', exist_ok=True)
    app.run(debug=True)