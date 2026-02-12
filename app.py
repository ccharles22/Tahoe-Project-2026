"""
Minimal Flask application for data parsing service.

Entry point for the data parsing and QC pipeline web service.
"""

from flask import Flask, redirect, url_for
from parsing.routes import parsing_bp
from parsing.models import init_db


def create_app() -> Flask:
    """
    Create and configure Flask application.
    
    Returns:
        Configured Flask application instance
    """
    app = Flask(__name__)
    
    # Configuration
    app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB max
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
    
    # Root route - redirect to upload page
    @app.route('/')
    def index():
        return redirect(url_for('parsing.upload_form'))
    
    # Register blueprints
    app.register_blueprint(parsing_bp)
    
    # Initialize database (create tables if they don't exist)
    with app.app_context():
        init_db()
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
