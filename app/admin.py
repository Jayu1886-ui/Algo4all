from flask import (
    Blueprint, render_template, request, flash, redirect,
    url_for, session, jsonify
)
from werkzeug.security import check_password_hash
from .models import Admin, User, AppSettings
from . import db
from datetime import datetime, timezone
from functools import wraps

admin = Blueprint('admin', __name__)

# --- Utility Functions ---

def is_admin_logged_in():
    """Checks if an admin is currently logged in via session."""
    return session.get('admin_logged_in') is True

def admin_required(f):
    """Decorator to protect routes that require admin login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not is_admin_logged_in():
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        return f(*args, **kwargs)
    return decorated_function

# --- Auth Routes ---

@admin.route('/login', methods=['GET', 'POST'])
def login():
    """Handles admin login."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        admin_user = Admin.query.filter_by(username=username).first()
        if admin_user and check_password_hash(admin_user.password, password):
            session['admin_logged_in'] = True
            flash('Login successful.', 'success')
            return redirect(url_for('admin.dashboard'))

        flash('Invalid username or password.', 'danger')

    return render_template('admin/admin_login.html')


@admin.route('/logout')
def logout():
    """Logs the admin out by clearing the session flag."""
    session.pop('admin_logged_in', None)
    flash('You have been logged out from the admin panel.', 'success')
    return redirect(url_for('admin.login'))

# --- Dashboard ---

@admin.route('/dashboard')
def dashboard():
    """
    Displays the main admin dashboard.
    This function now includes logic to automatically disable users
    whose 7-day trial period has expired.
    """
    if not is_admin_logged_in():
        return redirect(url_for('admin.login'))
    
    # Get the global app setting (no change here)
    current_setting = AppSettings.query.filter_by(setting_name='global_app_status').first()
    
    # Get all users to process them
    all_users = User.query.all()
    
    # This will be the final list of user data passed to the template
    users_data_for_template = []
    
    # The current time, aware of its timezone (crucial for accurate comparisons)
    now_utc = datetime.now(timezone.utc)

    for user in all_users:
        if user.name == "JAYENDRASINH KISHORSINH DODIYA":
            users_data_for_template.append({
                'id': user.id,
                'name': user.name,
                'mobile_number': user.mobile_number,
                'registration_date': user.registration_date.strftime('%Y-%m-%d %H:%M:%S') if user.registration_date else 'N/A',
                'days_since_registration': 0,
                'is_trading_on': True  # Always ON for admin
            })
        if user.registration_date:
            registration_date_utc = user.registration_date.replace(tzinfo=timezone.utc)
            days_since_registration = (now_utc - registration_date_utc).days
        else:
            days_since_registration = 0

        if days_since_registration > 7 and user.is_trading_on:
            user.is_trading_on = False
            db.session.add(user)
            print(f"ADMIN DASHBOARD: Automatically disabled trading for user {user.name} (Trial Expired).")

        users_data_for_template.append({
            'id': user.id,
            'name': user.name,
            'mobile_number': user.mobile_number,
            'registration_date': user.registration_date.strftime('%Y-%m-%d %H:%M:%S') if user.registration_date else 'N/A',
            'days_since_registration': days_since_registration,
            'is_trading_on': user.is_trading_on
        })
    
    # After the loop finishes, commit any changes made (like disabling expired users)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error committing auto-disable changes: {e}")
        flash("There was an error updating user statuses.", "danger")

    total_users_count = len(all_users)

    return render_template(
        'admin/admin_dashboard.html', 
        current_setting=current_setting, 
        users_data=users_data_for_template, # Use the new, processed data
        total_users=total_users_count
    )
    

# --- API-like Routes for Dashboard Interactivity ---

@admin.route('/toggle_app', methods=['POST'])
@admin_required
def toggle_app():
    """Toggles the global application ON/OFF status."""
    try:
        setting = AppSettings.query.filter_by(setting_name='global_app_status').first()
        if setting:
            setting.is_on = not setting.is_on
            db.session.commit()
            return jsonify({'success': True, 'new_status': setting.is_on})
        return jsonify({'success': False, 'error': 'Setting not found'}), 404
    except Exception as e:
        admin.logger.exception("Error toggling global app status")
        return jsonify({'success': False, 'error': 'Server error'}), 500

@admin.route('/toggle_user/<int:user_id>', methods=['POST'])
@admin_required
def toggle_user(user_id):
    """Toggles an individual user's 'is_active' status."""
    try:
        user = User.query.get(user_id)
        if user:
            user.is_active = not user.is_active
            db.session.commit()
            return jsonify({'success': True, 'new_status': user.is_active})
        return jsonify({'success': False, 'error': 'User not found'}), 404
    except Exception as e:
        admin.logger.exception(f"Error toggling user {user_id} status")
        return jsonify({'success': False, 'error': 'Server error'}), 500