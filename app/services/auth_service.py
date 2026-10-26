"""Authentication and profile service functions shared by auth views."""

from app.extensions import db
from app.models.user import User, Profile, Role

class AuthService:
    """Encapsulates password checks and account/profile persistence."""
    @staticmethod
    def register_user(username, email, password):
        """Register a new user, create their profile, and assign default 'User' role."""
        # Find default User role
        user_role = Role.query.filter_by(name='User').first()
        if not user_role:
            # Fallback if roles aren't seeded yet
            user_role = Role(name='User', description='Default user role')
            db.session.add(user_role)
            db.session.commit()
            
        # Create user
        user = User(
            username=username,
            email=email,
            role_id=user_role.id
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        # Create profile
        profile = Profile(user_id=user.id)
        db.session.add(profile)
        db.session.commit()
        
        return user

    @staticmethod
    def authenticate_user(email_or_username, password):
        """Verify user credentials and return the user object or None."""
        user = User.query.filter(
            (User.email == email_or_username) | (User.username == email_or_username)
        ).first()
        
        if user and user.check_password(password):
            return user
        return None

    @staticmethod
    def verify_email(user_id):
        """Mark the user's email as verified."""
        user = User.query.get(user_id)
        if user:
            user.is_verified = True
            db.session.commit()
            return True
        return False

    @staticmethod
    def update_reputation(user_id, amount):
        """Add or subtract reputation points for a user."""
        user = User.query.get(user_id)
        if user:
            user.reputation += amount
            # Reputation cannot fall below 0
            if user.reputation < 0:
                user.reputation = 0
            db.session.commit()
            return user
        return None

    @staticmethod
    def check_user_permission(user, required_role):
        """Return True if user has the required permission level or higher."""
        if not user or not user.is_authenticated:
            return False
            
        role_hierarchy = {
            'Guest': 0,
            'User': 1,
            'Moderator': 2,
            'Admin': 3
        }
        
        user_role_name = user.role.name if user.role else 'User'
        user_level = role_hierarchy.get(user_role_name, 1)
        required_level = role_hierarchy.get(required_role, 1)
        
        return user_level >= required_level
