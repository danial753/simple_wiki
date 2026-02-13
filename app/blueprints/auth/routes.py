# FILE: app/blueprints/auth/routes.py
import os
import uuid
import logging
from typing import Optional
from pathlib import Path

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    send_from_directory,
    abort
)
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# try to import extensions & models; fall back gracefully if not present
try:
    from ...extensions import db, login_manager  # type: ignore
except Exception:
    db = None
    login_manager = None

try:
    from ...models import User  # type: ignore
except Exception:
    User = None

auth_bp = Blueprint('auth', __name__, template_folder='templates')

logger = logging.getLogger(__name__)

# Register a user_loader if possible (defensive)
if login_manager is not None and User is not None:
    try:
        @login_manager.user_loader
        def _load_user(user_id: str):
            try:
                if db is not None:
                    return db.session.get(User, int(user_id))  # type: ignore
                else:
                    return User.query.get(int(user_id))  # type: ignore
            except Exception:
                try:
                    return User.query.get(user_id)  # fallback if id is str key
                except Exception:
                    return None
    except Exception:
        current_app.logger.exception("Failed to register login_manager.user_loader")


# ────────────────────────────────────────────────
# مسیر پوشه uploads (برای آواتار و فایل‌ها)
# ────────────────────────────────────────────────
def _uploads_dir() -> Path:
    # اصلاح مسیر: استفاده از UPLOAD_FOLDER که در __init__.py تعریف شده
    uploads_path = current_app.config.get('UPLOAD_FOLDER')
    if not uploads_path:
        root = Path(current_app.root_path)
        uploads_path = root.parent / 'uploads'  # root/uploads (نه app/uploads)
    uploads = Path(uploads_path)
    uploads.mkdir(parents=True, exist_ok=True)
    return uploads


def _allowed_file(filename: str) -> bool:
    """چک کردن فرمت مجاز برای فایل آواتار"""
    allowed = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def _save_avatar(file_storage):
    """ذخیره تصویر آواتار و برگرداندن نام فایل"""
    if not file_storage or file_storage.filename == '':
        return None

    if not _allowed_file(file_storage.filename):
        logger.warning(f"فرمت غیرمجاز آواتار: {file_storage.filename}")
        return None

    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    out = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
    dest = _uploads_dir() / out

    try:
        file_storage.save(str(dest))
        logger.info(f"آواتار ذخیره شد: {out}")
        # چک وجود فایل بعد از ذخیره (برای دیباگ)
        if os.path.exists(str(dest)):
            logger.info(f"فایل در مسیر درست ذخیره شد: {str(dest)}")
        else:
            logger.warning(f"فایل ذخیره نشد: {str(dest)}")
        return out
    except Exception as e:
        logger.exception(f"خطا در ذخیره آواتار: {str(e)}")
        return None


# ────────────────────────────────────────────────
# ورود (Login)
# ────────────────────────────────────────────────
@auth_bp.route('/login', methods=['GET', 'POST'], endpoint='login')
def login():
    if request.method == 'GET':
        return render_template('login.html')

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')

    if not username or not password:
        flash('نام کاربری و رمز عبور لازم است', 'warning')
        return redirect(url_for('auth.login'))

    user = None
    try:
        if User is not None:
            user = User.query.filter_by(username=username).first()  # type: ignore
    except Exception:
        current_app.logger.exception("DB lookup for user failed")

    if not user:
        flash('کاربر یافت نشد', 'danger')
        return redirect(url_for('auth.login'))

    # چک کردن رمز عبور
    try:
        stored = getattr(user, 'password', None)
        if stored and stored.startswith('pbkdf2:') or (stored and stored.count('$') >= 2):
            matched = check_password_hash(stored, password)
        else:
            matched = (stored == password)  # fallback (فقط برای تست - حذف شود)
    except Exception:
        matched = False

    if not matched:
        flash('نام‌کاربری یا رمز عبور اشتباه است', 'danger')
        return redirect(url_for('auth.login'))

    try:
        login_user(user)
        flash('با موفقیت وارد شدید', 'success')
        return redirect(url_for('wiki.index'))
    except Exception:
        current_app.logger.exception("login failed")
        flash('خطا هنگام ورود', 'danger')
        return redirect(url_for('auth.login'))


# ────────────────────────────────────────────────
# خروج (Logout)
# ────────────────────────────────────────────────
@auth_bp.route('/logout', endpoint='logout')
@login_required
def logout():
    try:
        logout_user()
        flash('از حساب کاربری خارج شدید', 'info')
    except Exception:
        current_app.logger.exception("logout failed")
        flash('خطا هنگام خروج', 'danger')

    return redirect(url_for('wiki.index'))


