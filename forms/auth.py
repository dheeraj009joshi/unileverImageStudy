from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from models.user import User

class LoginForm(FlaskForm):
    """User login form."""
    username_or_email = StringField('Username or Email', validators=[DataRequired(), Length(min=3, max=100)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

class RegistrationForm(FlaskForm):
    """User registration form."""
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=50)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=100)])
    name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    phone = StringField('Phone (Optional)', validators=[Length(max=20)])
    date_of_birth = StringField('Date of Birth (Optional, YYYY-MM-DD)', validators=[Length(max=10)])
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        """Check if username is already taken."""
        user = User.objects(username=username.data).first()
        if user:
            raise ValidationError('Username already taken. Please choose a different one.')
    
    def validate_email(self, email):
        """Check if email is already registered."""
        user = User.objects(email=email.data).first()
        if user:
            raise ValidationError('Email already registered. Please use a different one.')

class PasswordResetRequestForm(FlaskForm):
    """Password reset request form."""
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

class PasswordResetForm(FlaskForm):
    """Password reset form."""
    password = PasswordField('New Password', validators=[
        DataRequired(),
        Length(min=8, message='Password must be at least 8 characters long')
    ])
    confirm_password = PasswordField('Confirm New Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    submit = SubmitField('Reset Password')

class ProfileUpdateForm(FlaskForm):
    """User profile update form."""
    name = StringField('Full Name', validators=[DataRequired(), Length(max=100)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=100)])
    phone = StringField('Phone (Optional)', validators=[Length(max=20)])
    date_of_birth = StringField('Date of Birth (Optional, YYYY-MM-DD)', validators=[Length(max=10)])
    submit = SubmitField('Update Profile')
    
    def __init__(self, original_email, *args, **kwargs):
        super(ProfileUpdateForm, self).__init__(*args, **kwargs)
        self.original_email = original_email
    
    def validate_email(self, email):
        """Check if email is already taken by another user."""
        if email.data != self.original_email:
            user = User.objects(email=email.data).first()
            if user:
                raise ValidationError('Email already registered. Please use a different one.')
