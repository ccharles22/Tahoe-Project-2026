import os
from flask import Flask
from dotenv import load_dotenv

from .extensions import db, login_manager, bcrypt
from .models import User

load_dotenv()

def create_app():
    app = Flask(__name__)  # use default: app/templates and app/static

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    if not app.config["SQLALCHEMY_DATABASE_URI"]:
        raise RuntimeError("DATABASE_URL is not set. Create a .env file with DATABASE_URL=...")

    # init extensions
    db.init_app(app)
    bcrypt.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id: str):
        return User.query.get(int(user_id))

    # ✅ IMPORTANT: ensure models are registered (only if needed)
    # If you already import models via .models above, you can omit this.
    # from . import models  # noqa: F401

    # register blueprints
    from .blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)

    # add staging blueprint
    from .blueprints.staging import staging_bp
    app.register_blueprint(staging_bp)

    # add home blueprint (if you have one)
    # from .blueprints.home import home_bp
    # app.register_blueprint(home_bp)

    return app
