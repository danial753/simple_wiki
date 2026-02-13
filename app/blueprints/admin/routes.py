# FILE: app/blueprints/admin/routes.py
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ...extensions import db
from ...models import User
from werkzeug.security import generate_password_hash

admin_bp = Blueprint('admin', __name__, template_folder='templates', url_prefix='/admin')

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def wrapped(*a, **kw):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('فقط ادمین دسترسی دارد', 'danger')
            return redirect(url_for('index'))
        return f(*a, **kw)
    return wrapped

@admin_bp.route('/users', endpoint='admin_users')
@login_required
@admin_required
def admin_users():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('search', '').strip()
    query = User.query
    if q:
        like = f"%{q}%"
        query = query.filter((User.username.ilike(like)) | (User.email.ilike(like)) | (User.full_name.ilike(like)))
    users = query.order_by(User.id.desc()).paginate(page=page, per_page=10, error_out=False)
    return render_template('admin_users.html', users=users, search_query=q)

@admin_bp.route('/users/new', methods=['GET','POST'], endpoint='admin_user_new')
@login_required
@admin_required
def admin_user_new():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        email = request.form.get('email','').strip()
        pwd = request.form.get('password','').strip()
        if not username or not email or not pwd:
            flash('فیلدها را کامل کنید', 'warning'); return redirect(url_for('admin.admin_user_new'))
        if User.query.filter_by(username=username).first():
            flash('نام کاربری تکراری', 'danger'); return redirect(url_for('admin.admin_user_new'))
        if User.query.filter_by(email=email).first():
            flash('ایمیل تکراری', 'danger'); return redirect(url_for('admin.admin_user_new'))
        user = User(username=username, email=email, password=generate_password_hash(pwd),
                    full_name=request.form.get('full_name'), role=request.form.get('role','user'))
        db.session.add(user); db.session.commit()
        flash('کاربر ایجاد شد', 'success'); return redirect(url_for('admin.admin_users'))
    return render_template('admin_user_form.html', user=None)

@admin_bp.route('/users/edit/<int:user_id>', methods=['GET','POST'], endpoint='admin_user_edit')
@login_required
@admin_required
def admin_user_edit(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        new_username = request.form.get('username','').strip()
        new_email = request.form.get('email','').strip()
        if new_username != user.username and User.query.filter_by(username=new_username).first():
            flash('نام کاربری تکراری', 'danger'); return redirect(url_for('admin.admin_user_edit', user_id=user_id))
        if new_email != user.email and User.query.filter_by(email=new_email).first():
            flash('ایمیل تکراری', 'danger'); return redirect(url_for('admin.admin_user_edit', user_id=user_id))
        user.username = new_username
        user.email = new_email
        user.full_name = request.form.get('full_name')
        user.role = request.form.get('role','user')
        if request.form.get('password'):
            user.password = generate_password_hash(request.form.get('password'))
        db.session.commit()
        flash('کاربر بروزرسانی شد', 'success'); return redirect(url_for('admin.admin_users'))
    return render_template('admin_user_form.html', user=user)

@admin_bp.route('/users/delete/<int:user_id>', methods=['POST'], endpoint='admin_user_delete')
@login_required
@admin_required
def admin_user_delete(user_id):
    user = User.query.get_or_404(user_id)
    if user.username == 'admin':
        flash('ادمین اصلی قابل حذف نیست', 'danger'); return redirect(url_for('admin.admin_users'))
    db.session.delete(user)
    db.session.commit()
    flash('کاربر حذف شد', 'success'); return redirect(url_for('admin.admin_users'))
