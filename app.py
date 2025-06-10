from flask import Flask, request, render_template, jsonify, send_from_directory
from dotenv import load_dotenv
import os
import requests
from table2ascii import table2ascii as t2a, PresetStyle
from collections import defaultdict
import json
from typing import Dict, List, Set, Tuple
from datetime import datetime, timedelta
import hashlib

load_dotenv()
API_KEY = os.getenv("API_KEY")

app = Flask(__name__)

# Cache control decorator
def cache_control(max_age=3600, s_maxage=None):
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

# [Keep all your existing helper functions here - fetch_data_from_api, get_match_data, etc.]
# ... (all your existing functions remain the same)

# Routes
@app.route('/')
@cache_control(max_age=300, s_maxage=300)
def index():
    try:
        response = app.response_class(
            response=render_template('index.html'),
            status=200,
            mimetype='text/html'
        )
        return response
    except Exception as e:
        return f"Error loading page: {str(e)}", 500

@app.route('/static/<path:filename>')
@cache_control(max_age=31536000)
def static_files(filename):
    try:
        return send_from_directory('static', filename)
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
        return jsonify({"error": str(e)}), 500

@app.route('/process', methods=['POST'])
@cache_control(max_age=3600, s_maxage=3600)
def process():
    try:
        match_url = request.form.get('match_url')
        side_by_side = request.form.get('side_by_side') == 'true'
        
        if not match_url:
            return jsonify({"error": "No match URL provided"}), 400
        
        # Create cache key based on match URL and settings
        cache_key = hashlib.md5(f"{match_url}_{side_by_side}".encode()).hexdigest()
        
        report = process_match(match_url, side_by_side)
        response = jsonify({"report": report})
        
        # Add cache headers
        response.headers['ETag'] = cache_key
        
        # Check if client has cached version
        if request.headers.get('If-None-Match') == cache_key:
            return '', 304
            
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()}), 200

# This is crucial for Vercel to detect the app
app = app

# For local development
if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    os.makedirs('leaderboard-data', exist_ok=True)
    os.makedirs('static', exist_ok=True)
    app.run(debug=True)