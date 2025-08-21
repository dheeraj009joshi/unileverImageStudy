from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from models.user import User
from forms.auth import LoginForm, RegistrationForm, PasswordResetRequestForm, PasswordResetForm, ProfileUpdateForm
from datetime import datetime

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login route."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        username_or_email = form.username_or_email.data
        print(f"Login attempt for: {username_or_email}")  # Debug
        
        # Try to find user by username first, then by email
        user = User.objects(username=username_or_email).first()
        if not user:
            user = User.objects(email=username_or_email).first()
        
        print(f"User found: {user is not None}")  # Debug
        if user:
            print(f"Password check result: {user.check_password(form.password.data)}")  # Debug
        if user and user.check_password(form.password.data):
            # Make session permanent for long-term login
            session.permanent = True
            login_user(user, remember=form.remember_me.data)
            user.last_login = datetime.utcnow()
            user.save()
            
            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('dashboard.index')
            return redirect(next_page)
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('auth/login.html', title='Sign In', form=form)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            name=form.name.data,
            phone=form.phone.data or None,
            date_of_birth=form.date_of_birth.data or None
        )
        user.set_password(form.password.data)
        user.save()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html', title='Register', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    """User logout route."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile management route."""
    form = ProfileUpdateForm(original_email=current_user.email)
    
    if form.validate_on_submit():
        current_user.name = form.name.data
        current_user.email = form.email.data
        current_user.phone = form.phone.data or None
        current_user.date_of_birth = form.date_of_birth.data or None
        current_user.updated_at = datetime.utcnow()
        current_user.save()
        
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('auth.profile'))
    elif request.method == 'GET':
        form.name.data = current_user.name
        form.email.data = current_user.email
        form.phone.data = current_user.phone
        form.date_of_birth.data = current_user.date_of_birth
    
    return render_template('auth/profile.html', title='Profile', form=form)

@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    """Change password route."""
    form = PasswordResetForm()
    
    if form.validate_on_submit():
        current_user.set_password(form.password.data)
        current_user.updated_at = datetime.utcnow()
        current_user.save()
        
        flash('Password changed successfully!', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('auth/change_password.html', title='Change Password', form=form)

@auth_bp.route('/reset-password-request', methods=['GET', 'POST'])
def reset_password_request():
    """Password reset request route."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    form = PasswordResetRequestForm()
    if form.validate_on_submit():
        user = User.objects(email=form.email.data).first()
        if user:
            # In a production environment, send email with reset token
            # For now, just show a message
            flash('If an account with that email exists, you will receive a password reset email.', 'info')
        else:
            # Don't reveal if email exists or not
            flash('If an account with that email exists, you will receive a password reset email.', 'info')
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password_request.html', title='Reset Password', form=form)

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Password reset with token route."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    
    # In a production environment, validate the token
    # For now, just show the form
    form = PasswordResetForm()
    
    if form.validate_on_submit():
        # In production, find user by token and update password
        flash('Password has been reset successfully!', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', title='Reset Password', form=form)
