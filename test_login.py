#!/usr/bin/env python3
"""
Test script to debug login issues
"""

from mongoengine import connect
from models.user import User
import bcrypt

# Connect to database
connect('iped_system', host='mongodb://localhost:27017/')

def test_user_creation():
    """Create a test user if none exists."""
    
    # Check if user exists
    existing_user = User.objects(username="dlovej009").first()
    
    if existing_user:
        print(f"User exists: {existing_user.username}")
        print(f"User ID: {existing_user._id}")
        print(f"Password hash: {existing_user.password_hash[:50]}...")
        
        # Test password
        test_password = "password123"  # Change this to your actual password
        is_valid = existing_user.check_password(test_password)
        print(f"Password '{test_password}' is valid: {is_valid}")
        
        return existing_user
    else:
        print("Creating new test user...")
        
        # Create test user
        user = User(
            username="dlovej009",
            email="test@example.com",
            name="Test User"
        )
        user.set_password("password123")
        user.save()
        
        print(f"User created with ID: {user._id}")
        return user

def test_password_check():
    """Test password checking functionality."""
    
    user = User.objects(username="dlovej009").first()
    if not user:
        print("No user found!")
        return
    
    # Test various passwords
    test_passwords = ["password123", "wrongpassword", "dlovej009"]
    
    for password in test_passwords:
        is_valid = user.check_password(password)
        print(f"Password '{password}': {'✓ Valid' if is_valid else '✗ Invalid'}")

if __name__ == "__main__":
    print("Testing user creation and password checking...")
    user = test_user_creation()
    print("\nTesting password validation...")
    test_password_check()
