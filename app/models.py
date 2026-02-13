# FILE: app/models.py
from datetime import datetime
import json
from typing import List, Optional

from flask_login import UserMixin
from sqlalchemy import ForeignKey, text
from sqlalchemy.orm import relationship, backref

from .extensions import db

# ---------------- MODELS ----------------
class User(db.Model, UserMixin):
    """
    مدل کاربر — ارث‌بری از UserMixin ویژگی‌های مورد نیاز flask-login
    را فراهم می‌کند: is_authenticated, is_active, is_anonymous, get_id()
    """
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
    tags = db.Column(db.String(1000))
    feature_image = db.Column(db.String(255))
    gallery = db.Column(db.Text)   # JSON list
    videos = db.Column(db.Text)    # JSON list
    personnel = db.Column(db.Text) # JSON list
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def get_gallery(self) -> List[str]:
        try:
            return json.loads(self.gallery) if self.gallery else []
        except Exception:
            return []

    def get_videos(self) -> List[str]:
        try:
            return json.loads(self.videos) if self.videos else []
        except Exception:
            return []

    def get_personnel(self) -> List[dict]:
        try:
            return json.loads(self.personnel) if self.personnel else []
        except Exception:
            return []


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


# ---------------- HELPERS ----------------
def get_user_by_id(user_id: Optional[str]):
    """
    Helper for Flask-Login user_loader.
    Accepts str or int and returns a User or None.
    """
    if not user_id:
        return None
    try:
        uid = int(user_id)
    except Exception:
        return None
    try:
        # SQLAlchemy 1.4+: session.get is preferred
        try:
            return db.session.get(User, uid)
        except Exception:
            return db.session.query(User).get(uid)
    except Exception:
        db.session.rollback()
        return None


def ensure_page_columns():
    """
    سازگاری با اسکیمای قدیمی: اگر از SQLite استفاده می‌شود و ستون‌های اختیاری
    وجود ندارند، در اینجا اضافه می‌شوند.
    این تابع صرفاً یک کمک‌افزاری است؛ اگر از Alembic یا migration tool استفاده می‌کنید،
    نیازی به آن نیست.
    """
    try:
        inspector = db.inspect(db.engine)
        if 'page' not in inspector.get_table_names():
            return
        rows = db.session.execute(text("PRAGMA table_info('page')")).fetchall()
        existing = {row[1] for row in rows}
        alters = []
        if 'subtitle' not in existing:
            alters.append("ALTER TABLE page ADD COLUMN subtitle TEXT")
        if 'gallery' not in existing:
            alters.append("ALTER TABLE page ADD COLUMN gallery TEXT")
        if 'videos' not in existing:
            alters.append("ALTER TABLE page ADD COLUMN videos TEXT")
        if 'personnel' not in existing:
            alters.append("ALTER TABLE page ADD COLUMN personnel TEXT")
        if alters:
            with db.engine.begin() as conn:
                for sql_stmt in alters:
                    try:
                        conn.execute(text(sql_stmt))
                    except Exception:
                        # ignore failures but log them
                        db.session.rollback()
    except Exception:
        # nothing fatal — فقط لاگ کن
        try:
            import logging
            logging.getLogger(__name__).exception("ensure_page_columns failed")
        except Exception:
            pass
