from flask import Blueprint, render_template, redirect, url_for

home_bp = Blueprint("home", __name__)

@home_bp.get("/")
def home():
    return render_template("home.html")

@home_bp.get("/start")
def start():
    return redirect(url_for("staging.create_experiment")) #may need to change later if we change staging route name
