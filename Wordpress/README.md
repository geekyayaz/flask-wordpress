# README.md
# Flask CMS - WordPress-like Content Management System

A complete content management system built with Flask, featuring user management, post creation, categories, comments, and an admin dashboard.

## Features

- **User Management**: Registration, login, role-based permissions
- **Content Creation**: Rich text editor, categories, tags, featured images
- **Admin Dashboard**: Complete backend interface for managing content
- **Comments System**: User comments with moderation
- **SEO Friendly**: Meta tags, clean URLs, sitemaps
- **Media Management**: File upload and organization
- **Responsive Design**: Bootstrap-based responsive templates
- **API Endpoints**: RESTful API for external integrations

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd flask-cms
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Initialize the database:
```bash
flask init-db
```

5. Run the application:
```bash
flask run
```

## Default Login

- Username: `admin`
- Password: `admin123`

## Project Structure

```
flask-cms/
├── app.py                 # Main application file
├── requirements.txt       # Python dependencies
├── cms.db                # SQLite database (created after init)
├── static/
│   └── uploads/          # Uploaded media files
└── templates/
    ├── base.html         # Base template
    ├── index.html        # Homepage
    ├── post_detail.html  # Single post view
    ├── auth/             # Authentication templates
    └── admin/            # Admin panel templates
```

## User Roles

- **Subscriber**: Can read posts and comment
- **Author**: Can create and edit own posts
- **Editor**: Can create, edit, and publish any post
- **Admin**: Full access to all features

## API Endpoints

- `GET /api/posts` - List all published posts
- `GET /api/posts/<slug>` - Get single post details

## Configuration

Key settings can be configured through the admin panel:
- Site title and description
- Posts per page
- Comment moderation settings

## Development

To add new features:

1. Create database models in `app.py`
2. Add forms for user input
3. Create routes and views
4. Design templates
5. Run migrations: `flask db migrate` and `flask db upgrade`

## Production Deployment

1. Set environment variables:
   - `SECRET_KEY`: Strong secret key
   - `DATABASE_URL`: Production database URL
   - `FLASK_ENV=production`

2. Use a production WSGI server like Gunicorn:
```bash
gunicorn app:app
```

3. Configure reverse proxy (Nginx) for static files and SSL

## License

MIT License