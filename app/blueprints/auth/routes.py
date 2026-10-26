"""Registered-account pages: credentials, verification, recovery, profile."""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models.user import User, Profile
from app.services.auth_service import AuthService
from app.services.wiki_service import WikiService
from app.blueprints.auth.forms import (
    LoginForm, RegisterForm, ForgotPasswordForm, ResetPasswordForm, EditProfileForm
)

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """Register a new user account."""
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
        
    form = RegisterForm()
    if form.validate_on_submit():
        user = AuthService.register_user(
            username=form.username.data,
            email=form.email.data,
            password=form.password.data
        )
        flash('Account created successfully! A verification email has been simulated.', 'success')
        # The current product uses a simulated verification step. A deployed
        # email flow would keep the same route boundary but send a signed,
        # expiring verification token instead.
        login_user(user)
        return redirect(url_for('auth.verify_prompt'))
        
    return render_template('auth/register.html', form=form)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Log in an existing user."""
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
        
    form = LoginForm()
    if form.validate_on_submit():
        user = AuthService.authenticate_user(
            email_or_username=form.email_or_username.data,
            password=form.password.data
        )
        if user:
            login_user(user, remember=form.remember_me.data)
            flash(f'Welcome back, {user.username}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.home'))
        else:
            flash('Invalid username/email or password.', 'danger')
            
    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    """Log out the current user."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('main.home'))


@auth_bp.route('/verify-prompt')
@login_required
def verify_prompt():
    """Show email verification helper prompt."""
    if current_user.is_verified:
        return redirect(url_for('main.home'))
    return render_template('auth/verify_prompt.html')


@auth_bp.route('/verify')
@login_required
def verify():
    """Simulate user verifying their email."""
    if AuthService.verify_email(current_user.id):
        flash('Email verified successfully! Welcome to TerraVault.', 'success')
    else:
        flash('Verification failed.', 'danger')
    return redirect(url_for('main.home'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    """Request a password reset link."""
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
        
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            flash('A password reset link has been simulated and sent to your email.', 'info')
            # This is a demonstration reset flow. Real deployments must issue
            # a short-lived, unguessable reset token rather than expose an ID.
            # (In a real system, you would generate a secure cryptographic token)
            return redirect(url_for('auth.reset_password', user_id=user.id))
        else:
            flash('Email address not found.', 'warning')
            
    return render_template('auth/forgot_password.html', form=form)


@auth_bp.route('/reset-password/<int:user_id>', methods=['GET', 'POST'])
def reset_password(user_id):
    """Reset user password using the simulated link."""
    user = User.query.get_or_444(user_id) if hasattr(User, 'query') else User.query.get(user_id)
    if not user:
        flash('Invalid reset request.', 'danger')
        return redirect(url_for('auth.login'))
        
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been reset successfully. You can now log in.', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template('auth/reset_password.html', form=form, user=user)


@auth_bp.route('/profile/<username>')
def profile(username):
    """View a user profile with achievements, bookmarks, and history."""
    user = User.query.filter_by(username=username).first_or_404()
    
    bookmarks = []
    history = []
    if current_user.is_authenticated and current_user.id == user.id:
        bookmarks = WikiService.get_user_bookmarks(user.id)
        history = WikiService.get_reading_history(user.id)
        
    # Calculate simple gamification achievements based on reputation
    achievements = []
    if user.reputation >= 1000:
        achievements.append({'name': 'Legend', 'desc': 'Attained 1,000+ reputation points.'})
    if user.reputation >= 100:
        achievements.append({'name': 'Explorer', 'desc': 'Engaged with 100+ points on articles.'})
    if len(user.articles) >= 10:
        achievements.append({'name': 'Scholar', 'desc': 'Published 10+ professional articles.'})
    elif len(user.articles) >= 1:
        achievements.append({'name': 'Contributor', 'desc': 'Published your first encyclopedia article.'})

    return render_template('auth/profile.html', user=user, bookmarks=bookmarks, 
                           history=history, achievements=achievements)


@auth_bp.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    """Modify the current user profile metadata."""
    form = EditProfileForm()
    profile_obj = current_user.profile
    
    # Fallback to create profile if not present
    if not profile_obj:
        profile_obj = Profile(user_id=current_user.id)
        db.session.add(profile_obj)
        db.session.commit()
        
    if form.validate_on_submit():
        profile_obj.bio = form.bio.data
        profile_obj.location = form.location.data
        profile_obj.website = form.website.data
        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('auth.profile', username=current_user.username))
        
    elif request.method == 'GET':
        form.bio.data = profile_obj.bio
        form.location.data = profile_obj.location
        form.website.data = profile_obj.website
        
    return render_template('auth/edit_profile.html', form=form)
