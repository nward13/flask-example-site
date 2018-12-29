# coding: utf-8

import calendar
from itertools import chain
from datetime import datetime, timedelta
from flask import Blueprint, flash, Flask, redirect, render_template, request, url_for
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

# Number of posts for each page across the site (i.e. main blog, archives, etc.)
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
        (sort_by_values['month'], 'Month (in ' + str(datetime.now().year) + ')'), 
        (sort_by_values['year'], 'Year')
    ]
    sort_by = SelectField('Sort By:', choices=sort_choices)

    # These are the subfields. These are filled in dynamically based on
    # the unique values in the database for whicheve category the user
    # selects. i.e. if I want to view posts by author, I will only have
    # to choose from authors that have published posts
    sub_sort = SelectField('Include Results From:', choices=[], coerce=int)


# The index route. The main page of our site serves all of the blog posts,
# starting with the most recent posts and showing 10 per page
@bp.route("/", methods=['GET', 'POST'])
def index():

    # Get the current page from the request arguments
    page = request.args.get('page', default=1, type=int)

    # Get the most recent posts from the database, using paginate, our 
    # number of posts per page (10), and the current page (from request arguments)
    posts = Post.query.order_by(Post.pub_date.desc()).paginate(page, POSTS_PER_PAGE, False)

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
    user_posts_query = posts_by_auth_query(author_id)

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
    
    # Get each user that has made a post and the number of posts they 
    # have made. Returns a list of (User, post_count) tuples. In the
    # event that there are no matching records, returns an empty list
    post_counts = db.session.query(User, func.count(Post.author_id)) \
        .outerjoin(Post).filter(Post.id != None).group_by(Post.author_id).all()

    # Go from a list of (User, post_count) tuples to a list of objects
    # containing only the values we need to pass into our template 
    authors = [{'id':user.id, 'name':user.name, 'post_count':post_count} 
        for (user, post_count) in post_counts]

    # Render our authors template with the authors from the database
    return render_template('blog/authors.html', authors=authors)


# The archive of blog posts
@bp.route("/blog/archive/", methods=['GET', 'POST'])
def archive():
    form = ArchiveForm()

    if form.validate_on_submit():

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
            posts = posts_by_auth_query(sub_sort).limit(30).all()

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
            'name': User.query.get(author_id).name 
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

    # Get a list of all possible submission choices. Our js will decide
    # what options to show a user, but the form needs to know the possible
    # option values to validate. Take the sub_options dict of lists and
    # create a tuple from each object in the lists.
    # chain.from_iterable(sub_options.values()) is equivalent to the list comprehension
    # [choice for category in sub_options.values() for choice in category]
    sub_sort_choices = [(choice['value'], choice['name']) 
        for choice in chain.from_iterable(sub_options.values())]

    # Add our choices to the form
    form.sub_sort.choices.extend(sub_sort_choices)

    # Render our template without posts for a GET request and show the
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


# Returns a reused base query for posts by the given author
def posts_by_auth_query(author_id):
    return Post.query.filter_by(author_id=author_id)


# Create a couple fake accounts and articles
@bp.route("/seed/")
def seed():

    # Total number of posts to make and how much to vary the pub_date of
    # each post. These constants are only declared inside seed function 
    # because this is just intended as a tester function and isn't related
    # to the rest of the site
    posts_to_make = 20
    time_diff = timedelta(days=21)

    # Check that we're not blowing up our own database with this function
    post_count = Post.query.count()
    if (post_count > 200):
        flash("Too many posts. Bailing.")
        return redirect(url_for('index'))

    # Users
    users = [
        {'email':"fakeemail@example.com", 'password':"password", 'name':"Joe"},
        {'email':"anotherlongfakeemail@example.com", 'password':"password", 'name':"Sawyer"},
        {'email':"longemailsaretheworst@example.com", 'password':"password", 'name':"Danielle"},
        {'email':"longemailexample@example.com", 'password':"password", 'name':"Logan"},
    ]

    # Post content
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