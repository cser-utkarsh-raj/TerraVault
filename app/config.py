"""Environment-driven configuration for local, test, and production apps."""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default_secret_key')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Some platforms provide postgres:// while SQLAlchemy expects postgresql://.
    # Normalize once at startup instead of scattering provider-specific checks.
    db_url = os.environ.get('DATABASE_URL', 'sqlite:///terravault.db')
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = db_url

    # Image upload configuration
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload size

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    # In production, require SSL for postgres if using Supabase
    # SQLALCHEMY_ENGINE_OPTIONS = {"sslmode": "require"}

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
