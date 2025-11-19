# In file: app/models.py (FINAL CORRECTED VERSION)

import os
from . import db
from flask_login import UserMixin
from sqlalchemy.sql import func
from datetime import datetime
from cryptography.fernet import Fernet

# --- Encryption Setup ---
try:
    ENCRYPTION_KEY = os.environ.get('FERNET_KEY').encode()
except AttributeError:
    raise RuntimeError("CRITICAL: FERNET_KEY environment variable not set.")

cipher_suite = Fernet(ENCRYPTION_KEY)

# --- Final User Model for User-Specific Encrypted Credentials ---
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    __table_args__ = {'extend_existing': True} # 💥 FIX 2: Safety net for Celery startup
    
    id = db.Column(db.Integer, primary_key=True)
    upstox_user_id = db.Column(db.String(100), unique=True, nullable=True)
    name = db.Column(db.String(100), nullable=True)
    mobile_number = db.Column(db.String(20), unique=True, nullable=False)
    
    is_trading_on = db.Column(db.Boolean, default=True, nullable=False)
    quantity = db.Column(db.Integer, default=75, nullable=False)
    registration_date = db.Column(db.DateTime(timezone=True), server_default=func.now())

    # --- Secure Storage for User-Specific Credentials (Encrypted) ---
    encrypted_client_id = db.Column(db.LargeBinary, nullable=True)
    encrypted_client_secret = db.Column(db.LargeBinary, nullable=True)
    encrypted_access_token = db.Column(db.LargeBinary, nullable=True)

    # --- Properties to automatically handle ENCRYPTION/DECRYPTION (User Token) ---
    @property
    def access_token(self):
        if not self.encrypted_access_token: return None
        try: return cipher_suite.decrypt(self.encrypted_access_token).decode()
        except Exception: return None

    @access_token.setter
    def access_token(self, value):
        self.encrypted_access_token = cipher_suite.encrypt(value.encode()) if value else None
        
    @property
    def client_id(self):
        if not self.encrypted_client_id: return None
        try: return cipher_suite.decrypt(self.encrypted_client_id).decode()
        except Exception: return None
    @client_id.setter
    def client_id(self, value):
        self.encrypted_client_id = cipher_suite.encrypt(value.encode()) if value else None

    @property
    def client_secret(self):
        if not self.encrypted_client_secret: return None
        try: return cipher_suite.decrypt(self.encrypted_client_secret).decode()
        except Exception: return None
    @client_secret.setter
    def client_secret(self, value):
        self.encrypted_client_secret = cipher_suite.encrypt(value.encode()) if value else None


# --- AppSettings Model for Owner Token Storage (System Credentials) ---
class AppSettings(db.Model):
    __tablename__ = 'app_settings'
    __table_args__ = {'extend_existing': True} # 💥 FIX 2: Safety net for Celery startup
    
    id = db.Column(db.Integer, primary_key=True)
    setting_name = db.Column(db.String(50), unique=True, nullable=False)
    is_on = db.Column(db.Boolean, default=False, nullable=False)
    
    # Dedicated field for a large, encrypted binary secret (e.g., Owner Access Token)
    encrypted_value = db.Column(db.LargeBinary, nullable=True) 
    
    # Property to automatically handle encryption/decryption of the secret (Owner Token)
    @property
    def secret_value(self):
        if not self.encrypted_value: return None
        try: return cipher_suite.decrypt(self.encrypted_value).decode()
        except Exception: return None

    @secret_value.setter
    def secret_value(self, value):
        self.encrypted_value = cipher_suite.encrypt(value.encode()) if value else None

# --- UNCHANGED Admin Model ---
class Admin(UserMixin, db.Model):
    __tablename__ = 'admins'
    __table_args__ = {'extend_existing': True} # 💥 FIX 2: Safety net for Celery startup
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)