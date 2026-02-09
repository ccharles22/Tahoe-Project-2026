import os
from flask import Flask
from app.db import db

# Factory function to create and configure the Flask application
def create_app():
    app = Flask(__name__)

    # --- DB CONFIG ---
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev_secret") 
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///tahoe.db") 
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False # disable to save resources; not needed for this app

    db.init_app(app)


    # Import models so SQLAlchemy knows them before create_all()
    from app import models  # ensures tables are registered

    # Create tables
    with app.app_context():
        db.create_all()
    # --- END DB CONFIG ---

    # --- BLUEPRINTS ---
    from app.routes.home import home_bp
    from app.routes.staging import staging_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(staging_bp)
    # --- END BLUEPRINTS ---

    return app