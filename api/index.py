from flask import Flask, request, render_template, jsonify, send_from_directory
from dotenv import load_dotenv
import os
import requests
from table2ascii import table2ascii as t2a, PresetStyle
from collections import defaultdict
import json
from typing import Dict, List, Set, Tuple
from datetime import datetime
import hashlib

# Load environment variables
load_dotenv()
API_KEY = os.getenv("API_KEY")

# Initialize Flask app
app = Flask(__name__, template_folder='../templates', static_folder='../static')

# ============================================================================
# DECORATORS AND UTILITIES
# ============================================================================

def cache_control(max_age=3600, s_maxage=None):
    """Decorator to add cache control headers to responses."""
    def decorator(f):
        def decorated_function(*args, **kwargs):
            response = f(*args, **kwargs)
            if hasattr(response, 'headers'):
                if s_maxage:
                    response.headers['Cache-Control'] = f'public, max-age={max_age}, s-maxage={s_maxage}'
                else:
                    response.headers['Cache-Control'] = f'public, max-age={max_age}'
                response.headers['Vary'] = 'Accept-Encoding'
            return response
        decorated_function.__name__ = f.__name__
        return decorated_function
    return decorator

def get_leaderboard_path():
    """Get the correct path for leaderboard data directory."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(current_dir), 'leaderboard-data')

# ============================================================================
# FACEIT API FUNCTIONS
# ============================================================================

def fetch_data_from_api(endpoint, api_key):
    """Fetch data from FACEIT API."""
    url = f"https://open.faceit.com/data/v4/{endpoint}"
    headers = {"accept": "application/json", "Authorization": f"Bearer {api_key}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def get_match_data(match_id, api_key):
    """Get match data from FACEIT API."""
    return fetch_data_from_api(f"matches/{match_id}", api_key)

def get_match_stats(match_id, api_key):
    """Get match statistics from FACEIT API."""
    return fetch_data_from_api(f"matches/{match_id}/stats", api_key)

def get_player_details(player_id, api_key):
    """Get player details from FACEIT API."""
    return fetch_data_from_api(f"players/{player_id}", api_key)

# ============================================================================
# MATCH PROCESSING FUNCTIONS
# ============================================================================

def get_team_name(faction_id, match_data):
    """Extract team name from match data by faction ID."""
    if not faction_id or faction_id == "":
        return "Draw"
    
    return next(
        (team["name"] for team in match_data["teams"].values() if team["faction_id"] == faction_id),
        "Failed to get Team Name"
    )

def get_map_name(map_id, match_data):
    """Extract map name from match data by map ID."""
    return next(
        (map_entity["name"] for map_entity in match_data["voting"]["map"]["entities"] 
         if map_entity["game_map_id"] == map_id),
        "Failed to get Map Name"
    )

def get_player_name(player_id, match_data, api_key):
    """Get player name from match data or API."""
    for team in match_data["teams"].values():
        for player in team["roster"]:
            if player["player_id"] == player_id:
                return player["game_player_name"]
    return get_player_details(player_id, api_key)["games"]["ow2"]["game_player_name"]

def get_team_stats(team_index, map_index, match_stats, match_data, api_key):
    """Get team statistics for a specific map."""
    role_order = {"Tank": 0, "Damage": 1, "Support": 2}
    players = match_stats["rounds"][map_index]["teams"][team_index]["players"]
    
    return sorted([
        {
            "name": get_player_name(player_data["player_id"], match_data, api_key),
            "player_stats": player_data["player_stats"],
        }
        for player_data in players
    ], key=lambda x: (role_order.get(x["player_stats"]["Role"], 3), x["name"]))

def calculate_score(eliminations, deaths, damage, healing):
    """Calculate fantasy score based on player stats."""
    elimination_points = eliminations // 3
    death_points = deaths * -1
    damage_points = (damage // 2000) * 0.5
    healing_points = (healing // 2000) * 0.5
    return elimination_points + death_points + damage_points + healing_points

def calculate_player_scores_for_each_map(match_data, match_stats, api_key):
    """Calculate scores for each player on each map."""
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
        
        for team_index in range(2):
            team_name = get_team_name(round_data["teams"][team_index]["team_id"], match_data)
            team = {"name": team_name, "players": []}
            
            team_stats = get_team_stats(team_index, i, match_stats, match_data, api_key)
            for player in team_stats:
                player_stats = player["player_stats"]
                score = calculate_score(
                    int(player_stats["Eliminations"]),
                    int(player_stats["Deaths"]),
                    int(player_stats["Damage Dealt"]),
                    int(player_stats["Healing Done"])
                )
                
                team["players"].append({
                    "role": player_stats["Role"],
                    "name": player["name"],
                    "eliminations": player_stats["Eliminations"],
                    "deaths": player_stats["Deaths"],
                    "damage": player_stats["Damage Dealt"],
                    "healing": player_stats["Healing Done"],
                    "score": score
                })
            
            result["teams"].append(team)
        match_summary.append(result)
    
    return match_summary

def calculate_player_scores_for_match(match_data, match_stats, api_key):
    """Calculate total scores for each player across all maps."""
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
    """Generate ASCII tables for each map in the match."""
    output = []
    
    for match_round in match_summary:
        round_info = f"Map {match_round['match_round'] + 1}: {match_round['mode']} - {match_round['map']}"
        score_summary = f"{match_round['teams'][0]['name']} {match_round['map_score']} {match_round['teams'][1]['name']}"
        
        output.extend([round_info, score_summary, ""])

        if side_by_side and len(match_round['teams']) == 2:
            # Generate side-by-side tables
            team_tables = []
            for team in match_round['teams']:
                headers = [team['name'], "Eliminations", "Deaths", "Damage", "Healing", "Score"]
                rows = [
                    [player["name"], player["eliminations"], player["deaths"], 
                     player["damage"], player["healing"], f"{player['score']:.1f}"]
                    for player in team["players"]
                ]
                team_tables.append(t2a(header=headers, body=rows, style=PresetStyle.double))
            
            # Combine tables side by side
            table1_lines = team_tables[0].split('\n')
            table2_lines = team_tables[1].split('\n')
            max_lines = max(len(table1_lines), len(table2_lines))
            
            combined_table = []
            for i in range(max_lines):
                line1 = table1_lines[i] if i < len(table1_lines) else " " * len(table1_lines[0])
                line2 = table2_lines[i] if i < len(table2_lines) else " " * len(table2_lines[0])
                combined_table.append(f"{line1}    {line2}")
            
            output.extend(['\n'.join(combined_table), ""])
        else:
            # Generate separate tables
            for team in match_round['teams']:
                headers = [team['name'], "Eliminations", "Deaths", "Damage", "Healing", "Score"]
                rows = [
                    [player["name"], player["eliminations"], player["deaths"],
                     player["damage"], player["healing"], f"{player['score']:.1f}"]
                    for player in team["players"]
                ]
                table = t2a(header=headers, body=rows, style=PresetStyle.double)
                output.extend([table, ""])
    
    return "\n".join(output)

def generate_ascii_table_for_match(scores, side_by_side=False):
    """Generate ASCII table for overall match scores."""
    output = []
    
    if side_by_side and len(scores) == 2:
        # Side-by-side overall scores
        team1_name = list(scores[0].keys())[0]
        team1_players = scores[0][team1_name]
        team2_name = list(scores[1].keys())[0]
        team2_players = scores[1][team2_name]
        
        table1_data = [[team1_name, "Score"]] + [[player, f"{score:.1f}"] for player, score in team1_players.items()]
        table2_data = [[team2_name, "Score"]] + [[player, f"{score:.1f}"] for player, score in team2_players.items()]
        
        table1 = t2a(header=table1_data[0], body=table1_data[1:], style=PresetStyle.double)
        table2 = t2a(header=table2_data[0], body=table2_data[1:], style=PresetStyle.double)
        
        table1_lines = table1.split('\n')
        table2_lines = table2.split('\n')
        max_lines = max(len(table1_lines), len(table2_lines))
        
        combined_table = []
        for i in range(max_lines):
            line1 = table1_lines[i] if i < len(table1_lines) else " " * len(table1_lines[0])
            line2 = table2_lines[i] if i < len(table2_lines) else " " * len(table2_lines[0])
            combined_table.append(f"{line1}    {line2}")
        
        output.extend(['\n'.join(combined_table), ""])
    else:
        # Separate tables for each team
        for team_scores in scores:
            for team, players in team_scores.items():
                table_data = [[team, "Score"]] + [[player, f"{score:.1f}"] for player, score in players.items()]
                table = t2a(header=table_data[0], body=table_data[1:], style=PresetStyle.double)
                output.extend([table, ""])
    
    return "\n".join(output)

def generate_match_result(match_data):
    """Generate match result summary."""
    team1 = match_data["teams"]["faction1"]["name"]
    team1_score = match_data["results"]["score"]["faction1"]
    team2 = match_data["teams"]["faction2"]["name"]
    team2_score = match_data["results"]["score"]["faction2"]
    competition_name = match_data["competition_name"]
    
    return f"{competition_name}\n{team1} {team1_score} - {team2} {team2_score}\n\n"

def process_match(match_url, side_by_side=False):
    """Process a FACEIT match URL and generate fantasy report."""
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

# ============================================================================
# LEADERBOARD DATA PROCESSING FUNCTIONS
# ============================================================================

def load_json_files(directory: str) -> Dict[str, List[Dict]]:
    """Load all JSON files from a directory."""
    gameweek_data = {}
    
    try:
        if not os.path.exists(directory):
            print(f"Directory '{directory}' not found")
            return gameweek_data
            
        for filename in os.listdir(directory):
            if filename.endswith('.json'):
                file_path = os.path.join(directory, filename)
                try:
                    with open(file_path, 'r') as file:
                        data = json.load(file)
                        gameweek_name = filename.replace('.json', '')
                        gameweek_data[gameweek_name] = data
                        print(f"Loaded {len(data) if isinstance(data, list) else 'non-list'} entries from {filename}")
                except json.JSONDecodeError as e:
                    print(f"JSON decode error in {filename}: {str(e)}")
                except Exception as e:
                    print(f"Error loading {filename}: {str(e)}")
    except Exception as e:
        print(f"Error accessing directory '{directory}': {str(e)}")
    
    return gameweek_data

def safe_get_roster_field(roster: Dict, field: str, default: str = "Unknown") -> str:
    """Safely get a field from roster with error handling."""
    try:
        if roster is None:
            return default
        value = roster.get(field, default)
        return value if value is not None else default
    except Exception:
        return default

def get_user_roster(roster: Dict) -> Set[str]:
    """Extract all players from a user's roster."""
    if roster is None:
        return set()
    
    players = set()
    try:
        players.add(safe_get_roster_field(roster, "tank"))
        players.add(safe_get_roster_field(roster, "dpsOne"))
        players.add(safe_get_roster_field(roster, "dpsTwo"))
        players.add(safe_get_roster_field(roster, "supportOne"))
        players.add(safe_get_roster_field(roster, "supportTwo"))
        players.discard("Unknown")  # Remove "Unknown" if it was added
    except Exception as e:
        print(f"Error processing roster: {str(e)}")
    
    return players

