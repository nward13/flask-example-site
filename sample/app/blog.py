# coding: utf-8

import calendar
from itertools import chain
from datetime import datetime, timedelta
from flask import Blueprint, flash, Flask, redirect, render_template, request, url_for, jsonify
from flask_login import current_user, login_required
from flask_wtf import FlaskForm
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql.expression import extract, distinct, func
from wtforms import StringField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Length
from werkzeug.security import generate_password_hash

from app.main import db
from app.auth import User, add_user

bp = Blueprint('blog', __name__)

# Number of items for each page across the site (i.e. main blog, archives, etc.)
ITEMS_PER_PAGE = 10


# Database model for blog posts
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
    # Categories for the archives. you can view posts organized by author, 
    # month or year. The field choices are updated dynamically based on
    # the unique values in the database for the user's current selection.
    # i.e. if I selected 2017 as the year, I will only be able to select
    # from authors who wrote posts in 2017
    year = SelectField('Year:', choices=[], coerce=int)
    month = SelectField('Month', choices=[], coerce=int)
    author = SelectField('Author', choices=[], coerce=int)


# The index route. The main page of our site serves all of the blog posts,
# starting with the most recent posts and showing 10 per page
@bp.route("/", methods=['GET', 'POST'])
def index():
    # Get the current page from the request arguments
    page = request.args.get('page', default=1, type=int)

    # Get the most recent posts from the database, using paginate, our 
    # number of posts per page (10), and the current page (from request arguments)
    posts = Post.query.order_by(Post.pub_date.desc()).paginate(page, ITEMS_PER_PAGE, False)

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
@bp.route("/blog/create/", methods=['GET', 'POST'])
@login_required
def create():
    form = PostForm()

    if form.validate_on_submit():
        # Add post to the database
        add_post(form.title.data, form.content.data, current_user.id)
        db.session.commit()
        
        # notify the user that they successfully created a post 
        flash('Post created successfully.')
        # Send them to the homepage
        return redirect(url_for('index'))

    # render create form on GET request or invalid POST request
    return render_template('blog/create.html', form=form)


# Page to view information and recent posts by an author
@bp.route("/blog/author/<int:author_id>/")
def author(author_id):

    # Grab the user (author) by the id in the route
    user = User.query.get(author_id)
    
    # If we can't find the author id in our database, let the user know
    if user is None:
        flash("Can't find that user id.")
        return redirect(request.args.get('next') or url_for('index'))

    # Base query for posts by author
    user_posts_query = Post.query.filter_by(author_id=author_id)

    # Get the number of posts the author has published
    post_count = user_posts_query.count()

    # Get the last three posts by the author (to display the titles)
    posts = user_posts_query.order_by(Post.pub_date.desc()).limit(3).all()

    # Render the author's information page
    return render_template('blog/author.html', user=user, post_count=post_count, posts=posts)


# The page to view a list of all the authors that have posted on the blog.
# Should show their number of posts and a link to their more detailed
# information page
@bp.route("/blog/authors/")
def authors():
    # Get the current page from the request arguments
    page = request.args.get('page', default=1, type=int)
    
    # Get each user that has made a post and the number of posts they 
    # have made. Returns a pagination object. post_counts.items will return
    # a list of (User, post_count) tuples. In the event that there are 
    # no matching records, returns an empty list
    post_counts = User.query.with_entities(User, func.count(Post.author_id)) \
        .outerjoin(Post, User.id == Post.author_id).filter(Post.id != None) \
        .group_by(Post.author_id).paginate(page, ITEMS_PER_PAGE, False)

    # Go from a list of (User, post_count) tuples to a list of objects
    # containing only the values we need to pass into our template 
    authors = [{'id':user.id, 'name':user.name, 'post_count':post_count} 
        for (user, post_count) in post_counts.items]

    # Get the urls for the next page and the previous page of authors
    next_url = url_for('blog.authors', page=post_counts.next_num) if post_counts.has_next else None
    prev_url = url_for('blog.authors', page=post_counts.prev_num) if post_counts.has_prev else None

    # Render our authors template with the authors from the database
    return render_template(
        'blog/authors.html', 
        authors=authors,
        next_url=next_url,
        prev_url=prev_url
    )


# Returns a JSON object with the options available for a given selection
# of archive categories. Used by the archive page JS to fill the archive
# select fields as the user narrows their search
@bp.route("/archive_options_ajax/")
def archive_options_ajax():
    # Grab the query paramaters from the request. Any parameter = 0 means
    # return all of the options for that category
    year = request.args.get('year')
    month = request.args.get('month')
    author_id = request.args.get('author')

    # Return a JSON of the distinct values in the database. i.e. If the 
    # request contains year=2017, returned object will have all available 
    # years, months with posts during 2017, and authors who made posts in 2017
    options = archive_options(year, month, author_id)
    return jsonify(options)
    

