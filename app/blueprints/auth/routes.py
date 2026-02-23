from flask import render_template, url_for, redirect, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from sqlalchemy.exc import IntegrityError

from . import auth_bp
from app.extensions import db, bcrypt
from app.forms import RegisterForm, LoginForm
from app.models import User
from app.forms import SettingsForm

from flask import current_app


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("auth.homepage"))

    form = RegisterForm()

    if form.validate_on_submit():
        try:
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode("utf-8")

            new_user = User(
                username=form.username.data,
                email=form.email.data,
                password_hash=hashed_password,
            )

            db.session.add(new_user)
            db.session.commit()

            login_user(new_user)
            flash("Account created successfully!", "success")
            return redirect(url_for("auth.homepage"))

        except IntegrityError as e:
            db.session.rollback()
            err = str(getattr(e, "orig", e)).lower()
            if "email" in err:
                form.email.errors.append("That email is already registered. Please use a different one.")
            elif "username" in err:
                form.username.errors.append("That username already exists. Please choose a different one.")
            else:
                form.username.errors.append("Could not create account. Please try again.")
        except Exception:
            db.session.rollback()
            form.username.errors.append("Could not create account. Please try again.")

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("auth.homepage"))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()

        if user:
            stored_hash = (user.password_hash or "").rstrip()

            if bcrypt.check_password_hash(stored_hash, form.password.data):
                login_user(user)
                flash(f"Welcome back, {user.username}!", "success")

                next_page = request.args.get("next")
                return redirect(next_page) if next_page else redirect(url_for("auth.homepage"))

        form.password.errors.append("Invalid username or password.")

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
    from app.models import Experiment, Variant, WildtypeProtein
    from sqlalchemy import func

    uid = current_user.user_id

    try:
        exp_count = Experiment.query.filter_by(user_id=uid).count()
        latest_exp = (Experiment.query
                      .filter_by(user_id=uid)
                      .order_by(Experiment.created_at.desc())
                      .first())
        wt_count = WildtypeProtein.query.filter_by(user_id=uid).count()
    except Exception:
        exp_count = 0
        latest_exp = None
        wt_count = 0

    return render_template(
        "auth/homepage.html",
        exp_count=exp_count,
        latest_exp=latest_exp,
        wt_count=wt_count,
    )


@auth_bp.route("/")
def home():
    return redirect(url_for("auth.login"))


@auth_bp.route("/home-main")
@login_required
def home_main():
    return redirect(url_for("auth.homepage"))


@auth_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    form = SettingsForm()

    # Pre-fill form with current user info on GET
    if request.method == "GET":
        form.username.data = current_user.username
        form.email.data = current_user.email

    if form.validate_on_submit():
        try:
            # Check username/email uniqueness (exclude current user)
            if form.username.data != current_user.username:
                if User.query.filter_by(username=form.username.data).first():
                    flash("That username is already taken.", "error")
                    return render_template("auth/settings.html", form=form)

            if form.email.data != current_user.email:
                if User.query.filter_by(email=form.email.data).first():
                    flash("That email is already registered.", "error")
                    return render_template("auth/settings.html", form=form)

            # Update username/email
            current_user.username = form.username.data
            current_user.email = form.email.data

            # Handle password change if requested
            if form.new_password.data:
                if not form.current_password.data:
                    flash("Enter your current password to change it.", "error")
                    return render_template("auth/settings.html", form=form)

                if not bcrypt.check_password_hash((current_user.password_hash or "").rstrip(), form.current_password.data):
                    flash("Current password is incorrect.", "error")
                    return render_template("auth/settings.html", form=form)

                new_hash = bcrypt.generate_password_hash(form.new_password.data).decode("utf-8").strip()
                current_user.password_hash = new_hash

            db.session.add(current_user)
            db.session.commit()

            # Ensure the change persisted and the new password verifies correctly.
            user_to_check = current_user
            try:
                db.session.refresh(user_to_check)
            except Exception:
                # Refresh may fail in some session configs; re-query as fallback.
                user_to_check = User.query.get(current_user.user_id)

            if form.new_password.data:
                # Verify new password matches stored hash; if not, raise to trigger rollback.
                if not bcrypt.check_password_hash((user_to_check.password_hash or "").strip(), form.new_password.data):
                    raise Exception("Password update did not persist correctly")

            flash("Settings updated successfully.", "success")
            return redirect(url_for("auth.settings"))

        except Exception as e:
            db.session.rollback()
            flash(f"Error updating settings: {str(e)}", "error")

    return render_template("auth/settings.html", form=form)


@auth_bp.route('/_debug/create_test_user', methods=['POST', 'GET'])
def _debug_create_test_user():
    """Temporary dev-only helper: create or replace a test user for integration.
    Only active when Flask debug mode is on.
    """
    if not current_app.debug:
        return ("Not allowed", 403)

    try:
        uname = "integ_test_user"
        email = "integ_test_user@example.com"
        pwd = "Testpass123!"
        existing = User.query.filter_by(username=uname).first()
        if existing:
            # update email and password
            existing.email = email
            existing.password_hash = bcrypt.generate_password_hash(pwd).decode('utf-8')
            db.session.add(existing)
        else:
            u = User(username=uname, email=email, password_hash=bcrypt.generate_password_hash(pwd).decode('utf-8'))
            db.session.add(u)
        db.session.commit()
        return ("ok", 200)
    except Exception as e:
        db.session.rollback()
        return (f"error: {e}", 500)

