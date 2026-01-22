"""
Authentication system for the panel
"""
import os
import hashlib
import secrets
from functools import wraps
from flask import request, jsonify, session

# Admin credentials from environment
ADMIN_USER = os.getenv('ADMIN_USER', 'admin')
ADMIN_PASS_HASH = hashlib.sha256(os.getenv('ADMIN_PASS', 'admin123').encode()).hexdigest()


def hash_password(password: str) -> str:
    """Hash password with SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against hash"""
    return hash_password(password) == password_hash


def login_required(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check session
        if 'user' not in session:
            # Check Authorization header
            auth = request.authorization
            if not auth or not verify_password(auth.password, ADMIN_PASS_HASH) or auth.username != ADMIN_USER:
                return jsonify({'success': False, 'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


def authenticate(username: str, password: str) -> bool:
    """Authenticate user"""
    return username == ADMIN_USER and verify_password(password, ADMIN_PASS_HASH)
