# Create default admin user
from app import User


admin = User.query.filter_by(username='admin').first()
if not admin:
    admin = User(
        username='admin', # type: ignore
        email='admin@example.com', # type: ignore
        first_name='Admin',
        last_name='User',
        role='admin'
    )
    admin.set_password('admin123')  # This sets the password