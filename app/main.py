# app/main.py

import json
import requests
import certifi
from functools import wraps
from flask import Blueprint, render_template, jsonify, flash, request, redirect, url_for, current_app
from flask_login import login_required, current_user
from flask_socketio import join_room, leave_room

from extensions import cache, db, socketio
from .models import User

main = Blueprint('main', __name__)


# ============================================================
# 1️⃣ Gatekeeper Decorator (Upstox Token Validator)
# ============================================================

def upstox_token_required(view_func):
    """Ensures current user's Upstox token is valid."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login"))

        token = current_user.access_token
        if not token:
            flash("Missing Upstox access token. Please log in again.", "error")
            return redirect(url_for("auth.login"))

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

        try:
            response = requests.get(
                "https://api.upstox.com/v2/user/profile",
                headers=headers,
                timeout=5,
                verify=certifi.where()
            )
            if response.status_code != 200:
                flash("Your Upstox session has expired. Please log in again.", "error")
                return redirect(url_for("auth.login"))

        except requests.RequestException:
            flash("Unable to verify Upstox session. Please log in again.", "error")
            return redirect(url_for("auth.login"))

        return view_func(*args, **kwargs)
    return wrapper


# ============================================================
# 2️⃣ Helper Function
# ============================================================

def get_upstox_headers():
    token = current_user.access_token
    if not token:
        return None
    return {
        'Accept': 'application/json',
        'Api-Version': '2.0',
        'Authorization': f'Bearer {token}'
    }


# ============================================================
# 3️⃣ Public Routes
# ============================================================

@main.route('/')
def index():
    return render_template('index.html')


@main.route('/disclaimer')
def disclaimer():
    return render_template('disclaimer.html')


# ============================================================
# 4️⃣ Protected Routes
# ============================================================

@main.route('/dashboard')
@login_required
@upstox_token_required
def dashboard():
    return render_template('main/dashboard.html')


@main.route('/api/get-dashboard-state')
@login_required
@upstox_token_required
def get_dashboard_state_api():
    """Returns cached market state or default response."""
    cache_key = f"market_state_{current_user.id}"
    cached = cache.get(cache_key)

    if not cached:
        return jsonify({
            "overall_trend": "Processing...",
            "indices": {},
            "atm_call": {},
            "atm_put": {}
        })

    return jsonify(json.loads(cached))


@main.route('/orders')
@login_required
@upstox_token_required
def orders():
    headers = get_upstox_headers()
    if not headers:
        flash('Invalid Upstox connection. Please log in again.', 'error')
        return redirect(url_for('auth.login'))

    orders_data = []
    try:
        res = requests.get(
            "https://api.upstox.com/v2/order/retrieve-all",
            headers=headers,
            timeout=10,
            verify=certifi.where()
        )
        res.raise_for_status()
        orders_data = res.json().get('data', [])
    except requests.RequestException as e:
        flash(f'Could not fetch orders. Error: {e}', 'error')

    return render_template('main/orders.html', orders=orders_data)


@main.route('/positions')
@login_required
@upstox_token_required
def positions():
    headers = get_upstox_headers()
    if not headers:
        flash('Invalid Upstox connection. Please log in again.', 'error')
        return redirect(url_for('auth.login'))

    funds, live_pnl, open_positions, closed_positions = 0.0, 0.0, [], []

    try:
        # Funds
        res_funds = requests.get(
            "https://api.upstox.com/v2/user/get-funds-and-margin?segment=SEC",
            headers=headers, timeout=10, verify=certifi.where()
        )
        res_funds.raise_for_status()
        equity = res_funds.json().get('data', {}).get('equity', {})
        funds = float(equity.get('available_margin', 0.0))

        # Open positions
        res_positions = requests.get(
            "https://api.upstox.com/v2/portfolio/short-term-positions",
            headers=headers, timeout=10, verify=certifi.where()
        )
        res_positions.raise_for_status()
        open_positions = res_positions.json().get('data', [])
        live_pnl = sum(float(p.get('pnl', 0.0)) for p in open_positions)

    except requests.RequestException as e:
        flash(f'Could not fetch portfolio data. Error: {e}', 'error')
    except Exception as e:
        current_app.logger.error(f"Unexpected error: {e}")
        flash('Unexpected error while fetching portfolio.', 'error')

    return render_template(
        'main/positions.html',
        funds=funds,
        live_pnl=live_pnl,
        open_positions=open_positions,
        closed_positions=closed_positions
    )


@main.route('/square-off', methods=['POST'])
@login_required
@upstox_token_required
def square_off():
    headers = get_upstox_headers()
    if not headers:
        flash('Invalid Upstox connection. Please log in again.', 'error')
        return redirect(url_for('auth.login'))

    try:
        res = requests.delete(
            "https://api.upstox.com/v2/order/positions/exit",
            headers=headers, timeout=15, verify=certifi.where()
        )
        res.raise_for_status()
        flash('Square-off request placed successfully!', 'success')
    except requests.RequestException as e:
        msg = str(e)
        if e.response is not None:
            try:
                msg = e.response.json().get('errors', [{}])[0].get('message', msg)
            except Exception:
                pass
        flash(f'Error placing square-off: {msg}', 'error')

    return redirect(url_for('main.positions'))


@main.route('/settings', methods=['GET', 'POST'])
@login_required
@upstox_token_required
def settings():
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'toggle_trading':
            current_user.is_trading_on = not current_user.is_trading_on
            flash(f"Trading set to {'ON' if current_user.is_trading_on else 'OFF'}.", 'success')
        elif action == 'update_quantity':
            try:
                qty = int(request.form.get('quantity'))
                if qty > 0 and qty % 75 == 0:
                    current_user.quantity = qty
                    flash(f"Quantity updated to {qty}.", 'success')
                else:
                    flash('Quantity must be a positive multiple of 75.', 'error')
            except (ValueError, TypeError):
                flash('Invalid input.', 'error')
        db.session.commit()
        return redirect(url_for('main.settings'))

    return render_template('main/settings.html')


# ============================================================
# 5️⃣ Socket.IO Events
# ============================================================

@socketio.on('connect')
def handle_connect_event():
    """Authenticate user and join their private room."""
    from flask_login import current_user
    if not current_user.is_authenticated:
        return False  # Reject connection silently

    join_room(str(current_user.id))
    print(f'✅ Client connected: {current_user.name} joined room "{current_user.id}"')


@socketio.on('disconnect')
def handle_disconnect_event():
    print(f'❌ Client disconnected: {request.sid}')
