"""Flask extension instances shared across the application."""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt

try:
    from flask_compress import Compress
except ModuleNotFoundError:
    Compress = None

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
compress = Compress() if Compress is not None else None
