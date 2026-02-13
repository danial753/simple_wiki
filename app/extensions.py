# FILE: app/extensions.py
"""
تعریف و مقداردهی افزونه‌ها (singletons) برای اپ:
- db (SQLAlchemy)
- migrate (Flask-Migrate)
- login_manager (Flask-Login)
- cache (Flask-Caching)
- csrf (Flask-WTF CSRFProtect) — در صورت نیاز قابل فعال‌سازی است.

این فایل فقط instance‌ها را ایجاد می‌کند. برای مقداردهی نهایی از
    init_extensions(app, user_loader=..., request_loader=..., enable_csrf=...)
یا از هر init_* جداگانه استفاده کنید.
"""

from typing import Callable, Optional, Any
import logging

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_caching import Cache

logger = logging.getLogger(__name__)

# تلاش برای وارد کردن CSRFProtect در صورت موجود بودن
try:
    from flask_wtf import CSRFProtect  # type: ignore
    _csrf_available = True
except Exception:
    CSRFProtect = None  # type: ignore
    _csrf_available = False

# ---------- Singletons (instances) ----------
db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
cache = Cache()
# CSRFProtect تنها هنگام init_extensions ساخته و مقداردهی می‌شود (در صورت درخواست)

# ---------- Core init function ----------

def init_extensions(
    app: Flask,
    user_loader: Optional[Callable[[str], Any]] = None,
    request_loader: Optional[Callable[[Any], Any]] = None,
    enable_csrf: bool = False,
) -> None:
    """
    مقداردهی همهٔ افزونه‌ها در یک فراخوانی.

    Args:
        app: شیء Flask
        user_loader: تابعی که یک user_id (str) می‌گیرد و شیء کاربر را برمی‌گرداند.
        request_loader: تابع اختیاری برای بارگذاری کاربر براساس درخواست (flask-login request_loader).
        enable_csrf: اگر True و flask-wtf نصب باشد، CSRFProtect مقداردهی می‌شود.
    """
    # SQLAlchemy و Migrate
    try:
        db.init_app(app)
        migrate.init_app(app, db)
        app.logger.debug("Initialized db and migrate")
    except Exception:
        app.logger.exception("Failed to init db/migrate")

    # LoginManager
    try:
        login_manager.init_app(app)
        # پیش‌فرض‌های معقول (قابل بازنویسی در create_app)
        login_manager.login_message = app.config.get(
            'LOGIN_MESSAGE', "برای ادامه، لطفاً وارد شوید."
        )
        login_manager.login_message_category = app.config.get(
            'LOGIN_MESSAGE_CATEGORY', "info"
        )

        # ثبت loaderها در صورت ارسال شدن
        if user_loader:
            try:
                login_manager.user_loader(user_loader)
                app.logger.debug("Registered Flask-Login user_loader")
            except Exception:
                app.logger.exception("Registering user_loader failed")

        if request_loader:
            try:
                login_manager.request_loader(request_loader)
                app.logger.debug("Registered Flask-Login request_loader")
            except Exception:
                app.logger.exception("Registering request_loader failed")

        app.logger.debug("Initialized login_manager")
    except Exception:
        app.logger.exception("Failed to init login_manager")

    # Cache (Flask-Caching)
    try:
        cache.init_app(app)
        app.logger.debug("Initialized cache")
    except Exception:
        app.logger.exception("Failed to init cache")

    # CSRF (اختیاری)
    if enable_csrf:
        if _csrf_available and CSRFProtect is not None:
            try:
                CSRFProtect().init_app(app)
                app.logger.debug("CSRFProtect enabled")
            except Exception:
                app.logger.exception("Failed to init CSRFProtect")
        else:
            app.logger.warning(
                "CSRFProtect requested but flask-wtf is not installed; skipping CSRF init"
            )

# ---------- Individual init helpers ----------

def init_db(app: Flask) -> None:
    """مقداردهی SQLAlchemy (db) برای اپ مشخص."""
    try:
        db.init_app(app)
        app.logger.debug("db.init_app called")
    except Exception:
        app.logger.exception("init_db failed")

def init_migrate(app: Flask) -> None:
    """مقداردهی Flask-Migrate (migrate) برای اپ مشخص."""
    try:
        migrate.init_app(app, db)
        app.logger.debug("migrate.init_app called")
    except Exception:
        app.logger.exception("init_migrate failed")

def init_login_manager(
    app: Flask,
    user_loader: Optional[Callable[[str], Any]] = None,
    request_loader: Optional[Callable[[Any], Any]] = None,
) -> None:
    """
    مقداردهی LoginManager و ثبت loaderها در صورت نیاز.
    """
    try:
        login_manager.init_app(app)
        login_manager.login_message = app.config.get(
            'LOGIN_MESSAGE', "برای ادامه، لطفاً وارد شوید."
        )
        login_manager.login_message_category = app.config.get('LOGIN_MESSAGE_CATEGORY', "info")

        if user_loader:
            try:
                login_manager.user_loader(user_loader)
                app.logger.debug("Registered user_loader via init_login_manager")
            except Exception:
                app.logger.exception("Failed to register user_loader in init_login_manager")

        if request_loader:
            try:
                login_manager.request_loader(request_loader)
                app.logger.debug("Registered request_loader via init_login_manager")
            except Exception:
                app.logger.exception("Failed to register request_loader in init_login_manager")

        app.logger.debug("login_manager initialized")
    except Exception:
        app.logger.exception("init_login_manager failed")

def init_cache(app: Flask) -> None:
    """مقداردهی cache (Flask-Caching) برای اپ مشخص."""
    try:
        cache.init_app(app)
        app.logger.debug("cache.init_app called")
    except Exception:
        app.logger.exception("init_cache failed")


# ---------- Convenience export ----------
__all__ = [
    "db",
    "migrate",
    "login_manager",
    "cache",
    "init_extensions",
    "init_db",
    "init_migrate",
    "init_login_manager",
    "init_cache",
]