def calculate_transfers(current_gw_data: List[Dict], previous_gw_data: List[Dict]) -> Tuple[Dict[str, Dict], int]:
    """Calculate transfer in/out data by comparing gameweeks."""
    if not current_gw_data or not previous_gw_data:
        return {}, 0
    
    try:
        previous_rosters = {
            roster["username"]: roster 
            for roster in previous_gw_data 
            if roster and "username" in roster
        }
        
        transfer_stats = {}
        existing_users = 0
        
        for current_roster in current_gw_data:
            if not current_roster or "username" not in current_roster:
                continue
                
            username = current_roster["username"]
            
            if username in previous_rosters:
                existing_users += 1
                previous_roster = previous_rosters[username]
                
                current_players = get_user_roster(current_roster)
                previous_players = get_user_roster(previous_roster)
                
                transferred_in = current_players - previous_players
                transferred_out = previous_players - current_players
                
                for player in transferred_in:
                    if player and player != "Unknown":
                        if player not in transfer_stats:
                            transfer_stats[player] = {"transferred_in": 0, "transferred_out": 0}
                        transfer_stats[player]["transferred_in"] += 1
                    
                for player in transferred_out:
                    if player and player != "Unknown":
                        if player not in transfer_stats:
                            transfer_stats[player] = {"transferred_in": 0, "transferred_out": 0}
                        transfer_stats[player]["transferred_out"] += 1
        
        return transfer_stats, existing_users
    except Exception as e:
        print(f"Error calculating transfers: {str(e)}")
        return {}, 0