# The archive of blog posts
@bp.route("/blog/archive/", methods=['GET', 'POST'])
def archive():
    # Grab the year, month, author args from the request.
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    author_id = request.args.get('author_id', type=int)

    # If the request args are not None, we're looking for another page of
    # the archive posts
    if None not in (year, month, author_id):
        # Get the current page from the request arguments
        page = request.args.get('page', default=1, type=int)

        # Get all of the posts for the given paramters. Returns a pagination
        # object where the items are a list of Post objects
        posts = archive_posts(year, month, author_id).paginate(page, ITEMS_PER_PAGE, False)

        # Get the urls for the next page and the previous page, which will be
        # used for "Older Posts" links
        next_url = url_for('blog.archive', \
            page=posts.next_num, \
            year=year, \
            month=month, \
            author_id=author_id) \
            if posts.has_next else None

        prev_url = url_for('blog.archive', \
            page=posts.prev_num, \
            year=year, \
            month=month, \
            author_id=author_id) \
            if posts.has_prev else None

        # Render the template with all of the posts in the category on the
        # page requested.
        return render_template(
            'blog/archive.html', 
            form=None,
            posts=posts.items,
            next_url=next_url,
            prev_url=prev_url
        )
        
    # We're not looking for another page of posts, so it's either a POST
    # request submitting the archive form or an initial GET looking
    # for the archive form

    # Instantiate the form
    form = ArchiveForm()

    # Get all available unique values for years, months, and authors in the db 
    options = archive_options()  

    # archive options returns a dictionary of lists, with each list containing
    # a dict with 'value' and 'name' for each option, where value is the
    # useful value to us and name is the display name. We want to add these
    # options to the form choices as (value, name) tuples
    form.year.choices = [(choice['value'], choice['name']) for choice in options['year']]
    form.month.choices = [(choice['value'], choice['name']) for choice in options['month']]
    form.author.choices = [(choice['value'], choice['name']) for choice in options['author']]

    # POST request with valid form
    if form.validate_on_submit():
        # Grab the query parameters from the form
        year = form.year.data
        month = form.month.data
        author_id = form.author.data

        # Get all of the posts for the given paramters. Returns a pagination
        # object where the items are a list of Post objects
        posts = archive_posts(year, month, author_id).paginate(1, ITEMS_PER_PAGE, False)

        # Get the urls for the next page and the previous page, which will be
        # used for "Older Posts" links
        next_url = url_for('blog.archive', \
            page=posts.next_num, \
            year=year, month=month, \
            author_id=author_id) \
            if posts.has_next else None

        prev_url = url_for('blog.archive', \
            page=posts.prev_num, \
            year=year, \
            month=month, \
            author_id=author_id) \
            if posts.has_prev else None

        # Render the template with the first page of posts in that category.
        return render_template(
            'blog/archive.html', 
            form=None,
            posts=posts.items,
            next_url=next_url,
            prev_url=prev_url
        )

    # Render our template without posts for a GET request with no request
    # args and show the user the selection form
    return render_template(
        'blog/archive.html', 
        form=form,
        posts=None
    )


# Returns a filter to specify the post's publish year. year=0 means
# 'any year', so it returns an empty string which will not affect the query
def year_filter(year):
    return '' if int(year) == 0 else extract('year', Post.pub_date) == year


# Returns a filter to specify the post's publish month. month=0 means
# 'any month', so it returns an empty string which will not affect the query
def month_filter(month):
    return '' if int(month) == 0 else extract('month', Post.pub_date) == month


# Returns a filter to specify the post's author. author_id=0 means 'any
# author', so it returns an empty string which will not affect the query
def author_filter(author_id):
    return '' if int(author_id) == 0 else Post.author_id == author_id


# Returns the unique year values in the db corresponding to the given month
# and author parameters. Calling without arguments will return all unique years
def year_options(month=0, author_id=0):
    # Get the query filters for the given month and author. 0 values will result
    # in an empty string in the filters list which will not affect the query
    filters = [month_filter(month), author_filter(author_id)]

    # Get all unique year values for the given month and author. Returns
    # a list of (year,) tuples
    years_raw = db.session.query(distinct(extract('year', Post.pub_date)))\
        .filter(*filters).all()

    # Return a list of dicts with the value and display name for each year    
    return [{'value':year, 'name':year} for (year,) in years_raw]


# Returns the unique month values in the db corresponding to the given year
# and author parameters. Calling without arguments will return all unique months
def month_options(year=0, author_id=0):
    # Get the query filters for the given year and author. 0 values will result
    # in an empty string in the filters list which will not affect the query
    filters = [year_filter(year), author_filter(author_id)]

    # Get all unique month values for the given year and author. Returns
    # a list of (month,) tuples
    months_raw = db.session.query(distinct(extract('month', Post.pub_date)))\
        .filter(*filters).all()

    # Return a list of dicts with the value and display name for each month
    return [{'value':month, 'name':calendar.month_name[month]} for (month,) in months_raw]


# Returns the unique authors in the db corresponding to the given year and 
# month parameters. Calling without arguments will return all unique authors
def author_options(year=0, month=0):
    # Get the query filters for the given month and year. 0 values will result
    # in an empty string in the filters list which will not affect the query
    filters = [year_filter(year), month_filter(month)]

    # Get all unique author_id values and their names for the given year 
    # and month. Returns a list of (author_id, name) tuples
    authors_raw = db.session.query(distinct(Post.author_id), User.name)\
        .outerjoin(User).filter(*filters).all()

    # Return a list of dicts with the author_id and display name for each author
    return [{'value':auth_id, 'name':auth_name} for (auth_id, auth_name) in authors_raw]


