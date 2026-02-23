import os
import logging
from flask import Flask, render_template, send_from_directory, abort
from dotenv import load_dotenv
from sqlalchemy.exc import OperationalError, DatabaseError

from .extensions import db, login_manager, bcrypt, compress
from .models import User

log = logging.getLogger(__name__)

load_dotenv()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        log.warning("Invalid integer for %s=%r; using default=%d", name, value, default)
        return default


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

    # Response compression for text assets (HTML/CSS/JS/JSON).
    app.config["COMPRESS_REGISTER"] = True
    app.config["COMPRESS_LEVEL"] = _env_int("COMPRESS_LEVEL", 6)
    app.config["COMPRESS_MIN_SIZE"] = _env_int("COMPRESS_MIN_SIZE", 500)
    app.config["COMPRESS_MIMETYPES"] = [
        "text/html",
        "text/css",
        "text/xml",
        "text/plain",
        "application/javascript",
        "application/json",
        "application/xml",
        "image/svg+xml",
    ]

    # DB engine settings are environment-driven so local/dev can fail fast.
    db_connect_timeout = _env_int("DB_CONNECT_TIMEOUT", 3)
    db_pool_recycle = _env_int("DB_POOL_RECYCLE", 280)
    db_pool_size = _env_int("DB_POOL_SIZE", 5)
    db_max_overflow = _env_int("DB_MAX_OVERFLOW", 10)
    db_keepalives_idle = _env_int("DB_KEEPALIVES_IDLE", 30)
    db_keepalives_interval = _env_int("DB_KEEPALIVES_INTERVAL", 10)
    db_keepalives_count = _env_int("DB_KEEPALIVES_COUNT", 5)

    engine_options = {
        "pool_recycle": db_pool_recycle,
        "pool_pre_ping": True,
        "pool_size": db_pool_size,
        "max_overflow": db_max_overflow,
    }
    if not (db_url or "").startswith("sqlite:"):
        engine_options["connect_args"] = {
            "connect_timeout": db_connect_timeout,
            "keepalives": 1,
            "keepalives_idle": db_keepalives_idle,
            "keepalives_interval": db_keepalives_interval,
            "keepalives_count": db_keepalives_count,
        }
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options

    if not app.config["SQLALCHEMY_DATABASE_URI"]:
        raise RuntimeError("DATABASE_URL is not set. Create a .env file with DATABASE_URL=...")

    # init extensions
    db.init_app(app)
    bcrypt.init_app(app)
    if compress is not None:
        compress.init_app(app)
    else:
        log.warning("Flask-Compress not installed; response compression is disabled.")

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
        return render_template("errors/db_error.html"), 503

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

    # Serve built MkDocs site if present (generated `site/` folder from `mkdocs build`)
    site_dir = os.path.join(os.path.dirname(__file__), "..", "site")
    site_dir = os.path.abspath(site_dir)
    if os.path.isdir(site_dir):
        @app.route("/docs/")
        def docs_index():
            return send_from_directory(site_dir, "index.html")

        @app.route("/docs/<path:filename>")
        def docs_files(filename):
            path = os.path.join(site_dir, filename)
            if os.path.exists(path):
                return send_from_directory(site_dir, filename)
            abort(404)

    return app