def analyze_player_frequency(rosters: List[Dict], transfer_data: Dict = None, existing_users: int = 0) -> List[Dict]:
    """Analyze player selection frequency in rosters."""
    if not rosters:
        return []
    
    try:
        player_stats = {}
        total_teams = len(rosters)
        
        for roster in rosters:
            if not roster:
                continue
                
            # Process each role
            role_mappings = {
                "tank": ["tank"],
                "dps": ["dpsOne", "dpsTwo"],
                "support": ["supportOne", "supportTwo"]
            }
            
            for role, fields in role_mappings.items():
                for field in fields:
                    player = safe_get_roster_field(roster, field)
                    if player and player != "Unknown":
                        if player not in player_stats:
                            player_stats[player] = {"role": role, "count": 0}
                        player_stats[player]["count"] += 1
        
        # Build result list
        result = []
        for player_name, stats in player_stats.items():
            if not player_name or player_name == "Unknown":
                continue
                
            percentage = (stats["count"] / total_teams) * 100 if total_teams > 0 else 0
            
            player_data = {
                "name": player_name,
                "role": stats["role"],
                "count": stats["count"],
                "percentage": round(percentage, 1)
            }
            
            # Add transfer data if available
            if transfer_data and player_name in transfer_data:
                transfers = transfer_data[player_name]
                player_data.update({
                    "transferred_in": transfers["transferred_in"],
                    "transferred_out": transfers["transferred_out"],
                    "net_transfers": transfers["transferred_in"] - transfers["transferred_out"]
                })
                
                if existing_users > 0:
                    player_data["transfer_in_pct"] = round((transfers['transferred_in'] / existing_users) * 100, 1)
                    player_data["transfer_out_pct"] = round((transfers['transferred_out'] / existing_users) * 100, 1)
                else:
                    player_data["transfer_in_pct"] = 0.0
                    player_data["transfer_out_pct"] = 0.0
            elif transfer_data is not None:
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
        
    except Exception as e:
        print(f"Error analyzing player frequency: {str(e)}")
        return []

