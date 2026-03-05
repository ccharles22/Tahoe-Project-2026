"""Authentication and homepage routes for the UI_test app."""

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
    """Redirect the register shortcut to the homepage auth sheet."""
    if current_user.is_authenticated:
        return redirect(url_for("auth.homepage"))
    return redirect(url_for("auth.homepage", auth="register"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Redirect the login shortcut to the homepage auth sheet."""
    if current_user.is_authenticated:
        return redirect(url_for("auth.homepage"))
    next_page = (request.values.get("next") or "").strip()
    if next_page:
        return redirect(url_for("auth.homepage", auth="login", next=next_page))
    return redirect(url_for("auth.homepage", auth="login"))


@auth_bp.route("/logout", methods=["GET", "POST"])
@login_required
def logout():
    """Terminate the current session and return to the homepage."""
    logout_user()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("auth.homepage"))


@auth_bp.route("/homepage", methods=["GET", "POST"])
def homepage():
    """Render the public homepage and handle inline auth actions."""
    from app.models import Experiment, Variant, WildtypeProtein
    from sqlalchemy import func

    login_form = LoginForm(prefix="login")
    register_form = RegisterForm(prefix="register")
    requested_auth_panel = (request.args.get("auth") or "").strip().lower()
    open_auth_panel = requested_auth_panel if requested_auth_panel in {"login", "register"} else None
    login_next = (request.args.get("next") or "").strip()

    # Dispatch based on which inline auth form (login or register) was submitted.
    if request.method == "POST":
        auth_action = (request.form.get("auth_action") or "").strip().lower()
        if auth_action == "login":
            open_auth_panel = "login"
            if login_form.validate():
                user = User.query.filter_by(username=login_form.username.data).first()
                if user:
                    # Strip trailing whitespace that may pad fixed-width DB columns.
                    stored_hash = (user.password_hash or "").rstrip()
                    if bcrypt.check_password_hash(stored_hash, login_form.password.data):
                        login_user(user)
                        flash(f"Welcome back, {user.username}!", "success")
                        next_page = (request.form.get("next") or request.args.get("next") or "").strip()
                        return redirect(next_page) if next_page else redirect(url_for("auth.homepage"))
                login_form.password.errors.append("Invalid username or password.")
        elif auth_action == "register":
            open_auth_panel = "register"
            if register_form.validate():
                try:
                    hashed_password = bcrypt.generate_password_hash(register_form.password.data).decode("utf-8")
                    new_user = User(
                        username=register_form.username.data,
                        email=register_form.email.data,
                        password_hash=hashed_password,
                    )
                    db.session.add(new_user)
                    db.session.commit()
                    login_user(new_user)
                    flash("Account created successfully!", "success")
                    return redirect(url_for("auth.homepage"))
                except IntegrityError as e:
                    # Determine which unique constraint was violated for targeted feedback.
                    db.session.rollback()
                    err = str(getattr(e, "orig", e)).lower()
                    if "email" in err:
                        register_form.email.errors.append("That email is already registered. Please use a different one.")
                    elif "username" in err:
                        register_form.username.errors.append("That username already exists. Please choose a different one.")
                    else:
                        register_form.username.errors.append("Could not create account. Please try again.")
                except Exception:
                    db.session.rollback()
                    register_form.username.errors.append("Could not create account. Please try again.")

    # Gather dashboard statistics for authenticated users.
    exp_count = 0
    latest_exp = None
    wt_count = 0

    if current_user.is_authenticated:
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
        login_form=login_form,
        register_form=register_form,
        open_auth_panel=open_auth_panel,
        login_next=login_next,
    )


@auth_bp.route("/")
def home():
    """Redirect the auth root path to the homepage."""
    return redirect(url_for("auth.homepage"))


@auth_bp.route("/home-main")
def home_main():
    """Support legacy homepage links by redirecting to the homepage."""
    return redirect(url_for("auth.homepage"))


@auth_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    """Render and process the account settings form."""
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
