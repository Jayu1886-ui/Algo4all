import json
from flask import Blueprint, jsonify
from flask_login import login_required, current_user
from app import cache

# Create the API blueprint
api = Blueprint('api', __name__)

@api.route('/get-dashboard-state')
@login_required
def get_dashboard_state():
    """
    API endpoint for the frontend to fetch the most recent market state
    for the currently logged-in user from the Redis cache.
    """
    user_id = current_user.id
    cache_key = f"market_state_{user_id}"
    
    cached_data_json = cache.get(cache_key)
    
    if cached_data_json:
        market_data = json.loads(cached_data_json)
        return jsonify(market_data)
    else:
        # Return a default "empty" state to prevent frontend errors
        return jsonify({
            "overall_trend": "Calculating...",
            "indices": {}, "atm_call": {}, "atm_put": {}
        })