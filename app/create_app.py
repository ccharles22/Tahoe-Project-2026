from __future__ import annotations

import logging
from flask import Flask

from app.web.routes import sequence_routes


def create_app() -> Flask:
    app = Flask(__name__)

    # Basic logging config
    logging.basicConfig(level=logging.INFO)

    # Register blueprints
    app.register_blueprint(sequence_routes.bp, url_prefix="/api")

    return app
