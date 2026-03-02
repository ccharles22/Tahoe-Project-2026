"""WTForms definitions used by the authentication and settings flows."""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField
from wtforms.validators import InputRequired, Length, ValidationError, Email, Optional

from .models import User

class RegisterForm(FlaskForm):
    username = StringField(
        validators=[
            InputRequired(message="Username is required."),
            Length(min=4, max=255, message="Username must be between 4 and 255 characters."),
        ],
        render_kw={"placeholder": "Username"},
    )

    email = StringField(
        validators=[
            InputRequired(message="Email is required."),
            Email(message="Enter a valid email address."),
            Length(max=255, message="Email must be 255 characters or fewer."),
        ],
        render_kw={"placeholder": "Email"},
    )

    password = PasswordField(
        validators=[
            InputRequired(message="Password is required."),
            Length(min=4, max=20, message="Password must be between 4 and 20 characters."),
        ],
        render_kw={"placeholder": "Password"},
    )

    submit = SubmitField("Register")

    def validate_username(self, username):
        if User.query.filter_by(username=username.data).first():
            raise ValidationError("That username already exists. Please choose a different one.")

    def validate_email(self, email):
        if User.query.filter_by(email=email.data).first():
            raise ValidationError("That email is already registered. Please use a different one.")


class LoginForm(FlaskForm):
    username = StringField(
        validators=[
            InputRequired(message="Username is required."),
            Length(min=4, max=255, message="Username must be between 4 and 255 characters."),
        ],
        render_kw={"placeholder": "Username"},
    )

    password = PasswordField(
        validators=[
            InputRequired(message="Password is required."),
            Length(min=4, max=20, message="Password must be between 4 and 20 characters."),
        ],
        render_kw={"placeholder": "Password"},
    )

    submit = SubmitField("Login")


class SettingsForm(FlaskForm):
    username = StringField(
        validators=[InputRequired(), Length(min=4, max=255)],
        render_kw={"placeholder": "Username"},
    )

    email = StringField(
        validators=[InputRequired(), Email(), Length(max=255)],
        render_kw={"placeholder": "Email"},
    )

    current_password = PasswordField(
        validators=[Optional()],
        render_kw={"placeholder": "Current password (required to change password)"},
    )

    new_password = PasswordField(
        validators=[Optional(), Length(min=4, max=20)],
        render_kw={"placeholder": "New password (leave blank to keep current)"},
    )

    receive_notifications = BooleanField("Receive email notifications", default=True)

    submit = SubmitField("Save settings")
