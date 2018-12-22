# coding: utf-8

import calendar
from datetime import datetime, timedelta
from flask import Blueprint, flash, Flask, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.expression import extract, distinct
from wtforms import StringField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Length
from werkzeug.security import generate_password_hash

from app.main import db

bp = Blueprint('blog', __name__)

POSTS_PER_PAGE = 10

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80), nullable=False)
    body = db.Column(db.Text, nullable=False)
    pub_date = db.Column(db.DateTime, nullable=False)

    # Create relationship between posts and their authors
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    author = db.relationship(
        'User',
        backref=db.backref('posts', lazy='dynamic')
    )

    def __init__(self, title, body, author_id, pub_date=None):
        self.title = title
        self.body = body
        self.author_id=author_id
        if pub_date is None:
            pub_date = datetime.utcnow()
        self.pub_date = pub_date

    def __repr__(self):
        return '<Post %r>' % self.title


# Form to create a post
class PostForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    content = TextAreaField('Content', validators=[
        DataRequired(),
        Length(min=10, max=10000, message="Post must be between %(min)d and %(max)d characters.")
    ])


# Form to select how to sort the archives
class ArchiveForm(FlaskForm):
    # These are the categories for the archives. you can view posts
    # organized by author, month or year
    sort_by_values = {'author':'author', 'month':'month', 'year':'year'}
    sort_choices = [
        (sort_by_values['author'], 'Author'), 
        (sort_by_values['month'], 'Month (in 2018)'), 
        (sort_by_values['year'], 'Year')
    ]
    sort_by = SelectField(u'Sort By:', choices=sort_choices)

    # These are the subfields. These are filled in dynamically based on
    # the unique values in the database for whicheve category the user
    # selects. i.e. if I want to view posts by author, I will only have
    # to choose from authors that have published posts
    sub_sort = SelectField(u'Include Results From:', choices=[])


# The index route. The main page of our site serves all of the blog posts,
# starting with the most recent posts and showing 10 per page
@bp.route("/", methods=['GET', 'POST'])
def index():
    # Not sure if we want this to be the same for all pages yet, so keeping
    # as a constant with the same name, but assigned separately where used
    POSTS_PER_PAGE = 10

    # Get the current page from the request arguments
    page = request.args.get('page', default=1, type=int)

    # Get the most recent posts from the database, using paginate, our 
    # number of posts per page (10), and the current page (from request arguments)
    posts = Post.query.paginate(page, POSTS_PER_PAGE, False)

    # Get the urls for the next page and the previous page, which will be
    # used for "Older Posts" links
    next_url = url_for('blog.index', page=posts.next_num) if posts.has_next else None
    prev_url = url_for('blog.index', page=posts.prev_num) if posts.has_prev else None

    # Render the index template, passing in the posts to list on the new page
    # and the links to the new next and prev pages
    return render_template(
        'blog/index.html', 
        posts=posts.items,
        next_url=next_url,
        prev_url=prev_url
    )


# 'Create a Blog Post' Page
@bp.route("/blog/create", methods=['GET', 'POST'])
@login_required
def create():
    form = PostForm()

    if form.validate_on_submit():
        # Add post to the database. add_post returns true on success,
        # so we want to notify the user that they successfully created
        # a post, then send them to the home page
        if add_post(form.title.data, form.content.data, current_user.id):
            flash('Post created successfully.')
            return redirect(url_for('index'))

    # render create form on GET request or invalid POST request
    return render_template('blog/create.html', form=form)


# Page to view information and recent posts by an author
@bp.route("/blog/author/<int:author_id>")
def author(author_id):
    from app.auth import User

    # Grab the user (author) by the id in the route
    user = User.query.filter_by(id=author_id).one_or_none()
    
    # If we can't find the author id in our database, let the user know
    if user is None:
        flash("Can't find that user id.")
        return redirect(request.args.get('next') or url_for('index'))

    # Get the number of posts the author has published
    post_count = Post.query.filter_by(author_id=author_id).count()

    # Get the last three posts by the author (to display the titles)
    posts = Post.query.filter_by(author_id=author_id).order_by(Post.pub_date.desc()).limit(3).all()

    # Render the author's information page
    return render_template('blog/author.html', user=user, post_count=post_count, posts=posts)