# Get all posts matching the publish year, publish month, and author parameters
# Any argument=0 means that all values for that category are matched.
# Calling without arguments returns all posts in the db
def archive_posts(year=0, month=0, author_id=0):
    base_query = Post.query

    # Get the query filters for the given parameters. 0 values will result
    # in an empty string in the filters list which will not affect the query
    filters = [year_filter(year), month_filter(month), author_filter(author_id)]

    # Query the db for posts matching the year, month, and author parameters.
    # Returns a list of Post objects
    return base_query.filter(*filters)


# Get all unique years, months, and authors from the db that match the 
# given parameters. Used to provide select options for the archive page 
# based on what is already selected. Any argument=0 means that all values 
# for that category are matched. Calling without arguments returns all 
# distinct years, months, and authors in the db
def archive_options(year=0, month=0, author_id=0):
    # Get the unique years, months, and authors that match the given 
    # parameters. These are lists of dicts with {'value', 'name'} for
    # each option, i.e. months = [{'value':2, 'name':February}, ...]
    years = year_options(month, author_id)
    months = month_options(year, author_id)
    authors = author_options(year, month)

    # Store all options in a dict, with each key corresponding to a list
    # of sub-dicts, where each sub-dicts represent an option  
    options = {
        'year': years,
        'month': months,
        'author': authors
    }

    # Add an option for 'Any value' to each category
    any_choice = {'value': 0, 'name':'All'}
    for option in options.values():
        option.insert(0, any_choice)

    return options


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


# Create a couple fake accounts and articles
@bp.route("/seed/")
def seed():

    # Total number of posts to make and how much to vary the pub_date of
    # each post. These constants are only declared inside seed function 
    # because this is just intended as a tester function and isn't related
    # to the rest of the site
    posts_to_make = 30
    time_diff = timedelta(days=15)

    # Check that we're not blowing up our own database with this function
    post_count = Post.query.count()
    if (post_count > 200):
        flash("Too many posts. Bailing.")
        return redirect(url_for('index'))

    # Example users
    users = [
        {'email':"fakeemail@example.com", 'password':"password", 'name':"Joe"},
        {'email':"anotherlongfakeemail@example.com", 'password':"password", 'name':"Sawyer"},
        {'email':"longemailsaretheworst@example.com", 'password':"password", 'name':"Danielle"},
        {'email':"longemailexample@example.com", 'password':"password", 'name':"Logan"},
        {'email':"tomsemail@example.com", 'password':"password", 'name':"Tom"},
        {'email':"terrysemail@example.com", 'password':"password", 'name':"Terry"},
        {'email':"rachelsemail@example.com", 'password':"password", 'name':"Rachel"},
        {'email':"paulsemail@example.com", 'password':"password", 'name':"Paul"},
        {'email':"susiesemail@example.com", 'password':"password", 'name':"Susie"},
        {'email':"ryansemail@example.com", 'password':"password", 'name':"Ryan"},
        {'email':"cathysemail@example.com", 'password':"password", 'name':"Cathy"},
    ]

    # Example post content
    posts = [
        "An pericula mediocritatem necessitatibus pri, velit falli deterruisset in nec, at eum porro nobis. Est inani mollis suscipiantur ex, his in tale oblique accusamus, quod consulatu mea at. Mucius alienum delicata te vix, probo phaedrum salutatus vis no. Mazim laudem perpetua ius ad. Quis definitiones est id, accusata constituto honestatis mei id, in eos persius tincidunt expeten"
        "Tacimates euripidis usu et, in ocurreret sententiae reprehendunt qui, id molestie laboramus vix. Omnes albucius constituto sed et, at nec viderer labores oportere. Cu nostrud lucilius corrumpit usu, est solet tacimates consulatu id. Usu eu consul numquam saperet."
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
        
        # Commit db changes
        db.session.commit()

        # Grab the user id
        user_entry = User.query.filter_by(email=user['email']).one_or_none()
        user['id'] = user_entry.id

    # Store the current date to calculate varying fake publish dates for 
    # the new fake posts
    now = datetime.utcnow()

    # Create blog posts, decreasing the pub_date every time to create some variety
    for post_num in range(posts_to_make):
        # Rotate through author_id's, publishing every post from a new author
        # until we run out of made up authors
        author_id = users[post_num % len(users)]['id']

        # Rotate through posts, publishing every post with new content
        # until we run out of posts, then loop back around
        post = posts[post_num % len(posts)]

        # Calculate the publish date. This is done just to provide some
        # variety and make the archive more interesting
        pub_date = now - time_diff * post_num

        # Make the title of each post based on the current post count
        title = "Post Number " + str(post_count + posts_to_make - post_num)

        # Add the post to the database
        add_post(title, post, author_id, pub_date)

    # Commit db changes
    db.session.commit()

    # Send them to the homepage
    flash('Lots of new posts!')
    return redirect(url_for('index'))