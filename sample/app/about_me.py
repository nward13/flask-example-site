from flask import Blueprint, render_template

bp = Blueprint('about_me', __name__)

@bp.route('/about_me/')
def about_me():
    return render_template('about_me/about_me.html')