def generate_leaderboard(current_gw_data: List[Dict], previous_gw_data: List[Dict] = None, gameweek_name: str = "") -> List[Dict]:
    """Generate leaderboard with weekly points, overall positions, and position changes."""
    if not current_gw_data:
        return []
    
    try:
        leaderboard = []
        previous_rosters = {}
        previous_total_positions = {}
        
        # Process previous gameweek data if available
        if previous_gw_data:
            previous_rosters = {
                roster["username"]: roster 
                for roster in previous_gw_data 
                if roster and "username" in roster
            }
            
            valid_previous = [roster for roster in previous_gw_data if roster and "score" in roster]
            previous_total_leaderboard = sorted(valid_previous, key=lambda x: float(x.get("score", 0)), reverse=True)
            previous_total_positions = {roster["username"]: i + 1 for i, roster in enumerate(previous_total_leaderboard)}
        
        # Process current gameweek data
        valid_current = [roster for roster in current_gw_data if roster and "score" in roster and "username" in roster]
        current_total_leaderboard = sorted(valid_current, key=lambda x: float(x.get("score", 0)), reverse=True)
        current_total_positions = {roster["username"]: i + 1 for i, roster in enumerate(current_total_leaderboard)}
        
        for roster in valid_current:
            username = roster["username"]
            current_total_score = float(roster.get("score", 0))
            
            # Calculate weekly points
            weekly_points = current_total_score
            if username in previous_rosters:
                previous_total_score = float(previous_rosters[username].get("score", 0))
                weekly_points = current_total_score - previous_total_score
            
            # Build leaderboard entry
            leaderboard_entry = {
                "username": username,
                "weekly_points": round(weekly_points, 1),
                "current_total_score": round(current_total_score, 1),
                "current_overall_position": current_total_positions[username],
                "transferred_in": [],
                "transferred_out": [],
                "tank": safe_get_roster_field(roster, "tank"),
                "dpsOne": safe_get_roster_field(roster, "dpsOne"),
                "dpsTwo": safe_get_roster_field(roster, "dpsTwo"),
                "supportOne": safe_get_roster_field(roster, "supportOne"),
                "supportTwo": safe_get_roster_field(roster, "supportTwo")
            }
            
            # Add previous gameweek data and transfers
            if username in previous_rosters:
                previous_total_score = float(previous_rosters[username].get("score", 0))
                previous_overall_position = previous_total_positions.get(username)
                
                leaderboard_entry.update({
                    "previous_total_score": round(previous_total_score, 1),
                    "previous_overall_position": previous_overall_position,
                    "overall_position_change": (previous_overall_position - leaderboard_entry["current_overall_position"]) if previous_overall_position else 0
                })
                
                # Calculate transfers
                current_players = get_user_roster(roster)
                previous_players = get_user_roster(previous_rosters[username])
                
                leaderboard_entry["transferred_in"] = list(current_players - previous_players)
                leaderboard_entry["transferred_out"] = list(previous_players - current_players)
            else:
                leaderboard_entry.update({
                    "previous_total_score": None,
                    "previous_overall_position": None,
                    "overall_position_change": 0
                })
            
            leaderboard.append(leaderboard_entry)
        
        # Sort by weekly points and assign weekly positions
        leaderboard.sort(key=lambda x: x["weekly_points"], reverse=True)
        for i, entry in enumerate(leaderboard, 1):
            entry["weekly_position"] = i
        
        return leaderboard
    except Exception as e:
        print(f"Error generating leaderboard: {str(e)}")
        return []

