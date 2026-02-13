# FILE: app/config.py
"""
تنظیمات مرکزی اپلیکیشن.

نحوۀ استفاده:
- در create_app می‌توانی از `app.config.from_object(DevConfig)` یا ProdConfig/ TestConfig استفاده کنی.
- مقادیر حساس مثل SECRET_KEY و DATABASE_URL را از متغیر محیطی بخوان.
"""

import os
from pathlib import Path
from typing import Tuple, Set

# پایه‌ای‌ترین تنظیمات
class BaseConfig:
    # امنیت
    SECRET_KEY: str = os.environ.get('SECRET_KEY', 'change_me_in_production')

    # مسیرها
    BASE_DIR: Path = Path(os.environ.get('BASE_DIR', Path.cwd()))
    PAGES_DIR: str = os.environ.get('PAGES_DIR', str(BASE_DIR / 'pages'))
    UPLOAD_FOLDER: str = os.environ.get('UPLOAD_FOLDER', str(BASE_DIR / 'static' / 'uploads'))
    MEDIA_ROOT: str = os.environ.get('MEDIA_ROOT', str(BASE_DIR / 'media'))

    # دیتابیس
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False
    SQLALCHEMY_DATABASE_URI: str = os.environ.get('DATABASE_URL', f"sqlite:///{BASE_DIR / 'simple_wiki.db'}")

    # آپلودها و فایل‌ها
    MAX_CONTENT_LENGTH: int = int(os.environ.get('MAX_CONTENT_LENGTH', 5 * 1024 * 1024 * 1024))  # 5 GiB
    CKEDITOR_MAX_UPLOAD: int = int(os.environ.get('CKEDITOR_MAX_UPLOAD', 200 * 1024 * 1024))  # 200 MiB
    DEFAULT_CHUNK_SIZE: int = int(os.environ.get('DEFAULT_CHUNK_SIZE', 8 * 1024 * 1024))  # 8 MiB

    # پسوندهای مجاز
    ALLOWED_EXTENSIONS: Set[str] = set(os.environ.get('ALLOWED_EXTENSIONS',
        "png,jpg,jpeg,gif,webp,pdf,mp4,webm,mov,mkv,avi,svg,doc,docx").split(","))
    ALLOWED_VIDEO_EXT: Set[str] = set(os.environ.get('ALLOWED_VIDEO_EXT', "mp4,webm,mov,mkv,avi").split(","))

    # تصویر
    IMAGE_MAX_DIM: int = int(os.environ.get('IMAGE_MAX_DIM', 2400))
    THUMBNAIL_SIZE: Tuple[int, int] = (int(os.environ.get('THUMBNAIL_WIDTH', 400)), int(os.environ.get('THUMBNAIL_HEIGHT', 400)))
    CREATE_WEBP: bool = os.environ.get('CREATE_WEBP', 'true').lower() in ('1', 'true', 'yes')

    # کامنت‌ها
    MAX_COMMENT_LENGTH: int = int(os.environ.get('MAX_COMMENT_LENGTH', 4000))

    # Template / Jinja
    TEMPLATES_AUTO_RELOAD: bool = os.environ.get('TEMPLATES_AUTO_RELOAD', 'true').lower() in ('1', 'true', 'yes')

    # Cache (optional) — config keys used by Flask-Caching if فعال شود
    CACHE_TYPE: str = os.environ.get('CACHE_TYPE', 'simple')  # production: 'redis'
    CACHE_DEFAULT_TIMEOUT: int = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', 300))

    # Login
    LOGIN_VIEW: str = os.environ.get('LOGIN_VIEW', 'login')

    # Debug (default خاموش)
    DEBUG: bool = os.environ.get('FLASK_DEBUG', 'false').lower() in ('1','true','yes')

    # Misc
    CREATE_DEFAULT_ADMIN: bool = os.environ.get('CREATE_DEFAULT_ADMIN', 'false').lower() in ('1','true','yes')
    ADMIN_PASSWORD: str = os.environ.get('ADMIN_PASSWORD', '')

class DevConfig(BaseConfig):
    DEBUG = True
    # در محیط توسعه به‌صورت پیش‌فرض از sqlite فایل استفاده می‌کنیم
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f"sqlite:///{BaseConfig.BASE_DIR / 'simple_wiki_dev.db'}")
    TEMPLATES_AUTO_RELOAD = True
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'simple')

class ProdConfig(BaseConfig):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', BaseConfig.SQLALCHEMY_DATABASE_URI)
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'redis')

class TestConfig(BaseConfig):
    TESTING = True
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///:memory:')
    # کمینه‌سازی زمان‌ها برای تست
    CACHE_TYPE = os.environ.get('CACHE_TYPE', 'null')
    CKEDITOR_MAX_UPLOAD = 10 * 1024 * 1024
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024

# Convenience helper برای بارگذاری کانفیگ بر اساس نام محیط
def get_config(env: str = None):
    """
    env: 'dev' | 'prod' | 'test' or None (defaults to dev)
    """
    e = (env or os.environ.get('FLASK_ENV') or 'dev').lower()
    if e in ('prod', 'production'):
        return ProdConfig
    if e in ('test', 'testing'):
        return TestConfig
    return DevConfig
