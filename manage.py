# FILE: manage.py
import os
import click
from getpass import getpass

from app import create_app
from app.extensions import db, migrate
from app.models import User

from werkzeug.security import generate_password_hash

# انتخاب کانفیگ از ENV یا پیش‌فرض
config_name = os.environ.get('FLASK_CONFIG')  # optional: 'dev'/'prod'/'test' or a full path/class
app = create_app(config_name)

# ---------------- CLI commands ----------------

@app.cli.command("create-db")
def create_db():
    """Create database tables."""
    with app.app_context():
        db.create_all()
        click.echo("Database tables created.")

@app.cli.command("drop-db")
@click.confirmation_option(prompt='Are you sure you want to DROP the database tables?')
def drop_db():
    """Drop all database tables (DANGEROUS)."""
    with app.app_context():
        db.drop_all()
        click.echo("Database tables dropped.")

@app.cli.command("create-admin")
@click.option('--username', '-u', default=None, help='admin username')
@click.option('--email', '-e', default=None, help='admin email')
@click.option('--password', '-p', default=None, help='admin password (if not provided, will prompt)')
def create_admin(username, email, password):
    """
    Create an admin user. If user exists, updates their role to admin.
    """
    with app.app_context():
        uname = username or input("Admin username [admin]: ") or "admin"
        mail = email or input("Admin email [admin@example.com]: ") or "admin@example.com"
        pwd = password
        if not pwd:
            pwd = getpass("Admin password (will not echo): ")
            if not pwd:
                click.echo("Password required. Aborting.")
                return

        existing = db.session.query(User).filter_by(username=uname).first()
        if existing:
            existing.email = mail
            existing.role = 'admin'
            existing.password = generate_password_hash(pwd)
            db.session.commit()
            click.echo(f"Updated existing user '{uname}' to admin.")
            return

        user = User(username=uname, email=mail, password=generate_password_hash(pwd), role='admin')
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created admin user '{uname}'.")

@app.cli.command("create-default-admin")
def create_default_admin():
    """
    Create default admin only if CREATE_DEFAULT_ADMIN env is truthy.
    This mirrors behavior in create_app but can be invoked manually.
    """
    create_flag = os.environ.get('CREATE_DEFAULT_ADMIN', 'false').lower() in ('1','true','yes')
    if not create_flag:
        click.echo("CREATE_DEFAULT_ADMIN not enabled in environment. Use -- or set env var.")
        return
    admin_pwd = os.environ.get('ADMIN_PASSWORD') or os.environ.get('INITIAL_ADMIN_PASSWORD') or None
    if not admin_pwd:
        admin_pwd = getpass("Password for default admin (will not echo): ")
        if not admin_pwd:
            click.echo("Password required. Aborting.")
            return
    with app.app_context():
        existing = db.session.query(User).filter_by(username='admin').first()
        if existing:
            click.echo("Default admin already exists.")
            return
        user = User(username='admin', email='admin@example.com', password=generate_password_hash(admin_pwd), role='admin')
        db.session.add(user)
        db.session.commit()
        click.echo("Default admin created (username=admin).")

# optional: runserver command wrapper
@app.cli.command("runserver")
@click.option("--host", default="127.0.0.1", help="Host to listen on")
@click.option("--port", default=5000, help="Port to listen on", type=int)
@click.option("--debug/--no-debug", default=None, help="Enable/disable debug mode (overrides config)")
def runserver(host, port, debug):
    """Run development server (wrapper around flask run)."""
    if debug is not None:
        app.debug = debug
    click.echo(f"Starting server on {host}:{port} (debug={app.debug})")
    app.run(host=host, port=port, debug=app.debug)

# shell context for `flask shell` (Flask CLI picks up app when FLASK_APP=manage.py)
@app.shell_context_processor
def make_shell_context():
    return {'app': app, 'db': db, 'User': User}

# fallback if invoked directly
if __name__ == "__main__":
    # If the user runs `python manage.py` directly, start server in debug mode
    app.run(host="127.0.0.1", port=int(os.environ.get('PORT', 5000)), debug=True)
