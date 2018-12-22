import os

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from werkzeug.debug import DebuggedApplication
from werkzeug.security import generate_password_hash

from app import commands

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://{}:{}@{}:3306/{}'.format(
    os.getenv('MYSQL_USERNAME', 'web_user'),
    os.getenv('MYSQL_PASSWORD', 'password'),
    os.getenv('MYSQL_HOST', 'db'), os.getenv('MYSQL_DATABASE', 'sample_app'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'this is something special'

if app.debug:
    app.wsgi_app = DebuggedApplication(app.wsgi_app, True)

db = SQLAlchemy(app)
commands.init_app(app, db)

# Make imports from rest of app after app is configured
from app import auth, blog, about_me

# Register blueprints

# about me bp just serves the about me page. No other logic
app.register_blueprint(about_me.bp)
# auth bp handles all of the login and new user logic
app.register_blueprint(auth.bp)
# blog bp handles creating, viewing, and sorting blog posts
app.register_blueprint(blog.bp)
app.add_url_rule('/', endpoint='index')


if __name__ == "__main__":
    app.run()
