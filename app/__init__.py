# FILE: app/__init__.py
"""
Application factory for simple_wiki.

Responsibilities:
- create_app(config_object=None) returns a configured Flask app
- register extensions (via app.extensions.init_extensions)
- register blueprints (best-effort; tolerant to partial refactors)
- register flask-login user_loader (prefer a models.get_user_by_id if present)
- provide a Jinja helper `endpoint_exists(name)` to avoid BuildError in templates
- create database tables and call any compatibility helpers (e.g. ensure_page_columns)
- optionally create a default admin user when CREATE_DEFAULT_ADMIN env var is truthy

This file is intentionally defensive: missing blueprints or missing helper functions
should not prevent the app from starting during incremental refactors.
"""
from __future__ import annotations

import os
import logging
from typing import Optional, Dict

from flask import Flask, current_app, send_from_directory

# local imports
from .config import DevConfig
from .extensions import init_extensions, db, login_manager

logger = logging.getLogger(__name__)


def register_blueprints(app: Flask) -> None:
    """
    Try to import and register the project's known blueprints.
    Fail quietly (with debug logs) if a blueprint module is missing so that
    partial refactors don't break app startup.
    """
    # core wiki blueprint
    try:
        from .blueprints.wiki.routes import wiki_bp  # type: ignore
        app.register_blueprint(wiki_bp)
        app.logger.debug("Registered blueprint: wiki")
    except Exception:
        app.logger.debug("wiki blueprint not available to register yet")

    # auth blueprint (optional)
    try:
        from .blueprints.auth.routes import auth_bp  # type: ignore
        app.register_blueprint(auth_bp, url_prefix='')
        app.logger.debug("Registered blueprint: auth")
    except Exception:
        app.logger.debug("auth blueprint not available to register yet")

    # admin blueprint (optional)
    try:
        from .blueprints.admin.routes import admin_bp  # type: ignore
        app.register_blueprint(admin_bp, url_prefix='/admin')
        app.logger.debug("Registered blueprint: admin")
    except Exception:
        app.logger.debug("admin blueprint not available to register yet")

    # api blueprint (optional)
    try:
        from .blueprints.api.routes import api_bp  # type: ignore
        app.register_blueprint(api_bp, url_prefix='/api')
        app.logger.debug("Registered blueprint: api")
    except Exception:
        app.logger.debug("api blueprint not available to register yet")


def _register_user_loader(app: Flask) -> None:
    """
    Register a user_loader for Flask-Login.

    Priority:
    1. If models.get_user_by_id exists, use it.
    2. Otherwise register a fallback that attempts to load User by primary key.
    """
    try:
        # preferred: an explicit helper in models
        from .models import get_user_by_id  # type: ignore
        login_manager.user_loader(get_user_by_id)
        app.logger.debug("Flask-Login user_loader registered (get_user_by_id).")
        return
    except Exception:
        app.logger.debug("models.get_user_by_id not found; installing fallback user_loader")

    def _fallback_loader(user_id: str):
        try:
            from .models import User  # type: ignore
            # Try modern SQLAlchemy API first
            try:
                uid = int(user_id)
            except Exception:
                uid = user_id
            try:
                return db.session.get(User, uid)
            except Exception:
                # older SQLAlchemy fallback
                return db.session.query(User).get(uid)
        except Exception:
            app.logger.exception("fallback user_loader failed for id=%s", user_id)
            return None

    login_manager.user_loader(_fallback_loader)
    app.logger.debug("Flask-Login fallback user_loader registered.")


def _add_endpoint_aliases(app: Flask, aliases: Dict[str, str]) -> None:
    """
    Create alias endpoints to map old endpoint names (keys) to canonical endpoints (values).

    For each alias -> target:
      - if target exists in app.view_functions:
          find URL rules whose endpoint == target and add a new url_rule with same rule
          but endpoint set to alias (and same allowed methods).
      - skip aliases where target is missing or alias already exists.

    This is used only to preserve compatibility with templates that expect bare endpoints
    like "index" instead of "wiki.index".
    """
    for alias, target in aliases.items():
        try:
            # skip if alias already exists
            if alias in app.view_functions:
                app.logger.debug("Alias %s already exists; skipping", alias)
                continue

            # skip if target not registered
            if target not in app.view_functions:
                app.logger.debug("Alias target %s not present; skipping alias %s", target, alias)
                continue

            # find url rules for the target endpoint
            rules = [r for r in app.url_map.iter_rules() if r.endpoint == target]
            if not rules:
                app.logger.debug("No url rules found for target endpoint %s; skipping alias %s", target, alias)
                continue

            for rule in rules:
                # compute methods excluding HEAD/OPTIONS which are added automatically
                methods = set(rule.methods) - {"HEAD", "OPTIONS"}
                # add new rule using the same URL pattern but new endpoint name
                # view_func must be the same as target's view function
                try:
                    app.add_url_rule(rule.rule, endpoint=alias, view_func=app.view_functions[target], methods=list(methods))
                    app.logger.debug("Added alias endpoint %s -> %s (rule=%s)", alias, target, rule.rule)
                except Exception:
                    app.logger.exception("Failed to add alias %s -> %s for rule %s", alias, target, rule.rule)
        except Exception:
            app.logger.exception("Unexpected error while adding alias %s -> %s", alias, target)


