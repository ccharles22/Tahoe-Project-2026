"""Simple redirects into the homepage and staging workspace."""

from flask import Blueprint, redirect, url_for

home_bp = Blueprint("home", __name__)

@home_bp.get("/")
def home():
    """Send the root route to the public homepage."""
    return redirect(url_for("auth.homepage"))

@home_bp.get("/start")
def start():
    """Send the start shortcut to the staging workspace."""
    return redirect(url_for("staging.create_experiment"))
