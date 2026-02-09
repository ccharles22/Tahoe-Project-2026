from flask import Flask, render_template, url_for, redirect, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, logout_user, current_user, login_required
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired, Length, ValidationError, Email
from flask_bcrypt import Bcrypt

# Initialize the Flask application 
app = Flask(__name__)

# Configure database BEFORE initializing SQLAlchemy
app.config['SQLALCHEMY_DATABASE_URI'] = (
    'postgresql://candicecharles:Candy22@100.80.183.102:5432/bio727p_group_project'
)
app.config['SECRET_KEY'] = 'mysecretkey'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize extensions AFTER config is set
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# --------------------
# Flask-Login configuration
# --------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User Model - MUST MATCH EXISTING DATABASE SCHEMA
class User(db.Model, UserMixin):
    __tablename__ = 'users'
    __table_args__ = {'schema': 'public', 'extend_existing': True}

    user_id = db.Column(db.BigInteger, primary_key=True)  # bigint in database
    username = db.Column(db.String(255), unique=True, nullable=False)  # varchar(255)
    email = db.Column(db.String(255), unique=True, nullable=False)  # varchar(255)
    password_hash = db.Column(db.String(64), nullable=False)  # char(64) - FIXED LENGTH!
    created_at = db.Column(db.DateTime, server_default=db.text('CURRENT_TIMESTAMP'))
    updated_at = db.Column(db.DateTime, server_default=db.text('CURRENT_TIMESTAMP'))

    # CRITICAL FIX: Flask-Login needs this method
    # By default it looks for 'id', but our primary key is 'user_id'
    def get_id(self):
        return str(self.user_id)


# Load user by ID for Flask-Login session handling
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Registration Form
class RegisterForm(FlaskForm):
    username = StringField( 
        validators=[InputRequired(), Length(min=4, max=255)],  # Changed to match database
        render_kw={"placeholder": "Username"}
    )
    
    email = StringField(
        validators=[InputRequired(), Email(), Length(max=255)],  # Added length constraint
        render_kw={"placeholder": "Email"}
    )

    password = PasswordField(
        validators=[InputRequired(), Length(min=4, max=20)],
        render_kw={"placeholder": "Password"}
    )

    submit = SubmitField("Register")

    def validate_username(self, username):
        existing_user_username = User.query.filter_by(username=username.data).first()
        if existing_user_username:
            raise ValidationError("That username already exists. Please choose a different one.")
    
    def validate_email(self, email):
        existing_user_email = User.query.filter_by(email=email.data).first()
        if existing_user_email:
            raise ValidationError("That email is already registered. Please use a different one.")


# Login Form
class LoginForm(FlaskForm):
    username = StringField(
        validators=[InputRequired(), Length(min=4, max=255)],  # Changed to match database
        render_kw={"placeholder": "Username"}
    )
    
    password = PasswordField(
        validators=[InputRequired(), Length(min=4, max=20)], 
        render_kw={"placeholder": "Password"}
    )
    
    submit = SubmitField("Login")


# --------------------
# Routes
# --------------------

@app.route('/')
def home():
    """Render the landing page"""
    return render_template('home.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Handle user registration"""
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('homepage'))
    
    form = RegisterForm()

    if form.validate_on_submit():
        try:
            # Hash the password before saving it
            hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
            
            # CRITICAL: Database has CHAR(64), bcrypt produces 60 chars
            # Pad with spaces to exactly 64 characters
            hashed_password = hashed_password.ljust(64)
            
            # Create a new user object
            new_user = User(
                username=form.username.data,
                email=form.email.data,
                password_hash=hashed_password
            )
            
            # Add to database
            db.session.add(new_user)
            db.session.commit()
            
            print(f"[SUCCESS] Registered user: {new_user.username}")
            print(f"[DEBUG] Hash length: {len(hashed_password)}")
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Registration failed: {str(e)}")
            flash(f'Error creating account: {str(e)}', 'error')
    
    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle user login"""
    # Redirect if already logged in
    if current_user.is_authenticated:
        return redirect(url_for('homepage'))
    
    form = LoginForm()

    if form.validate_on_submit():
        # Query user by username
        user = User.query.filter_by(username=form.username.data).first()
        
        if user:
            print(f"[DEBUG] User found: {user.username}")
            
            # CRITICAL: Database stores CHAR(64) with padding
            # Strip trailing spaces from stored hash before checking
            stored_hash = user.password_hash.rstrip()
            
            print(f"[DEBUG] Stored hash length: {len(user.password_hash)} (with padding)")
            print(f"[DEBUG] Trimmed hash length: {len(stored_hash)}")
            
            # Check password
            if bcrypt.check_password_hash(stored_hash, form.password.data):
                login_user(user)
                print(f"[SUCCESS] Login successful for: {user.username}")
                flash(f'Welcome back, {user.username}!', 'success')
                
                # Redirect to next page or homepage
                next_page = request.args.get('next')
                return redirect(next_page) if next_page else redirect(url_for('homepage'))
            else:
                print(f"[DEBUG] Password mismatch for user: {user.username}")
                flash('Invalid username or password', 'error')
        else:
            print(f"[DEBUG] User not found: {form.username.data}")
            flash('Invalid username or password', 'error')

    return render_template('login.html', form=form)


@app.route('/homepage')
@app.route('/HOMEPAGE')
@login_required
def homepage():
    """Protected homepage - requires login"""
    return render_template('HOMEPAGE.html')


@app.route('/logout', methods=['GET', 'POST'])
@login_required
def logout():
    """Log the user out and redirect to login page"""
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))


# --------------------
# Database initialization
# --------------------
if __name__ == '__main__':
    # DO NOT create tables - they already exist in PostgreSQL
    # The table was created externally with specific schema
    # Our model just connects to the existing table
    
    print("[INFO] Connecting to existing PostgreSQL database...")
    print("[INFO] Table: public.users (managed externally)")

    # Run the application
    app.run(debug=True)
