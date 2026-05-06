from flask_sqlalchemy import SQLAlchemy
from cryptography.fernet import Fernet
import os
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# Clé Fernet
if not os.path.exists('fernet.key'):
    with open('fernet.key', 'wb') as f:
        f.write(Fernet.generate_key())

with open('fernet.key', 'rb') as f:
    fernet = Fernet(f.read())



class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)   # email chiffré
    password = db.Column(db.String(255), nullable=False)             # mot de passe chiffré
    region = db.Column(db.String(50), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    alerts_enabled = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        """Hash et stocke le mot de passe de l'utilisateur."""
        self.password = generate_password_hash(password)

    def check_password(self, password):
        """Vérifie le mot de passe de l'utilisateur."""
        return check_password_hash(self.password, password)

    def set_email(self, email):
        """Chiffre et stocke l'email de l'utilisateur."""
        self.email = fernet.encrypt(email.encode())

    def get_email(self):
        """Déchiffre et retourne l'email de l'utilisateur."""
        try:
            return fernet.decrypt(self.email).decode()
        except Exception:
            return None

    def get_region(self):
        return self.region
    
    def set_region(self, region):
        self.region = region

    def is_alerts_enabled(self):
        return self.alerts_enabled
    
    def set_alerts_enabled(self, enabled):
        self.alerts_enabled = enabled
