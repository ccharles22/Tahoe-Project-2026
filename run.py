"""Flask application entry point.

Creates and runs the app using the factory defined in ``app/__init__.py``.
Use ``python run.py`` for local development with hot-reload enabled.
"""

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, reloader_type="stat")