def _inject_template_helpers(app: Flask) -> None:
    """
    Provide template helper functions (via context_processor).
    - endpoint_exists(name): returns True if endpoint is registered (prevents BuildError)
    """
    @app.context_processor
    def _helpers():
        def endpoint_exists(name: str) -> bool:
            try:
                return name in current_app.view_functions
            except Exception:
                return False
        return {"endpoint_exists": endpoint_exists}


def create_app(config_object: Optional[object] = None) -> Flask:
    """
    Application factory – با مسیرهای ریشه پروژه (برای manage.py)
    """
    # محاسبه ریشه پروژه (simple_wiki 2) – جایی که manage.py است
    PROJECT_ROOT = os.getcwd()  # os.getcwd() همیشه ریشه اجرای فعلی را می‌دهد (manage.py)
    APP_DIR = os.path.join(PROJECT_ROOT, 'app')
    STATIC_DIR = os.path.join(APP_DIR, 'static')
    TEMPLATE_DIR = os.path.join(APP_DIR, 'templates')

    # دیباگ مسیرها – این خطوط را حتماً نگه دارید تا چک کنیم
    logger.info(f"PROJECT_ROOT (from os.getcwd): {PROJECT_ROOT}")
    logger.info(f"STATIC_DIR: {STATIC_DIR}")
    logger.info(f"TEMPLATE_DIR: {TEMPLATE_DIR}")

    # ساخت اپ با مسیرهای قطعی
    app = Flask(__name__,
                static_folder=STATIC_DIR,
                template_folder=TEMPLATE_DIR)

    # اجبار Flask برای شناخت مسیر /static
    app.static_url_path = '/static'

    # تست دستی برای اطمینان از کارکرد پوشه static (می‌توانید بعداً حذف کنید)
    @app.route('/test-static/<path:filename>')
    def test_static(filename):
        try:
            return send_from_directory(app.static_folder, filename)
        except Exception as e:
            return f"Error serving static file: {str(e)}", 500

    # فعال کردن Jinja برای {% do %}
    try:
        app.jinja_env.add_extension('jinja2.ext.do')
    except Exception:
        pass

    # بارگذاری تنظیمات
    cfg = config_object or DevConfig
    if isinstance(cfg, str):
        app.config.from_object(cfg)
    else:
        app.config.from_object(cfg)

    # مقداردهی extensions
    try:
        enable_csrf = app.config.get('ENABLE_CSRF', False)
        init_extensions(app, enable_csrf=enable_csrf)
        app.logger.debug("Extensions initialized via init_extensions")
    except Exception:
        app.logger.exception("init_extensions failed; attempting minimal extension init")
        try:
            from .extensions import db as _db, migrate as _migrate, login_manager as _lm  # type: ignore
            _db.init_app(app)
            _migrate.init_app(app, _db)
            _lm.init_app(app)
        except Exception:
            app.logger.exception("Manual extension initialization failed")

    # تنظیم صفحه ورود
    try:
        login_manager.login_view = app.config.get('LOGIN_VIEW', 'login')
    except Exception:
        pass

    # ثبت blueprintها
    register_blueprints(app)

    # ثبت user_loader
    try:
        _register_user_loader(app)
    except Exception:
        app.logger.exception("registering user_loader failed")

    # helperهای قالب
    _inject_template_helpers(app)

    # aliasهای endpoint
    endpoint_aliases: Dict[str, str] = {
        'index': 'wiki.index',
        'discover': 'wiki.discover',
        'view_page': 'wiki.view_page',
        'edit_page': 'wiki.edit_page',
        'uploaded_file': 'wiki.uploaded_file',
        'stream_video': 'wiki.stream_video',
        'api_page_save': 'wiki.api_page_save',
        'api_page_delete': 'wiki.api_page_delete',
        'add_comment': 'wiki.add_comment',
        'login': 'auth.login',
        'register': 'auth.register',
        'logout': 'auth.logout',
        'profile': 'auth.profile',
        'admin_users': 'admin.admin_users',
        'admin_user_new': 'admin.admin_user_new',
        'admin_user_edit': 'admin.admin_user_edit',
        'admin_user_delete': 'admin.admin_user_delete',
    }

    with app.app_context():
        try:
            from . import models  # noqa: F401
            db.create_all()
            # call compatibility helper if available
            try:
                if hasattr(models, 'ensure_page_columns'):
                    models.ensure_page_columns()
            except Exception:
                app.logger.exception("ensure_page_columns failed")
        except Exception:
            app.logger.exception("models import or db.create_all failed")

        # add endpoint aliases (only those with existing canonical targets will be added)
        try:
            _add_endpoint_aliases(app, endpoint_aliases)
        except Exception:
            app.logger.exception("adding endpoint aliases failed")

        # optionally create a default admin user when explicitly requested via env var
        try:
            create_default = os.environ.get('CREATE_DEFAULT_ADMIN', 'false').lower() in ('1', 'true', 'yes')
            if create_default:
                from .models import User  # type: ignore
                from werkzeug.security import generate_password_hash
                admin_exists = db.session.query(User).filter_by(username='admin').first()
                if not admin_exists:
                    admin_pwd = os.environ.get('ADMIN_PASSWORD') or os.environ.get('INITIAL_ADMIN_PASSWORD') or 'admin'
                    admin = User(username='admin', email='admin@example.com',
                                 password=generate_password_hash(admin_pwd), role='admin')
                    db.session.add(admin)
                    db.session.commit()
                    app.logger.info("Created default admin account (username=admin).")
        except Exception:
            app.logger.exception("Failed to create default admin (if requested)")




    return app