# The page to view a list of all the authors that have posted on the blog.
# Should show their number of posts and a link to their more detailed
# information page
@bp.route("/blog/authors")
def authors():
    from app.auth import User
    
    # Grab the first 20 authors from the database. 20 is arbitrary, should
    # in theory just paginate this
    authors = User.query.limit(20).all()

    # get the number of posts each author has published
    for author in authors:
        author.post_count = Post.query.filter_by(author_id=author.id).count()

    # Render our authors template with the authors from the database
    return render_template('blog/authors.html', authors=authors)


# The archive of blog posts
@bp.route("/blog/archive/", methods=['GET', 'POST'])
def archive():
    from app.auth import User

    form = ArchiveForm()

    # Having trouble getting the select form to validate. This is 
    # definitely not secure, as we take inputs directly from user and user
    # them to access our db w/o validation, but it works for now
    if form.is_submitted():

        # The sorting category from the submitted form (i.e. yearly, monthly, by author)
        sort_by = form.sort_by.data

        # The element to search by in the category (i.e. the author's name).
        # The form data will always contain the sub-field value rather than
        # the name (the # for a month and the author_id for an author)
        sub_sort = form.sub_sort.data

        # If we're sorting by year, grab all the posts where year matches
        # the sub_sort parameter (the year the user wants posts from).
        # Again, the post limit is arbitrary, we should theoretically just
        # paginate this too
        if sort_by == ArchiveForm.sort_by_values['year']:
            posts = Post.query.filter(extract('year', Post.pub_date) == sub_sort).limit(30).all()

        # If we're sorting by month, grab all the posts where month matches
        # the sub-sort parameter
        elif sort_by == ArchiveForm.sort_by_values['month']:
            posts = Post.query.filter(extract('month', Post.pub_date) == sub_sort).limit(30).all()

        # If we're sorting by author, grab all the posts where author_id
        # matches the sub-sort parameter
        elif sort_by == ArchiveForm.sort_by_values['author']:
            posts = Post.query.filter_by(author_id=sub_sort).limit(30).all()

        # Render the template with all of the posts in that category.
        return render_template(
            'blog/archive.html', 
            form=None,  
            sub_options=None, 
            posts=posts,
        )

    # If this is a GET request, we send an object to the template with all 
    # of the potential sort selections for each category (rather than an 
    # AJAX request on selection of the category). This allows us to use
    # jQuery to quickly change the secondary selection elements based
    # on which category the user selected. To do this, we need to find all
    # of the unique values in the database for each category (years, months, authors)


    # Get all the unique publication years in the database
    years_raw = db.session.query(distinct(extract('year', Post.pub_date))).all()
    # Flatten the returned tuples e.g. query returns (2018,) but we want 2018
    # Also, add each value to a dict so that we can match the format of authors and months,
    # which both require display names that don't match the value names
    years = [{'value':year, 'name':year} for (year,) in years_raw]


    # Get all the unique publication months for posts published in 2018 from the db
    # First, get all the posts from this year, then 
    posts_this_yr = Post.query.filter(extract('year', Post.pub_date) == 2018).all()
    month_values = []
    # Filter out the unique months of publication
    for post in posts_this_yr:
        month = post.pub_date.month
        if month not in month_values:
            month_values.append(month)
    # Take all the unique month numbers and match them up with a display name
    # i.e. I want to choose from January, February, rather than 1, 2
    months = [{'value':month, 'name':calendar.month_name[month]} for month in month_values]


    # Get all the unique author id's from the db
    author_ids_raw = db.session.query(Post.author_id).distinct().limit(10).all()
    # Flatten the id values
    author_ids = [author_id for (author_id,) in author_ids_raw]
    authors = []
    # Grab the name for each author_id, and add them to an object so that
    # users can select authors by name, but we can still recieve the request
    # by author_id (because names are not unique values in the db)
    for author_id in author_ids:
        authors.append({
            'value':author_id, 
            'name': User.query.filter_by(id=author_id).one_or_none().name 
        })


    # Store all of our unique values for each category as one object to 
    # pass to the template so that our js can access it
    # Each item in the dict represents a category and contains a list of 
    # sub-dicts, where the sub-dicts contain the value and display name 
    # for each unique option in the category
    sub_options = {
        'year': years,
        'month': months,
        'author': authors
    }

    # Render out template without posts for a GET request and show the
    # user the selection form
    return render_template(
        'blog/archive.html', 
        form=form,  
        sub_options=sub_options,
        posts=None
    )


