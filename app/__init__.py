"""Application factory and shared docs-serving helpers for the UI_test app."""

import os
import logging
from flask import Flask, render_template, send_from_directory, abort, redirect, make_response
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
    """Create and configure the UI_test Flask application."""
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

    from .services.analysis.app import register_analysis_routes
    register_analysis_routes(app)

    @app.route("/favicon.ico")
    def favicon():
        icon_dir = os.path.join(app.static_folder, "img")
        return send_from_directory(
            icon_dir,
            "webpage_tahoe_favicon_v2.png",
            mimetype="image/png",
            max_age=0,
        )

    # Serve built MkDocs site (unified docs site output).
    # Routes are always registered so docs work after a build without requiring
    # the app to have seen `site/` at startup time.
    site_dir = os.path.join(
        os.path.dirname(__file__), "..", "mkdocs", "site"
    )
    site_dir = os.path.abspath(site_dir)
    metrics_site_dir = os.path.join(
        os.path.dirname(__file__), "..", "user_guide_mkdocs", "site"
    )
    metrics_site_dir = os.path.abspath(metrics_site_dir)
    bonus_site_dir = os.path.join(
        os.path.dirname(__file__), "..", "bonus_visualisations_mkdocs", "bonus_visualisations_mkdocs", "site"
    )
    bonus_site_dir = os.path.abspath(bonus_site_dir)

    def _mark_docs_no_cache(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    def _serve_docs_target_from(base_dir: str, target: str):
        path = os.path.join(base_dir, target)
        if os.path.isdir(path):
            target = os.path.join(target, "index.html")
            path = os.path.join(base_dir, target)
        if os.path.exists(path):
            return _mark_docs_no_cache(send_from_directory(base_dir, target, max_age=0))
        abort(404)

    def _serve_docs_target(target: str):
        return _serve_docs_target_from(site_dir, target)

    @app.route("/guide/")
    def docs_hub():
        return _mark_docs_no_cache(make_response(render_template("docs/guide_hub.html")))

    @app.route("/docs/")
    def docs_index():
        return _serve_docs_target("index.html")

    @app.route("/docs/database/")
    @app.route("/docs/database/<path:filename>")
    def docs_database_alias(filename: str = "index.html"):
        target = "/docs/postgresql_visualization/database/"
        if filename != "index.html":
            target = f"{target}{filename}"
        return redirect(target)

    @app.route("/docs/<path:filename>")
    def docs_files(filename):
        return _serve_docs_target(filename)

    # MkDocs builds in this project contain root-relative links (for example
    # /parsing_qc/... and /postgresql_visualization/...) plus shared asset
    # paths like /assets/... and /search/.... Serve those as aliases so the
    # guide remains navigable when hosted inside the Flask app.
    @app.route("/parsing_qc/")
    @app.route("/parsing_qc/<path:filename>")
    def docs_parsing_qc(filename: str = "index.html"):
        target = os.path.join("parsing_qc", filename)
        return _serve_docs_target(target)

    @app.route("/postgresql_visualization/")
    @app.route("/postgresql_visualization/<path:filename>")
    def docs_postgresql_visualization(filename: str = "index.html"):
        target = os.path.join("postgresql_visualization", filename)
        return _serve_docs_target(target)

    @app.route("/assets/<path:filename>")
    def docs_assets(filename: str):
        target = os.path.join("assets", filename)
        return _serve_docs_target(target)

    @app.route("/search/<path:filename>")
    def docs_search(filename: str):
        target = os.path.join("search", filename)
        return _serve_docs_target(target)

    def _serve_metrics_docs_target(target: str):
        return _serve_docs_target_from(metrics_site_dir, target)

    def _serve_bonus_docs_target(target: str):
        return _serve_docs_target_from(bonus_site_dir, target)

    @app.route("/metrics/")
    @app.route("/metrics/<path:filename>")
    def docs_metrics(filename: str = "index.html"):
        target = "/docs/postgresql_visualization/metrics/"
        if filename != "index.html":
            target = f"{target}{filename}"
        return redirect(target)

    @app.route("/activity_score_calculations/")
    @app.route("/activity_score_calculations/<path:filename>")
    def docs_activity_score(filename: str = "index.html"):
        target = "/docs/postgresql_visualization/activity_score_calculations/"
        if filename != "index.html":
            target = f"{target}{filename}"
        return redirect(target)

    @app.route("/bonus_visualisations/")
    @app.route("/bonus_visualisations/<path:filename>")
    def docs_bonus_visualisations(filename: str = "index.html"):
        target = "/docs/bonus_visualisations/"
        if filename != "index.html":
            target = f"{target}{filename}"
        return redirect(target)

    # The metrics-only guide links back to a shared set of PostgreSQL
    # documentation pages at root-level paths. Mirror those URLs so cross-links
    # remain navigable.
    root_postgres_sections = (
        "database",
        "schema_design_notes",
        "plots",
        "plots_lineage",
        "plots_distribution",
        "plots_top10",
        "plots_protein_network",
        "pipeline",
        "user_guide",
        "database_setup_tailscale",
        "postgresql_tailscale_methodology",
        "git_workflow",
        "OWNERS",
    )

    def _build_root_postgres_view(section: str):
        def _view(filename: str = "index.html"):
            target = os.path.join("postgresql_visualization", section, filename)
            return _serve_docs_target(target)

        return _view

    for section in root_postgres_sections:
        app.add_url_rule(
            f"/{section}/",
            endpoint=f"docs_root_{section}",
            view_func=_build_root_postgres_view(section),
        )
        app.add_url_rule(
            f"/{section}/<path:filename>",
            endpoint=f"docs_root_{section}_files",
            view_func=_build_root_postgres_view(section),
        )

    return app
