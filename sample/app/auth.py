# coding: utf-8

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, LoginManager, logout_user, UserMixin
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, EqualTo
from werkzeug.security import check_password_hash, generate_password_hash

from app.main import app, db

bp = Blueprint('auth', __name__, url_prefix='/auth')

# Create LoginManager instance and configure it for login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in or create an account to access this page."


@login_manager.user_loader
def load_user(user_id):
    # Return user if we get an id match
    return User.query.get(user_id) if user_id else None


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True)
    password = db.Column(db.String(120))
    name = db.Column(db.String(120))

    def __repr__(self):
        return '<User %r, %r>' % (self.email, self.name)

    def check_password(self, password):
        # Check the hash of the password to avoid storing plaintext passwords
        return check_password_hash(self.password, password)


class SignupForm(FlaskForm):
    name = StringField('Pen Name', validators=[DataRequired(message="Please provide a pen name.")])
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('New Password', [
        DataRequired(), 
        EqualTo('confirm_password', message='Passwords must match')
    ])
    confirm_password  = PasswordField('Confirm Password')

    def __init__(self, *args, **kwargs):
        FlaskForm.__init__(self, *args, **kwargs)
        self.user = None

    def validate(self):
        # check that form fields all match required formats
        rv = FlaskForm.validate(self)
        if not rv:
            return False
        
        # Check if the user already exists in our database
        user_match = User.query.filter_by(email=self.email.data).one_or_none()
        if user_match is not None:
            # If we already have a match, tell them to login
            self.email.errors.append('An account with that email already exists.')
            return False

        return True

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

    def __init__(self, *args, **kwargs):
        FlaskForm.__init__(self, *args, **kwargs)
        self.user = None

    def validate(self):
        rv = FlaskForm.validate(self)
        if not rv:
            return False

        # Grab the user by email
        user = User.query.filter_by(email=self.email.data).one_or_none()

        if user:
            # If the user exists, check that they entered the correct password
            password_match = user.check_password(self.password.data)
            if password_match:
                self.user = user
                return True

        self.password.errors.append('Invalid email and/or password specified.')
        return False


# Login page
@bp.route('/login/', methods=['GET', 'POST'])
def login():
    form = LoginForm()

    # Check that login is valid
    if form.validate_on_submit():
        # If valid login info, log them in and send them on their way
        login_user(form.user)
        flash('Logged in successfully.')
        return redirect(request.args.get('next') or url_for('index'))

    # Render login page for GET request or invalid POST request
    return render_template('auth/login.html', form=form)


#Sign Up Page
@bp.route('/signup/', methods=['GET', 'POST'])
def signup():
    form = SignupForm()

    # If form fields are valid and user not yet in database
    if form.validate_on_submit():
        # Add new user to the database
        add_user(form.email.data, form.password.data, form.name.data, True)

        # Send them to their destination or the home page
        flash('Thanks for signing up! Go to the Create page to make a post.')
        return redirect(request.args.get('next') or url_for('index'))

    # Render signup page for GET request or invalid POST request
    return render_template('auth/signup.html', form=form)


@bp.route('/logout/')
@login_required
def logout():
    logout_user()
    return redirect(request.args.get('next') or url_for('index'))


# Page to view account info
@bp.route('/account/')
@login_required
def account():
    # See how many posts the user has made
    from app.blog import Post
    post_count = Post.query.filter_by(author_id=current_user.id).count()

    return render_template('auth/account.html', user=current_user, post_count=post_count)


# Helper function to add a user to the database. Note that we expect  
# password in plaintext, but store the hash of the password in the db.
# Can log them in automatically, but login bool defaults to False
def add_user(email, password, name, login=False):
    new_user = User(
        email=email,
        password=generate_password_hash(password),
        name=name
    )

    # Add them to the database
    db.session.add(new_user)
    db.session.commit()

    # And log them in if requested
    if login:
        login_user(new_user)