# Helper function to add posts to the database
def add_post(title, body, author_id, pub_date=None):
    # Add post to the database
    new_post = Post(
        title = title,
        body = body,
        author_id = author_id,
        pub_date=pub_date
    )
    db.session.add(new_post)
    db.session.commit()

    # Return true on success so if called from browser, UI can notify user
    return True


# Create a couple fake accounts and articles
@bp.route("/seed")
def seed():
    from app.auth import User, add_user

    # Check that we're not blowing up our own database with this function
    post_count = Post.query.count()
    if (post_count > 60):
        flash("Too many posts. Bailing.")
        return redirect(url_for('index'))

    # Use really long emails, because right now it doesn't check for a
    # collision in the database
    users = [
        {'email':"fakeemailreserved@example.com", 'password':"password", 'name':"Joe"},
        {'email':"anotherlongfakeemail@example.com", 'password':"password", 'name':"Sawyer"},
        {'email':"longemailsaretheworst@example.com", 'password':"password", 'name':"Danielle"}
    ]

    # post content
    posts = [
        "Iis repugnemus perficitur dei persuadere dum praesertim familiarem quodcumqu",
        "reliqui ut vigilia mo at ostendi. Ut re vero unde soni ex ac solo. Quicquam temporis physicae ex ex co. Gi quibusnam perceptio ad ac industria persuasum eminenter. Male vi eram quin ha ii ad modo inde. Nos via probentur obversari ope opportune. Ea de animam iisdem juncta.",
        "Ita dependent productus dat simplicia uno. Aciem corpo ",
        "Re invenerunt transferre imbecillia prosecutus de dissolvant gi occasionem. Obstat ferant suo multae putavi quodam partes sit hoc. Sed ope sex ero conemur aliq",
        "Ipso in utor et sine. Tum hic agnosco proprie illarum cum agendam efficta mem creatum",
        "Expectem decipior eam abducere doctrina ero habuimus sae cavendum. Tractatu admittit ut de cavendum occurrit invenero co alicujus. Re invenerunt transferre imbecillia prosecutus de dissolvant gi occasionem. Obstat ferant suo multae putavi quodam partes sit hoc",
        "Quaslibet meditatio meo libertate ens praeditis. Uti otii nam hac dei haud alia deus. Deinde realem falsae statim usu rantem hos inquam dei.",
        "Dari boni co vi anno. Extitisse tantumdem abstinere formantur dat suspicari mea est",
        "Evidentius aliquoties at si perficitur de expectabam deceperunt. Sae tot dominum dicimus futurus divelli. Sex qui quales aptior tamque hic. ",
        "Quantumvis persuadeam ha se ut credidique ac integritas",
        "Alterius addamque ea gi fingerem sequatur sessione is credendi.",
        "Ea an istis vetus demus. Divinae videmur ubi proinde una cum rei. Pappo et ideae summa longa locis to.",
        "Extitisse tantumdem abstinere formantur dat suspicari mea est. Novi vel has fal sine dat etsi",
    ]

    # Add users
    for user in users:
        # If the user doesn't exist yet, add them
        if User.query.filter_by(email=user['email']).one_or_none() is None:
            add_user(user['email'], user['password'], user['name'])

        # Grab the user id
        user_entry = User.query.filter_by(email=user['email']).one_or_none()
        user['id'] = user_entry.id

    # Store current time to calculate varying fake publish dates for the fake posts
    now = datetime.utcnow()

    # Create 13 blog posts, decreasing the pub_date every time to create some variety
    for idx, post in enumerate(posts):
        # Rotate through author_id's, publishing every post from a new author
        # until we run out of made up authors
        author_id = users[idx % (len(users))]['id']

        # Calculate the publish date. This is done just to provide some
        # variety and make the archive more interesting
        time_diff = timedelta(days=14)
        pub_date = now - time_diff * idx

        # Make the title of each post based on the current post count
        title = "Post Number " + str(post_count + idx + 1)

        # Add the post to the database
        add_post(title, post, author_id, pub_date)

    flash('Lots of new posts!')
    return redirect(url_for('index'))