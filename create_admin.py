In file: create_admin.py
from werkzeug.security import generate_password_hash
from app import create_app, db
from app.models import Admin, AppSettings
from dotenv import load_dotenv
load_dotenv()

app, _ = create_app()

with app.app_context():

ADMIN_USERNAME = 'Jayendra'
ADMIN_PASSWORD = 'Jayu1823'


# Delete existing admin if any
existing_admin = Admin.query.filter_by(username=ADMIN_USERNAME).first()
if existing_admin:
    db.session.delete(existing_admin)
    db.session.commit()
    print("Existing admin deleted.")

# Create new admin
hashed_password = generate_password_hash(ADMIN_PASSWORD, method='pbkdf2:sha256')
new_admin = Admin(username=ADMIN_USERNAME, password=hashed_password)
db.session.add(new_admin)
db.session.commit()
print(f"Admin '{ADMIN_USERNAME}' created with fixed password.")


# Initialize the AppSettings table
setting = AppSettings.query.filter_by(setting_name='global_app_status').first()
if not setting:
    new_setting = AppSettings(setting_name='global_app_status', is_on=False)
    db.session.add(new_setting)
    db.session.commit()
    print("Initialized 'global_app_status' setting to OFF.")
else:
    print("'global_app_status' setting already exists.")