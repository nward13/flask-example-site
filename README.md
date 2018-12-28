# Nick Ward Code Challenge
Thanks for checking out my code challenge. This ReadMe contains some info about design choices, features, and how to run the server and use the site.

## Tasks
- Create an about me page and link to it in the nav
- Create a create blog post page

    - a post must have a title
    - the post itelf must be at least 10 characters long (yes totally arbitrary :-) )

- Update the index page to list all blog posts (showing 10 per page)
- Add archive listing page that limits the results to a specific month/year

## Requirements

- You will need to install docker (https://store.docker.com/search?offering=community&platform=desktop&q=&type=edition)
- If you are running on windows the make commands won't work.  You will have to manually run the commands found in Makefile
- If you are running on Linux, you may have to run all make commands as super user

## Where is the code?

Main.py contains the logic to initialize the app and database and to register the app blueprints, but most of the logic is contained in the auth blueprint (login, create new user, require login, etc.) and the blog blueprint, which handles all of the logic for creating, viewing, and sorting blog posts.

## How to start the server

    $ make build -- only needed the first time you run things
    $ make up

## How to stop and reset the database

    $ make down
    $ make up

**NOTE** running make down will blow away your database!

## How to regenerate the db schema

    $ make up
    $ make dump-schema -- separate terminal

## How to access the server from your browser
- localhost (no port should be specified)


# What does the site do
I was a bit uncertain whether this was intended to be my own blog or a blog for everyone, so I included some features from both. The about "About Nick" page contains some basic information about me and some pictures. The rest of the site is intended to be a blog for everyone. Here are some things you can do with it:

## Login / Register a New User
There are no users by default, but you can create a new account by following the 'Create an account' link from the login page. Once you register, you will be logged in and able to create blog posts.

## Create Blog Posts
After creating an account or loggin in, you can go to the 'Create' page to make a new blog post. If you just want to see how a group of posts appear on the site, see 'Seed the Blog' below.

## Seed the Blog
At the bottom of the page (from any page on the site), you can click the 'Seed the blog' link to automatically create three new users and 20 new posts from those users. The point of this is just to make it easy to see how the site acts with multiple posts from different users and publish times. The publish dates of these "seed" posts are also varied to make the archive page a bit more interesting.

## Viewing blog posts
Everyone's blog posts will show up on the home page with the most recent posts first and 10 posts per page. You can go to the Archives page to view blog posts in a more organized way.

## Authors
The 'Authors' page lists all of the authors who have contricuted to the blog. You can see how many posts each author has made and link to an information page about them by following the 'More about this author' link. This information page lists their contact information and recent posts, as well as linking to the archives page, where you can see all of their blog posts.

## Archives
The Archives page allows you to view blog posts by Author, Month (for posts in 2018), and Year. For each 'Sort By' option, the secondary options are filled in with all of the unique values that currently exist in the database.


