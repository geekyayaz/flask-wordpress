from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, PasswordField, SelectField, BooleanField, HiddenField
from wtforms.validators import DataRequired, Email, Length, EqualTo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import secrets
from functools import wraps
import re
from slugify import slugify

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cms.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize extensions
db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# User loader for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(50))
    last_name = db.Column(db.String(50))
    role = db.Column(db.String(20), default='subscriber')
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    posts = db.relationship('Post', backref='author', lazy=True)
    comments = db.relationship('Comment', backref='author', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def has_permission(self, permission):
        permissions = {
            'subscriber': ['read'],
            'author': ['read', 'create_post', 'edit_own_post'],
            'editor': ['read', 'create_post', 'edit_post', 'publish'],
            'admin': ['all']
        }
        user_perms = permissions.get(self.role, [])
        return permission in user_perms or 'all' in user_perms
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.username

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    posts = db.relationship('Post', backref='category', lazy=True)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    
    def __repr__(self):
        return f'<Tag {self.name}>'

# Association table for many-to-many relationship between posts and tags
post_tags = db.Table('post_tags',
    db.Column('post_id', db.Integer, db.ForeignKey('post.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    content = db.Column(db.Text, nullable=False)
    excerpt = db.Column(db.Text)
    status = db.Column(db.String(20), default='draft')  # draft, published, private
    post_type = db.Column(db.String(20), default='post')  # post, page
    featured_image = db.Column(db.String(255))
    meta_title = db.Column(db.String(200))
    meta_description = db.Column(db.Text)
    view_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = db.Column(db.DateTime)
    
    # Foreign Keys
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    
    # Relationships
    comments = db.relationship('Comment', backref='post', lazy=True, cascade='all, delete-orphan')
    tags = db.relationship('Tag', secondary=post_tags, lazy='subquery',
                          backref=db.backref('posts', lazy=True))
    
    def __repr__(self):
        return f'<Post {self.title}>'
    
    @property
    def is_published(self):
        return self.status == 'published'
    
    def generate_excerpt(self, length=150):
        if self.excerpt:
            return self.excerpt
        # Strip HTML tags and truncate
        clean_content = re.sub('<[^<]+?>', '', self.content)
        return clean_content[:length] + '...' if len(clean_content) > length else clean_content

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    author_name = db.Column(db.String(100))
    author_email = db.Column(db.String(120))
    status = db.Column(db.String(20), default='pending')  # pending, approved, spam
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Foreign Keys
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Optional for logged-in users

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    
    @staticmethod
    def get_setting(key, default=None):
        setting = Setting.query.filter_by(key=key).first()
        return setting.value if setting else default
    
    @staticmethod
    def set_setting(key, value, description=None):
        setting = Setting.query.filter_by(key=key).first()
        if setting:
            setting.value = value
        else:
            setting = Setting(key=key, value=value, description=description)
            db.session.add(setting)
        db.session.commit()

# Forms
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    first_name = StringField('First Name')
    last_name = StringField('Last Name')
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Repeat Password', 
                            validators=[DataRequired(), EqualTo('password')])

class PostForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired(), Length(max=200)])
    content = TextAreaField('Content', validators=[DataRequired()])
    excerpt = TextAreaField('Excerpt')
    status = SelectField('Status', choices=[('draft', 'Draft'), ('published', 'Published'), ('private', 'Private')])
    post_type = SelectField('Type', choices=[('post', 'Post'), ('page', 'Page')])
    category_id = SelectField('Category', coerce=int)
    tags = StringField('Tags (comma separated)')
    featured_image = FileField('Featured Image', validators=[FileAllowed(['jpg', 'png', 'gif'])])
    meta_title = StringField('SEO Title', validators=[Length(max=200)])
    meta_description = TextAreaField('SEO Description')

class CommentForm(FlaskForm):
    content = TextAreaField('Comment', validators=[DataRequired()])
    author_name = StringField('Name', validators=[DataRequired()])
    author_email = StringField('Email', validators=[DataRequired(), Email()])

class CategoryForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Description')

class UserForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    first_name = StringField('First Name')
    last_name = StringField('Last Name')
    role = SelectField('Role', choices=[('subscriber', 'Subscriber'), ('author', 'Author'), 
                                       ('editor', 'Editor'), ('admin', 'Admin')])
    is_active = BooleanField('Active')

# Decorators
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.has_permission('all'):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def permission_required(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or not current_user.has_permission(permission):
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Template context processors
@app.context_processor
def inject_site_settings():
    return {
        'site_title': Setting.get_setting('site_title', 'My CMS'),
        'site_description': Setting.get_setting('site_description', 'A powerful content management system'),
        'recent_posts': Post.query.filter_by(status='published').order_by(Post.published_at.desc()).limit(5).all(),
        'categories': Category.query.all()
    }

# Public Routes
@app.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.filter_by(status='published', post_type='post')\
                     .order_by(Post.published_at.desc())\
                     .paginate(page=page, per_page=10, error_out=False)
    return render_template('index.html', posts=posts)

@app.route('/post/<slug>')
def post_detail(slug):
    post = Post.query.filter_by(slug=slug, status='published').first_or_404()
    
    # Increment view count
    post.view_count += 1
    db.session.commit()
    
    # Get approved comments
    comments = Comment.query.filter_by(post_id=post.id, status='approved')\
                           .order_by(Comment.created_at.desc()).all()
    
    comment_form = CommentForm()
    return render_template('post_detail.html', post=post, comments=comments, comment_form=comment_form)

@app.route('/page/<slug>')
def page_detail(slug):
    page = Post.query.filter_by(slug=slug, status='published', post_type='page').first_or_404()
    return render_template('page_detail.html', page=page)

@app.route('/category/<slug>')
def category_posts(slug):
    category = Category.query.filter_by(slug=slug).first_or_404()
    page = request.args.get('page', 1, type=int)
    posts = Post.query.filter_by(category=category, status='published', post_type='post')\
                     .order_by(Post.published_at.desc())\
                     .paginate(page=page, per_page=10, error_out=False)
    return render_template('category_posts.html', category=category, posts=posts)

@app.route('/search')
def search():
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    
    if query:
        posts = Post.query.filter(
            Post.status == 'published',
            Post.post_type == 'post',
            db.or_(
                Post.title.contains(query),
                Post.content.contains(query)
            )
        ).order_by(Post.published_at.desc())\
         .paginate(page=page, per_page=10, error_out=False)
    else:
        posts = None
    
    return render_template('search.html', posts=posts, query=query)

# Comment submission
@app.route('/post/<slug>/comment', methods=['POST'])
def add_comment(slug):
    post = Post.query.filter_by(slug=slug, status='published').first_or_404()
    form = CommentForm()
    
    if form.validate_on_submit():
        comment = Comment(
            content=form.content.data,
            post_id=post.id
        )
        
        if current_user.is_authenticated:
            comment.author_id = current_user.id
            comment.author_name = current_user.full_name
            comment.author_email = current_user.email
        else:
            comment.author_name = form.author_name.data
            comment.author_email = form.author_email.data
        
        db.session.add(comment)
        db.session.commit()
        flash('Your comment has been submitted and is awaiting approval.', 'success')
    
    return redirect(url_for('post_detail', slug=slug))

# Authentication Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data) and user.is_active:
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('admin_dashboard')
            return redirect(next_page)
        flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already exists', 'error')
            return render_template('auth/register.html', form=form)
        
        if User.query.filter_by(email=form.email.data).first():
            flash('Email already registered', 'error')
            return render_template('auth/register.html', form=form)
        
        user = User(
            username=form.username.data,
            email=form.email.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful', 'success')
        return redirect(url_for('login'))
    
    return render_template('auth/register.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Admin Routes
@app.route('/admin')
@login_required
def admin_dashboard():
    stats = {
        'total_posts': Post.query.count(),
        'published_posts': Post.query.filter_by(status='published').count(),
        'total_users': User.query.count(),
        'total_comments': Comment.query.count(),
        'pending_comments': Comment.query.filter_by(status='pending').count()
    }
    
    recent_posts = Post.query.order_by(Post.created_at.desc()).limit(5).all()
    recent_comments = Comment.query.order_by(Comment.created_at.desc()).limit(5).all()
    
    return render_template('admin/dashboard.html', stats=stats, 
                         recent_posts=recent_posts, recent_comments=recent_comments)

# Posts Management
@app.route('/admin/posts')
@login_required
@permission_required('create_post')
def admin_posts():
    page = request.args.get('page', 1, type=int)
    
    query = Post.query
    if not current_user.has_permission('edit_post'):
        query = query.filter_by(author_id=current_user.id)
    
    posts = query.order_by(Post.created_at.desc())\
                 .paginate(page=page, per_page=20, error_out=False)
    
    return render_template('admin/posts.html', posts=posts)

@app.route('/admin/posts/new', methods=['GET', 'POST'])
@login_required
@permission_required('create_post')
def admin_post_new():
    form = PostForm()
    form.category_id.choices = [(0, 'No Category')] + [(c.id, c.name) for c in Category.query.all()]
    
    if form.validate_on_submit():
        # Generate slug
        slug = slugify(form.title.data)
        counter = 1
        original_slug = slug
        while Post.query.filter_by(slug=slug).first():
            slug = f"{original_slug}-{counter}"
            counter += 1
        
        post = Post(
            title=form.title.data,
            slug=slug,
            content=form.content.data,
            excerpt=form.excerpt.data,
            status=form.status.data,
            post_type=form.post_type.data,
            meta_title=form.meta_title.data,
            meta_description=form.meta_description.data,
            author_id=current_user.id
        )
        
        if form.category_id.data and form.category_id.data != 0:
            post.category_id = form.category_id.data
        
        # Handle featured image upload
        if form.featured_image.data:
            filename = secure_filename(form.featured_image.data.filename)
            filename = f"{secrets.token_hex(8)}_{filename}"
            form.featured_image.data.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            post.featured_image = filename
        
        # Handle tags
        if form.tags.data:
            tag_names = [t.strip() for t in form.tags.data.split(',') if t.strip()]
            for tag_name in tag_names:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name, slug=slugify(tag_name))
                    db.session.add(tag)
                post.tags.append(tag)
        
        if post.status == 'published':
            post.published_at = datetime.utcnow()
        
        db.session.add(post)
        db.session.commit()
        
        flash('Post created successfully', 'success')
        return redirect(url_for('admin_posts'))
    
    return render_template('admin/post_form.html', form=form, title='New Post')

@app.route('/admin/posts/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def admin_post_edit(id):
    post = Post.query.get_or_404(id)
    
    # Check permissions
    if not current_user.has_permission('edit_post') and post.author_id != current_user.id:
        abort(403)
    
    form = PostForm(obj=post)
    form.category_id.choices = [(0, 'No Category')] + [(c.id, c.name) for c in Category.query.all()]
    
    if request.method == 'GET':
        form.category_id.data = post.category_id or 0
        form.tags.data = ', '.join([tag.name for tag in post.tags])
    
    if form.validate_on_submit():
        # Update slug if title changed
        if post.title != form.title.data:
            slug = slugify(form.title.data)
            counter = 1
            original_slug = slug
            while Post.query.filter(Post.slug == slug, Post.id != post.id).first():
                slug = f"{original_slug}-{counter}"
                counter += 1
            post.slug = slug
        
        post.title = form.title.data
        post.content = form.content.data
        post.excerpt = form.excerpt.data
        post.status = form.status.data
        post.post_type = form.post_type.data
        post.meta_title = form.meta_title.data
        post.meta_description = form.meta_description.data
        
        if form.category_id.data and form.category_id.data != 0:
            post.category_id = form.category_id.data
        else:
            post.category_id = None
        
        # Handle featured image upload
        if form.featured_image.data:
            # Delete old image
            if post.featured_image:
                old_path = os.path.join(app.config['UPLOAD_FOLDER'], post.featured_image)
                if os.path.exists(old_path):
                    os.remove(old_path)
            
            filename = secure_filename(form.featured_image.data.filename)
            filename = f"{secrets.token_hex(8)}_{filename}"
            form.featured_image.data.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            post.featured_image = filename
        
        # Handle tags
        post.tags.clear()
        if form.tags.data:
            tag_names = [t.strip() for t in form.tags.data.split(',') if t.strip()]
            for tag_name in tag_names:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name, slug=slugify(tag_name))
                    db.session.add(tag)
                post.tags.append(tag)
        
        # Update published date if status changed to published
        if post.status == 'published' and not post.published_at:
            post.published_at = datetime.utcnow()
        
        db.session.commit()
        flash('Post updated successfully', 'success')
        return redirect(url_for('admin_posts'))
    
    return render_template('admin/post_form.html', form=form, post=post, title='Edit Post')

@app.route('/admin/posts/<int:id>/delete', methods=['POST'])
@login_required
def admin_post_delete(id):
    post = Post.query.get_or_404(id)
    
    # Check permissions
    if not current_user.has_permission('edit_post') and post.author_id != current_user.id:
        abort(403)
    
    # Delete featured image
    if post.featured_image:
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], post.featured_image)
        if os.path.exists(image_path):
            os.remove(image_path)
    
    db.session.delete(post)
    db.session.commit()
    flash('Post deleted successfully', 'success')
    return redirect(url_for('admin_posts'))

# Categories Management
@app.route('/admin/categories')
@login_required
@permission_required('edit_post')
def admin_categories():
    categories = Category.query.order_by(Category.name).all()
    return render_template('admin/categories.html', categories=categories)

@app.route('/admin/categories/new', methods=['GET', 'POST'])
@login_required
@permission_required('edit_post')
def admin_category_new():
    form = CategoryForm()
    
    if form.validate_on_submit():
        slug = slugify(form.name.data)
        counter = 1
        original_slug = slug
        while Category.query.filter_by(slug=slug).first():
            slug = f"{original_slug}-{counter}"
            counter += 1
        
        category = Category(
            name=form.name.data,
            slug=slug,
            description=form.description.data
        )
        
        db.session.add(category)
        db.session.commit()
        flash('Category created successfully', 'success')
        return redirect(url_for('admin_categories'))
    
    return render_template('admin/category_form.html', form=form, title='New Category')

@app.route('/admin/categories/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@permission_required('edit_post')
def admin_category_edit(id):
    category = Category.query.get_or_404(id)
    form = CategoryForm(obj=category)
    
    if form.validate_on_submit():
        if category.name != form.name.data:
            slug = slugify(form.name.data)
            counter = 1
            original_slug = slug
            while Category.query.filter(Category.slug == slug, Category.id != category.id).first():
                slug = f"{original_slug}-{counter}"
                counter += 1
            category.slug = slug
        
        category.name = form.name.data
        category.description = form.description.data
        
        db.session.commit()
        flash('Category updated successfully', 'success')
        return redirect(url_for('admin_categories'))
    
    return render_template('admin/category_form.html', form=form, category=category, title='Edit Category')

@app.route('/admin/categories/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('edit_post')
def admin_category_delete(id):
    category = Category.query.get_or_404(id)
    
    # Check if category has posts
    if category.posts:
        flash('Cannot delete category with existing posts', 'error')
        return redirect(url_for('admin_categories'))
    
    db.session.delete(category)
    db.session.commit()
    flash('Category deleted successfully', 'success')
    return redirect(url_for('admin_categories'))

# Comments Management
@app.route('/admin/comments')
@login_required
@permission_required('edit_post')
def admin_comments():
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', 'all')
    
    query = Comment.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    comments = query.order_by(Comment.created_at.desc())\
                   .paginate(page=page, per_page=20, error_out=False)
    
    return render_template('admin/comments.html', comments=comments, status_filter=status_filter)

@app.route('/admin/comments/<int:id>/approve', methods=['POST'])
@login_required
@permission_required('edit_post')
def admin_comment_approve(id):
    comment = Comment.query.get_or_404(id)
    comment.status = 'approved'
    db.session.commit()
    flash('Comment approved', 'success')
    return redirect(url_for('admin_comments'))

@app.route('/admin/comments/<int:id>/spam', methods=['POST'])
@login_required
@permission_required('edit_post')
def admin_comment_spam(id):
    comment = Comment.query.get_or_404(id)
    comment.status = 'spam'
    db.session.commit()
    flash('Comment marked as spam', 'success')
    return redirect(url_for('admin_comments'))

@app.route('/admin/comments/<int:id>/delete', methods=['POST'])
@login_required
@permission_required('edit_post')
def admin_comment_delete(id):
    comment = Comment.query.get_or_404(id)
    db.session.delete(comment)
    db.session.commit()
    flash('Comment deleted', 'success')
    return redirect(url_for('admin_comments'))

# Users Management
@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    page = request.args.get('page', 1, type=int)
    users = User.query.order_by(User.created_at.desc())\
                     .paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_user_new():
    form = UserForm()
    
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already exists', 'error')
            return render_template('admin/user_form.html', form=form, title='New User')
        
        if User.query.filter_by(email=form.email.data).first():
            flash('Email already registered', 'error')
            return render_template('admin/user_form.html', form=form, title='New User')
        
        user = User(
            username=form.username.data,
            email=form.email.data,
            first_name=form.first_name.data,
            last_name=form.last_name.data,
            role=form.role.data,
            is_active=form.is_active.data
        )
        user.set_password('password123')  # Default password
        
        db.session.add(user)
        db.session.commit()
        flash('User created successfully. Default password is "password123"', 'success')
        return redirect(url_for('admin_users'))
    
    return render_template('admin/user_form.html', form=form, title='New User')

@app.route('/admin/users/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_user_edit(id):
    user = User.query.get_or_404(id)
    form = UserForm(obj=user)
    
    if form.validate_on_submit():
        if user.username != form.username.data and User.query.filter_by(username=form.username.data).first():
            flash('Username already exists', 'error')
            return render_template('admin/user_form.html', form=form, user=user, title='Edit User')
        
        if user.email != form.email.data and User.query.filter_by(email=form.email.data).first():
            flash('Email already registered', 'error')
            return render_template('admin/user_form.html', form=form, user=user, title='Edit User')
        
        user.username = form.username.data
        user.email = form.email.data
        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        user.role = form.role.data
        user.is_active = form.is_active.data
        
        db.session.commit()
        flash('User updated successfully', 'success')
        return redirect(url_for('admin_users'))
    
    return render_template('admin/user_form.html', form=form, user=user, title='Edit User')

@app.route('/admin/users/<int:id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_user_delete(id):
    user = User.query.get_or_404(id)
    
    if user.id == current_user.id:
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('admin_users'))
    
    # Reassign posts to current user or delete them
    for post in user.posts:
        post.author_id = current_user.id
    
    db.session.delete(user)
    db.session.commit()
    flash('User deleted successfully', 'success')
    return redirect(url_for('admin_users'))

# Settings Management
@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_settings():
    if request.method == 'POST':
        settings = [
            ('site_title', 'Site Title'),
            ('site_description', 'Site Description'),
            ('posts_per_page', 'Posts per page'),
            ('allow_comments', 'Allow comments'),
            ('comment_moderation', 'Comment moderation'),
        ]
        
        for key, description in settings:
            value = request.form.get(key, '')
            Setting.set_setting(key, value, description)
        
        flash('Settings updated successfully', 'success')
        return redirect(url_for('admin_settings'))
    
    # Get current settings
    current_settings = {}
    for setting in Setting.query.all():
        current_settings[setting.key] = setting.value
    
    return render_template('admin/settings.html', settings=current_settings)

# Media Management
@app.route('/admin/media')
@login_required
@permission_required('create_post')
def admin_media():
    uploads_dir = app.config['UPLOAD_FOLDER']
    files = []
    
    if os.path.exists(uploads_dir):
        for filename in os.listdir(uploads_dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                file_path = os.path.join(uploads_dir, filename)
                file_size = os.path.getsize(file_path)
                file_modified = datetime.fromtimestamp(os.path.getmtime(file_path))
                files.append({
                    'name': filename,
                    'size': file_size,
                    'modified': file_modified,
                    'url': url_for('static', filename=f'uploads/{filename}')
                })
    
    files.sort(key=lambda x: x['modified'], reverse=True)
    return render_template('admin/media.html', files=files)

@app.route('/admin/media/upload', methods=['POST'])
@login_required
@permission_required('create_post')
def admin_media_upload():
    if 'file' not in request.files:
        flash('No file selected', 'error')
        return redirect(url_for('admin_media'))
    
    file = request.files['file']
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('admin_media'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filename = f"{secrets.token_hex(8)}_{filename}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        flash('File uploaded successfully', 'success')
    else:
        flash('Invalid file type', 'error')
    
    return redirect(url_for('admin_media'))

@app.route('/admin/media/<filename>/delete', methods=['POST'])
@login_required
@permission_required('edit_post')
def admin_media_delete(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        flash('File deleted successfully', 'success')
    else:
        flash('File not found', 'error')
    
    return redirect(url_for('admin_media'))

# API Routes
@app.route('/api/posts')
def api_posts():
    page = request.args.get('page', 1, type=int)
    posts = Post.query.filter_by(status='published', post_type='post')\
                     .order_by(Post.published_at.desc())\
                     .paginate(page=page, per_page=10, error_out=False)
    
    return jsonify({
        'posts': [{
            'id': post.id,
            'title': post.title,
            'slug': post.slug,
            'excerpt': post.generate_excerpt(),
            'author': post.author.full_name,
            'published_at': post.published_at.isoformat() if post.published_at else None,
            'category': post.category.name if post.category else None,
            'tags': [tag.name for tag in post.tags]
        } for post in posts.items],
        'pagination': {
            'page': posts.page,
            'pages': posts.pages,
            'per_page': posts.per_page,
            'total': posts.total,
            'has_next': posts.has_next,
            'has_prev': posts.has_prev
        }
    })

@app.route('/api/posts/<slug>')
def api_post_detail(slug):
    post = Post.query.filter_by(slug=slug, status='published').first_or_404()
    
    return jsonify({
        'id': post.id,
        'title': post.title,
        'slug': post.slug,
        'content': post.content,
        'excerpt': post.generate_excerpt(),
        'author': post.author.full_name,
        'published_at': post.published_at.isoformat() if post.published_at else None,
        'category': post.category.name if post.category else None,
        'tags': [tag.name for tag in post.tags],
        'view_count': post.view_count,
        'meta_title': post.meta_title,
        'meta_description': post.meta_description
    })

# Utility functions
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# CLI Commands for initialization
@app.cli.command()
def init_db():
    """Initialize the database."""
    db.create_all()
    
    # Create default admin user
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@example.com',
            first_name='Admin',
            last_name='User',
            role='admin'
        )
        admin.set_password('admin123')
        db.session.add(admin)
    
    # Create default category
    if not Category.query.first():
        category = Category(
            name='General',
            slug='general',
            description='General posts'
        )
        db.session.add(category)
    
    # Create default settings
    default_settings = [
        ('site_title', 'My CMS', 'Website title'),
        ('site_description', 'A powerful content management system', 'Website description'),
        ('posts_per_page', '10', 'Number of posts per page'),
        ('allow_comments', 'true', 'Allow comments on posts'),
        ('comment_moderation', 'true', 'Moderate comments before publishing'),
    ]
    
    for key, value, description in default_settings:
        if not Setting.query.filter_by(key=key).first():
            setting = Setting(key=key, value=value, description=description)
            db.session.add(setting)
    
    # Create sample post
    if not Post.query.first():
        sample_post = Post(
            title='Welcome to Your New CMS',
            slug='welcome-to-your-new-cms',
            content='''<h2>Welcome to Your New Content Management System!</h2>
            
            <p>This is your first post. You can edit or delete it from the admin panel.</p>
            
            <h3>Getting Started</h3>
            <ul>
                <li>Login to the admin panel at <a href="/admin">/admin</a></li>
                <li>Create new posts and pages</li>
                <li>Manage categories and tags</li>
                <li>Customize your site settings</li>
            </ul>
            
            <p>Have fun building your website!</p>''',
            excerpt='Welcome to your new CMS! This is a sample post to get you started.',
            status='published',
            post_type='post',
            author_id=1,
            category_id=1,
            published_at=datetime.utcnow()
        )
        db.session.add(sample_post)
    
    db.session.commit()
    print('Database initialized successfully!')

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden_error(error):
    return render_template('errors/403.html'), 403

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

if __name__ == '__main__':
    app.run(debug=True)