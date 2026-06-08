from functools import wraps

from flask import Blueprint, redirect, render_template, request, session, url_for, flash

from .extensions import db
from .models import User

bp = Blueprint('auth', __name__)

ROLE_HOME = {'admin': 'admin.dashboard', 'teacher': 'teacher.session', 'student': 'student.scan'}


def current_user():
    username = session.get('username')
    if not username:
        return None
    return db.session.get(User, username)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for('auth.login'))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for('auth.login'))
            if user.role != role:
                return redirect(url_for(ROLE_HOME.get(user.role, 'auth.login')))
            return view(*args, **kwargs)
        return wrapped
    return decorator


@bp.route('/')
def index():
    user = current_user()
    if user:
        return redirect(url_for(ROLE_HOME.get(user.role, 'auth.login')))
    return redirect(url_for('auth.login'))


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '').strip()
        if not username or not password:
            flash('Enter username and password', 'err')
            return render_template('login.html')
        user = db.session.get(User, username)
        if not user or (user.password and user.password != password):
            flash('Invalid credentials', 'err')
            return render_template('login.html')
        session.clear()
        session['username'] = user.username
        return redirect(url_for(ROLE_HOME.get(user.role, 'auth.login')))
    if current_user():
        return redirect(url_for(ROLE_HOME.get(current_user().role, 'auth.login')))
    return render_template('login.html')


@bp.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return redirect(url_for('auth.login'))
