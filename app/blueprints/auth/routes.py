from flask import render_template, url_for, redirect, flash, request
from flask_login import login_user, logout_user, current_user, login_required

from . import auth_bp
from app.extensions import db, bcrypt
from app.forms import RegisterForm, LoginForm
from app.models import User


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("auth.homepage"))

    form = RegisterForm()

    if form.validate_on_submit():
        try:
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")

            # DB is CHAR(64). bcrypt is usually 60 chars. Pad to exactly 64.
            hashed_password = hashed_password.ljust(64)

            new_user = User(
                username=form.username.data,
                email=form.email.data,
                password_hash=hashed_password,
            )

            db.session.add(new_user)
            db.session.commit()

            flash("Account created successfully! Please log in.", "success")
            return redirect(url_for("auth.login"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error creating account: {str(e)}", "error")

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.homepage"))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user:
            # DB stores CHAR(64) padded; strip before checking
            stored_hash = (user.password_hash or "").rstrip()

            if bcrypt.check_password_hash(stored_hash, form.password.data):
                login_user(user)
                flash(f"Welcome back, {user.username}!", "success")

                next_page = request.args.get("next")
                return redirect(next_page) if next_page else redirect(url_for("auth.homepage"))

        flash("Invalid username or password", "error")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/homepage")
@login_required
def homepage():
    # Replace with your real protected landing page
    return render_template("auth/homepage.html")


@auth_bp.route("/")
def home():
    # Optional: a stage-1 landing page
    return render_template("home.html")