# ────────────────────────────────────────────────
# ثبت‌نام (Register)
# ────────────────────────────────────────────────
@auth_bp.route('/register', methods=['GET', 'POST'], endpoint='register')
def register():
    if request.method == 'GET':
        return render_template('register.html')

    username = request.form.get('username', '').strip()
    email = request.form.get('email', '').strip()
    password = request.form.get('password', '')
    full_name = request.form.get('full_name', '').strip()
    bio = request.form.get('bio', '').strip()

    if not username or not email or not password:
        flash('نام کاربری، ایمیل و رمز مورد نیاز است', 'warning')
        return redirect(url_for('auth.register'))

    try:
        if User is not None:
            exists = User.query.filter((User.username == username) | (User.email == email)).first()  # type: ignore
            if exists:
                flash('نام کاربری یا ایمیل قبلاً استفاده شده‌اند', 'warning')
                return redirect(url_for('auth.register'))
    except Exception:
        current_app.logger.exception("register: user existence check failed")

    # ایجاد کاربر جدید
    if User is not None:
        try:
            hashed = generate_password_hash(password)
            user = User(
                username=username,
                email=email,
                password=hashed,
                full_name=full_name,
                bio=bio
            )
            # تنظیم نقش پیش‌فرض
            user.role = current_app.config.get('DEFAULT_ROLE', 'user')

            db.session.add(user)  # type: ignore
            db.session.commit()  # type: ignore

            flash('ثبت‌نام موفق — اکنون وارد شوید', 'success')
            return redirect(url_for('auth.login'))
        except Exception:
            current_app.logger.exception("register failed")
            try:
                if db is not None:
                    db.session.rollback()
            except Exception:
                pass
            flash('خطا هنگام ثبت‌نام', 'danger')
            return redirect(url_for('auth.register'))
    else:
        flash('ثبت‌نام در حال حاضر پشتیبانی نمی‌شود (DB در دسترس نیست)', 'danger')
        return redirect(url_for('auth.register'))


# ────────────────────────────────────────────────
# پروفایل (Profile) – بروزرسانی اطلاعات و آواتار
# ────────────────────────────────────────────────
@auth_bp.route('/profile', methods=['GET', 'POST'], endpoint='profile')
@login_required
def profile():
    if request.method == 'GET':
        return render_template('profile.html', user=current_user)

    # POST: بروزرسانی پروفایل
    full_name = request.form.get('full_name', '').strip()
    bio = request.form.get('bio', '').strip()
    password = request.form.get('password', '').strip()
    avatar_file = request.files.get('avatar')

    updated = False  # برای چک کردن تغییرات

    try:
        user = current_user

        # ۱. آپلود و ذخیره آواتار
        if avatar_file and avatar_file.filename:
            fname = _save_avatar(avatar_file)
            if fname:
                user.avatar = fname  # مستقیم ست می‌کنیم
                updated = True
                logger.info(f"آواتار جدید برای {user.username} ذخیره شد: {fname}")
                flash('تصویر پروفایل با موفقیت تغییر یافت', 'success')
            else:
                logger.warning("ذخیره آواتار ناموفق بود – fname None برگشت")
                flash('خطا در ذخیره تصویر پروفایل (فرمت یا اندازه نامناسب)', 'danger')

        # ۲. بروزرسانی نام و بیوگرافی
        if full_name and full_name != (user.full_name or ''):
            user.full_name = full_name
            updated = True

        if bio and bio != (user.bio or ''):
            user.bio = bio
            updated = True

        # ۳. تغییر رمز عبور (اختیاری)
        if password:
            user.password = generate_password_hash(password)
            updated = True
            flash('رمز عبور با موفقیت تغییر یافت', 'success')

        # ۴. ذخیره تغییرات در دیتابیس – فقط اگر چیزی تغییر کرده باشد
        if updated:
            if db is not None:
                db.session.add(user)
                db.session.commit()
                logger.info(f"پروفایل کاربر {user.username} بروز شد")
                flash('پروفایل با موفقیت بروزرسانی شد', 'success')
            else:
                flash('دیتابیس در دسترس نیست – تغییرات ذخیره نشد', 'danger')
        else:
            flash('هیچ تغییری اعمال نشد', 'info')

    except Exception as e:
        logger.exception(f"خطا در بروزرسانی پروفایل کاربر {current_user.username}")
        if db is not None:
            try:
                db.session.rollback()
            except:
                pass
        flash(f'خطا در بروزرسانی: {str(e)}', 'danger')

    return redirect(url_for('auth.profile'))


# ────────────────────────────────────────────────
# مسیر کمکی برای سرو فایل‌های uploads (آواتارها)
# ────────────────────────────────────────────────
@auth_bp.route('/uploads/<path:filename>', endpoint='uploads_file')
def uploads_file(filename: str):
    uploads_root = os.path.abspath(str(_uploads_dir()))
    candidate = os.path.normpath(os.path.join(uploads_root, filename))

    if candidate.startswith(uploads_root + os.sep) and os.path.exists(candidate) and os.path.isfile(candidate):
        rel = os.path.relpath(candidate, uploads_root)
        return send_from_directory(uploads_root, rel)

    # fallback به آواتار پیش‌فرض
    default = current_app.config.get('DEFAULT_AVATAR', 'default_avatar.png')
    default_static = Path(current_app.static_folder) / default
    if default_static.exists():
        logger.info(f"Serving default avatar: {default}")
        return send_from_directory(current_app.static_folder, default)

    abort(404)