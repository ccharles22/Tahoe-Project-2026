import os
import logging
from flask import Flask, render_template
from dotenv import load_dotenv
from sqlalchemy.exc import OperationalError, DatabaseError

from .extensions import db, login_manager, bcrypt
from .models import User

log = logging.getLogger(__name__)

load_dotenv()

def create_app():
    app = Flask(__name__)

    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")
    db_url = os.getenv("DATABASE_URL")

    # SQLite path normalisation (local dev / tests)
    if db_url and db_url.startswith("sqlite:"):
        if db_url not in {"sqlite:///:memory:", "sqlite://"}:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            if db_url.startswith("sqlite:////"):
                abs_path = db_url.replace("sqlite:////", "", 1)
            else:
                rel_path = db_url.replace("sqlite:///", "", 1)
                abs_path = rel_path if os.path.isabs(rel_path) else os.path.join(base_dir, rel_path)
                db_url = "sqlite:////" + abs_path.replace("\\", "/")
            db_dir = os.path.dirname(abs_path)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Connection stability for remote Postgres (Tailscale / VPN)
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_recycle": 280,
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "connect_args": {
            "connect_timeout": 10,
            "keepalives": 1,
            "keepalives_idle": 30,
            "keepalives_interval": 10,
            "keepalives_count": 5,
        },
    }

    if not app.config["SQLALCHEMY_DATABASE_URI"]:
        raise RuntimeError("DATABASE_URL is not set. Create a .env file with DATABASE_URL=...")

    # init extensions
    db.init_app(app)
    bcrypt.init_app(app)

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id: str):
        try:
            return User.query.get(int(user_id))
        except (OperationalError, DatabaseError) as e:
            log.warning("DB unreachable in user_loader: %s", e)
            return None          # treat as logged-out; avoids crash

    # Graceful error page for DB connection failures
    @app.errorhandler(OperationalError)
    def handle_db_error(error):
        log.error("Database connection error: %s", error)
        return render_template("db_error.html"), 503

    # register blueprints
    from .blueprints.auth import auth_bp
    app.register_blueprint(auth_bp)

    from .blueprints.staging import staging_bp
    app.register_blueprint(staging_bp)

    from .blueprints.staging.routes.home import home_bp
    app.register_blueprint(home_bp)

    from .blueprints.parsing import parsing_bp
    app.register_blueprint(parsing_bp)

    from .blueprints.sequence import sequence_bp
    app.register_blueprint(sequence_bp)

    return app
