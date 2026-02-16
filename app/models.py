# FILE: app/models.py
from datetime import datetime
import json
from typing import List, Optional, Dict, Any

from flask_login import UserMixin
from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import relationship, backref

from .extensions import db


class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(150))
    bio = db.Column(db.Text)
    role = db.Column(db.String(50), default='user')
    avatar = db.Column(db.String(200), default='default_avatar.png')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    comments = relationship('Comment', back_populates='user', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<User {self.username} ({self.email})>"


class Page(db.Model):
    __tablename__ = 'page'
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    title = db.Column(db.String(255))
    subtitle = db.Column(db.String(512))
    excerpt = db.Column(db.Text)
    tags = db.Column(db.String(1000))          # comma-separated or JSON
    feature_image = db.Column(db.String(255))
    gallery = db.Column(db.Text)               # JSON list of filenames
    videos = db.Column(db.Text)                # JSON list of filenames
    personnel = db.Column(db.Text)             # JSON list of dicts
    content = db.Column(db.Text)               # محتوای اصلی (Markdown/HTML)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # ─────────── فیلد جدید برای مشخص کردن سازنده صفحه ───────────
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user = db.relationship('User', backref='pages')

    # ─────────────────────────────────────────────────────────
    # متدهای امن برای گرفتن داده‌ها (با مدیریت خطا)
    # ─────────────────────────────────────────────────────────
    def get_gallery(self) -> List[str]:
        """برگرداندن لیست مسیر فایل‌های گالری"""
        if not self.gallery:
            return []
        try:
            return json.loads(self.gallery)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    def get_videos(self) -> List[str]:
        """برگرداندن لیست مسیر فایل‌های ویدیو"""
        if not self.videos:
            return []
        try:
            return json.loads(self.videos)
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    def get_personnel(self) -> List[Dict[str, Any]]:
        """برگرداندن لیست افراد درگیر (هر کدام یک دیکشنری)"""
        if not self.personnel:
            return []
        try:
            data = json.loads(self.personnel)
            # اطمینان از اینکه لیست دیکشنری است
            if isinstance(data, list):
                return [
                    item if isinstance(item, dict) else {}
                    for item in data
                ]
            return []
        except (json.JSONDecodeError, TypeError, ValueError):
            return []

    def get_tags_list(self) -> List[str]:
        """برگرداندن لیست تگ‌ها به صورت امن"""
        if not self.tags:
            return []
        try:
            # اگر به صورت JSON ذخیره شده
            if self.tags.startswith('['):
                return json.loads(self.tags)
            # اگر comma-separated است (فرمت قدیمی)
            return [t.strip() for t in self.tags.split(',') if t.strip()]
        except Exception:
            return []

    def __repr__(self):
        return f"<Page {self.slug} ({self.title or 'بدون عنوان'})>"


class Comment(db.Model):
    __tablename__ = 'comment'
    id = db.Column(db.Integer, primary_key=True)
    page = db.Column(db.String(300), nullable=False, index=True)
    user_id = db.Column(db.Integer, ForeignKey('user.id'), nullable=False)
    parent_id = db.Column(db.Integer, ForeignKey('comment.id'), nullable=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)
    deleted = db.Column(db.Boolean, default=False)
    deleted_at = db.Column(db.DateTime, nullable=True)

    user = relationship('User', back_populates='comments')
    children = relationship('Comment', backref=backref('parent', remote_side=[id]), cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Comment {self.id} by user {self.user_id} on page {self.page}>"


# ────────────────────────────────────────────────
# Helper functions
# ────────────────────────────────────────────────
def get_user_by_id(user_id: Optional[str]) -> Optional[User]:
    if not user_id:
        return None
    try:
        uid = int(user_id)
        return db.session.get(User, uid)
    except Exception:
        return None


def ensure_page_columns():
    """
    فقط برای سازگاری با دیتابیس‌های قدیمی (SQLite بدون migration)
    در پروژه‌های واقعی بهتره از Flask-Migrate / Alembic استفاده بشه
    """
    try:
        inspector = db.inspect(db.engine)
        if 'page' not in inspector.get_table_names():
            return

        rows = db.session.execute(text("PRAGMA table_info('page')")).fetchall()
        existing = {row[1] for row in rows}

        alters = []
        for col in ['subtitle', 'excerpt', 'tags', 'feature_image', 'gallery', 'videos', 'personnel', 'content']:
            if col not in existing:
                alters.append(f"ALTER TABLE page ADD COLUMN {col} TEXT")

        if alters:
            with db.engine.begin() as conn:
                for stmt in alters:
                    try:
                        conn.execute(text(stmt))
                    except Exception as e:
                        print(f"خطا در اضافه کردن ستون: {e}")
                        # rollback خودکار انجام می‌شود
    except Exception as e:
        print(f"خطا در ensure_page_columns: {e}")