def process_all_gameweeks():
    """Process all gameweek data and return structured data for the web interface."""
    try:
        directory = get_leaderboard_path()
        gameweek_data = load_json_files(directory)
        
        print(f"Successfully loaded {len(gameweek_data)} gameweeks: {list(gameweek_data.keys())}")
        
        if not gameweek_data:
            return {"leaderboards": {}, "transfers": {}, "stages": {}}
        
        # Sort gameweeks properly
        def gameweek_sort_key(gw_name):
            if 'playoff' in gw_name.lower():
                num = ''.join(filter(str.isdigit, gw_name))
                return (1, int(num) if num else 0)  # Playoffs after regular season
            else:
                num = ''.join(filter(str.isdigit, gw_name))
                return (0, int(num) if num else 0)  # Regular season first
        
        sorted_gameweeks = sorted(gameweek_data.items(), key=lambda x: gameweek_sort_key(x[0]))
        previous_gw_data = None
        
        leaderboards = {}
        transfers = {}
        stages = {}
        
        for gameweek_name, rosters in sorted_gameweeks:
            print(f"Processing {gameweek_name} with {len(rosters) if isinstance(rosters, list) else 'non-list'} entries")
            
            if not isinstance(rosters, list) or not rosters:
                print(f"Warning: Skipping {gameweek_name} - invalid data")
                continue
            
            # Filter out None entries
            rosters = [r for r in rosters if r is not None]
            if not rosters:
                print(f"Warning: No valid rosters found in {gameweek_name}")
                continue
            
            # Determine stage
            stage = "Stage 2 Playoffs" if 'playoff' in gameweek_name.lower() else "Stage 2 Regular Season"
            if stage not in stages:
                stages[stage] = []
            stages[stage].append(gameweek_name)
            
            # Calculate transfers
            transfer_data, existing_users = calculate_transfers(rosters, previous_gw_data) if previous_gw_data else ({}, 0)
            new_users = len(rosters) - existing_users
            
            # Analyze player frequency for transfers
            player_analysis = analyze_player_frequency(rosters, transfer_data, existing_users)
            transfers[gameweek_name] = player_analysis
            
            # Generate leaderboard
            leaderboard = generate_leaderboard(rosters, previous_gw_data, gameweek_name)
            
            # Calculate statistics
            total_points = sum(entry["weekly_points"] for entry in leaderboard)
            average_points = round(total_points / len(leaderboard), 1) if leaderboard else 0
            
            leaderboards[gameweek_name] = {
                "data": leaderboard,
                "total_participants": len(leaderboard),
                "new_users": new_users,
                "existing_users": existing_users,
                "average_points": average_points
            }
            
            previous_gw_data = rosters
        
        result = {
            "leaderboards": leaderboards,
            "transfers": transfers,
            "stages": stages
        }
        
        print(f"Successfully processed {len(leaderboards)} gameweeks")
        return result
        
    except Exception as e:
        print(f"Error in process_all_gameweeks: {str(e)}")
        return {"leaderboards": {}, "transfers": {}, "stages": {}, "error": str(e)}

# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route('/')
@cache_control(max_age=300, s_maxage=300)
def index():
    """Serve the main page."""
    try:
        return render_template('index.html')
    except Exception as e:
        return f"Error loading page: {str(e)}", 500

@app.route('/static/<path:filename>')
@cache_control(max_age=31536000)
def static_files(filename):
    """Serve static files."""
    try:
        return send_from_directory('../static', filename)
    except Exception as e:
        return f"Static file not found: {str(e)}", 404

@app.route('/api/leaderboard-data')
@cache_control(max_age=300, s_maxage=300)
def get_leaderboard_data():
    """API endpoint to get all processed leaderboard data."""
    try:
        data = process_all_gameweeks()
        response = jsonify(data)
        
        # Add ETag for conditional requests
        content_hash = hashlib.md5(json.dumps(data, sort_keys=True).encode()).hexdigest()
        response.headers['ETag'] = content_hash
        
        # Check if client has cached version
        if request.headers.get('If-None-Match') == content_hash:
            return '', 304
            
        return response
    except Exception as e:
        error_response = {
            "error": str(e),
            "error_type": type(e).__name__,
            "leaderboard_path": get_leaderboard_path(),
            "path_exists": os.path.exists(get_leaderboard_path())
        }
        print(f"API Error: {error_response}")
        return jsonify(error_response), 500

@app.route('/process', methods=['POST'])
@cache_control(max_age=3600, s_maxage=3600)
def process():
    """Process FACEIT match URL and return fantasy report."""
    try:
        match_url = request.form.get('match_url')
        side_by_side = request.form.get('side_by_side') == 'true'
        
        if not match_url:
            return jsonify({"error": "No match URL provided"}), 400
        
        # Create cache key
        cache_key = hashlib.md5(f"{match_url}_{side_by_side}".encode()).hexdigest()
        
        # Check if client has cached version
        if request.headers.get('If-None-Match') == cache_key:
            return '', 304
        
        report = process_match(match_url, side_by_side)
        response = jsonify({"report": report})
        response.headers['ETag'] = cache_key
        
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy", 
        "timestamp": datetime.utcnow().isoformat(),
        "leaderboard_path": get_leaderboard_path(),
        "leaderboard_exists": os.path.exists(get_leaderboard_path())
    }), 200

# ============================================================================
# LOCAL DEVELOPMENT
# ============================================================================

if __name__ == '__main__':
    app.run(debug=True)