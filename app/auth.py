# In app/auth.py (FINAL VERSION with token file saving)

from flask import Blueprint, redirect, url_for, session, request, flash, render_template, current_app
from flask_login import login_user, logout_user, login_required, current_user
import requests
import certifi
from sqlalchemy.exc import IntegrityError
from .models import User, AppSettings 
from . import db 
import os # <-- ADDED: Needed for file operations

auth = Blueprint('auth', __name__)


# --- NEW: User Registration Route ---
@auth.route('/register', methods=['GET', 'POST'])
def register():
    # This page is for new users to confirm their registration.
    
    if request.method == 'POST':
        mobile_number = request.form.get('mobile_number')
        if not mobile_number:
            flash('Mobile number is required for registration.', 'error')
            return redirect(url_for('auth.register'))

        # Check if user already exists
        existing_user = User.query.filter_by(mobile_number=mobile_number).first()
        if existing_user:
            flash('This mobile number is already registered. Please log in.', 'success')
            return redirect(url_for('auth.login'))

        # Create new user in the database
        try:
            new_user = User(mobile_number=mobile_number, name="New User") # Name is temporary
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful! Please log in to connect your Upstox account.', 'success')
            return redirect(url_for('auth.login'))
        except IntegrityError:
            db.session.rollback()
            flash('An error occurred. This mobile number might already be registered.', 'error')
            return redirect(url_for('auth.login'))

    # For GET request, show the registration form
    mobile_for_registration = session.pop('registration_mobile_number', None)
    return render_template('auth/register.html', mobile_number=mobile_for_registration)


# --- MODIFIED: Login Route with "Gatekeeper" Logic ---
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        user_api_key = request.form.get('api_key')
        user_api_secret = request.form.get('api_secret')
        mobile_number = request.form.get('mobile_number')

        if not all([user_api_key, user_api_secret, mobile_number]):
            flash('Your API Key, API Secret, and Mobile Number are required.', 'error')
            return redirect(url_for('auth.login'))

        # --- THIS IS THE NEW "GATEKEEPER" LOGIC ---
        registered_user = User.query.filter_by(mobile_number=mobile_number).first()

        if not registered_user:
            # If no user is found, redirect them to the registration page.
            flash('Welcome! Please confirm your mobile number to register.', 'info')
            session['registration_mobile_number'] = mobile_number
            return redirect(url_for('auth.register'))
        # --- END OF NEW LOGIC ---

        # If the user exists, proceed with the Upstox connection.
        session['temp_api_key'] = user_api_key
        session['temp_api_secret'] = user_api_secret
        session['temp_mobile_number'] = mobile_number

        redirect_uri = current_app.config['UPSTOX_REDIRECT_URI']
        dialog_url = (f"https://api.upstox.com/v2/login/authorization/dialog?"
                      f"response_type=code&client_id={user_api_key}&redirect_uri={redirect_uri}")
        return redirect(dialog_url)

    return render_template('auth/login.html')


# --- MODIFIED: Callback Route to handle linking the account ---
@auth.route('/callback')
def callback():
    code = request.args.get('code')
    user_api_key = session.pop('temp_api_key', None)
    user_api_secret = session.pop('temp_api_secret', None)
    mobile_number = session.pop('temp_mobile_number', None)

    if not all([code, user_api_key, user_api_secret, mobile_number]):
        flash('Authorization failed or session expired. Please log in again.', 'error')
        return redirect(url_for('auth.login'))

    try:
        data = {'code': code, 'client_id': user_api_key, 'client_secret': user_api_secret,
                'redirect_uri': current_app.config['UPSTOX_REDIRECT_URI'], 'grant_type': 'authorization_code'}
        
        token_response = requests.post('https://api.upstox.com/v2/login/authorization/token', data=data, verify=certifi.where(), timeout=15)
        token_response.raise_for_status()
        token_data = token_response.json()
        
        access_token = token_data.get('access_token')
        upstox_user_id = token_data.get('user_id')

        if not all([access_token, upstox_user_id]):
            flash("Authentication failed: Upstox did not return a valid token.", "error")
            return redirect(url_for('auth.login'))

        # --- User Linking Logic (Remains the same) ---
        user = User.query.filter_by(mobile_number=mobile_number).first()
        
        if not user:
            user = User.query.filter_by(upstox_user_id=upstox_user_id).first()
            if not user:
                user = User(mobile_number=mobile_number)
                db.session.add(user)

        # Update the user's record with all their Upstox details.
        user.upstox_user_id = upstox_user_id
        user.name = token_data.get('user_name', 'Unnamed User') 
        user.client_id = user_api_key
        user.client_secret = user_api_secret
        # The access_token setter encrypts the token before saving
        user.access_token = access_token
        
        
        # ----------------------------------------------------------------------
        # --- NEW CRITICAL LOGIC: OWNER/SYSTEM TOKEN UNIFICATION ---
        # ----------------------------------------------------------------------
        
        is_primary_owner = (user_api_key == current_app.config['OWNER_API_KEY'])

        if is_primary_owner:
            print(f"[{user.name}] DETECTED PRIMARY OWNER LOGIN. SAVING TOKEN TO APP SETTINGS AND LAUNCHING SYSTEM.")
            
            # 1. Save the token to the AppSettings table (setter encrypts it)
            owner_setting = AppSettings.query.filter_by(setting_name='owner_access_token').first()
            
            if not owner_setting:
                owner_setting = AppSettings(setting_name='owner_access_token')
                db.session.add(owner_setting)
                
            owner_setting.secret_value = access_token 
            
            # 2. CRITICAL: Save the PLAIN-TEXT token to a file for the streamer to use temporarily
            try:
                # This saves to the project root, accessible by the streamer process
                with open('access_token.txt', 'w') as f:
                    f.write(access_token)
                print("    -> ✅ Saved plain-text token to access_token.txt.")
            except Exception as file_e:
                print(f"    -> ❌ WARNING: Failed to save access_token.txt locally: {file_e}")
            
            

        # ----------------------------------------------------------------------
        
        db.session.commit()
        login_user(user, remember=False)
        flash("Successfully connected your Upstox account!", "success")
        
        return redirect(url_for('main.dashboard'))

    except requests.exceptions.RequestException as e:
        flash(f'A network error occurred during token exchange: {e}', 'error')
        return redirect(url_for('auth.login'))
    except Exception as e:
        db.session.rollback()
        flash(f'An unexpected error occurred: {e}', 'error')
        return redirect(url_for('auth.login'))
      


# --- UNCHANGED: Logout Route ---
@auth.route('/logout')
@login_required
def logout():
    # ... (this function remains exactly the same) ...
    try:
        headers = {'Accept': 'application/json', 'Api-Version': '2.0', 'Authorization': f'Bearer {current_user.access_token}'}
        requests.delete("https://api.upstox.com/v2/logout", headers=headers, timeout=10, verify=certifi.where())
        print(f"Successfully invalidated Upstox token for user {current_user.id}")
    except requests.exceptions.RequestException as e:
        print(f"Note: Could not invalidate Upstox token during logout. Error: {e}")
    logout_user()
    flash('You have been successfully logged out.', 'success')
    return redirect(url_for('auth.login'))