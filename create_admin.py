from app import app, db
from models import User

def create_admin_user(username, password):
    with app.app_context():
        # Check if user already exists
        user = User.query.filter_by(username=username).first()
        if user:
            print(f"User {username} already exists")
            # Update password and admin status
            user.set_password(password)
            user.is_admin = True
        else:
            # Create new admin user
            user = User(username=username, is_admin=True)
            user.set_password(password)
            db.session.add(user)
        
        db.session.commit()
        print(f"Admin user {username} has been created/updated successfully!")
