# FILE: app/blueprints/wiki/routes.py
import os
import re
import json
import uuid
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    current_app, jsonify, send_from_directory, Response, abort, send_file
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from slugify import slugify

from datetime import datetime, timezone
from typing import Dict, Any
import logging
logger = logging.getLogger(__name__)


# اگر تابع allowed_file تعریف نشده، این را اضافه کن (یا از ps بیاور)
def allowed_file(filename: str) -> bool:
    """چک می‌کند آیا پسوند فایل مجاز است یا نه"""
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'mp4', 'mov', 'webm'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

# try to import extensions & models; fall back gracefully if not present
try:
    from ...extensions import db  # type: ignore
except Exception:
    db = None  # type: ignore

try:
    from ...models import Page, Comment, User  # type: ignore
except Exception:
    Page = Comment = User = None  # type: ignore

# try to import page service helpers
try:
    from ...services import page_service as ps  # type: ignore
except Exception:
    ps = None  # type: ignore

wiki_bp = Blueprint('wiki', __name__, template_folder='templates')


# -------------------- Path helpers / defaults --------------------
def _paths() -> Dict[str, Path]:
    """
    Return important filesystem paths. Prefer page_service._paths() if available.
    """
    if ps and hasattr(ps, '_paths'):
        try:
            p = ps._paths()
            return {k: Path(v) for k, v in p.items()}
        except Exception:
            current_app.logger.exception("ps._paths failed; falling back to defaults")

    root = Path(current_app.root_path)
    pages = Path(current_app.config.get('PAGES_DIR', root / 'pages'))
    uploads = Path(current_app.config.get('UPLOADS_DIR', root / 'uploads'))
    media = Path(current_app.config.get('MEDIA_ROOT', root / 'media'))
    videos = Path(current_app.config.get('VIDEO_FOLDER', media / 'videos'))
    tmp = Path(current_app.config.get('TMP_UPLOADS', media / 'tmp_uploads'))

    # ensure directories exist
    for d in (pages, uploads, media, videos, tmp):
        try:
            d.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    return {
        'ROOT': root,
        'PAGES_DIR': pages,
        'UPLOADS_DIR': uploads,
        'MEDIA_ROOT': media,
        'VIDEO_FOLDER': videos,
        'TMP_UPLOADS': tmp
    }


def _page_file_path(slug: str) -> str:
    """File path for a page slug. Prefer ps._page_file_path if available."""
    if ps and hasattr(ps, '_page_file_path'):
        try:
            return ps._page_file_path(slug)
        except Exception:
            current_app.logger.exception("ps._page_file_path failed; using fallback")
    return str(_paths()['PAGES_DIR'] / f"{slug}.html")


# -------------------- Utility helpers --------------------
def _allowed_file(name: str) -> bool:
    if ps and hasattr(ps, 'allowed_file'):
        try:
            return ps.allowed_file(name)
        except Exception:
            current_app.logger.exception("ps.allowed_file failed; falling back")
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    allowed = set(current_app.config.get('ALLOWED_EXTENSIONS', ['png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'mp4', 'webm', 'mov', 'mkv', 'avi', 'svg']))
    return ext in allowed


def _allowed_video(name: str) -> bool:
    if ps and hasattr(ps, 'allowed_video'):
        try:
            return ps.allowed_video(name)
        except Exception:
            current_app.logger.exception("ps.allowed_video failed; falling back")
    ext = name.rsplit('.', 1)[-1].lower() if '.' in name else ''
    allowed = set(current_app.config.get('ALLOWED_VIDEO_EXT', ['mp4', 'webm', 'mov', 'mkv', 'avi']))
    return ext in allowed


def _unique_filename(name: str) -> str:
    if ps and hasattr(ps, 'unique_filename'):
        try:
            return ps.unique_filename(name)
        except Exception:
            current_app.logger.exception("ps.unique_filename failed; falling back")
    safe = secure_filename(name)
    if '.' in safe:
        ext = safe.rsplit('.', 1)[1].lower()
        return f"{uuid.uuid4().hex}.{ext}"
    return uuid.uuid4().hex


# -------------------- Range-support for video streaming --------------------
def send_file_partial(path: str, mimetype: str = 'video/mp4'):
    """
    Support HTTP Range header for partial video streaming.
    """
    try:
        range_header = request.headers.get('Range', None)
        file_size = os.path.getsize(path)
        if not range_header:
            return send_file(path, conditional=True, mimetype=mimetype)
        m = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if not m:
            return send_file(path, conditional=True, mimetype=mimetype)
        start = int(m.group(1))
        end = m.group(2)
        if end:
            end = int(end)
        else:
            end = file_size - 1
        if start >= file_size:
            return Response(status=416)
        length = end - start + 1
        with open(path, 'rb') as f:
            f.seek(start)
            data = f.read(length)
        rv = Response(data, 206, mimetype=mimetype, direct_passthrough=True)
        rv.headers.add('Content-Range', f'bytes {start}-{end}/{file_size}')
        rv.headers.add('Accept-Ranges', 'bytes')
        rv.headers.add('Content-Length', str(length))
        return rv
    except Exception:
        current_app.logger.exception("send_file_partial failed")
        return abort(500)


# -------------------- Template globals --------------------
@wiki_bp.app_template_global()
def list_pages_global() -> List[str]:
    """
    Template helper: list pages (slugs).
    Prefer ps.list_pages, otherwise scan pages directory.
    """
    if ps and hasattr(ps, 'list_pages'):
        try:
            return ps.list_pages()
        except Exception:
            current_app.logger.exception("ps.list_pages failed; fallback to file scan")
    try:
        pages_dir = _paths()['PAGES_DIR']
        return sorted([p.stem for p in pages_dir.glob('*.html')])
    except Exception:
        return []


@wiki_bp.app_template_global()
def extract_tags_from_page(path: str) -> List[str]:
    """
    Template helper: extract tags from a page file.
    Prefer ps.extract_tags_from_page() if available.
    """
    if ps and hasattr(ps, 'extract_tags_from_page'):
        try:
            return ps.extract_tags_from_page(path)
        except Exception:
            current_app.logger.exception("ps.extract_tags_from_page failed; fallback")
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            txt = fh.read()
        m = re.search(r'<!--TAGS:(.*?)-->', txt, re.S)
        if m:
            return [t.strip() for t in m.group(1).split(',') if t.strip()]
    except Exception:
        pass
    return []


# -------------------- Routes --------------------
@wiki_bp.route('/', endpoint='index')
def index():
    """
    Home / recent pages list.
    """
    search = request.args.get('search') or request.args.get('q') or ''
    search = search.strip()
    pages_out: List[dict] = []
    all_tags_set = set()

    # Prefer DB Page model when available
    if Page is not None:
        try:
            q = Page.query.order_by(Page.updated_at.desc())  # type: ignore
            if search:
                like = f"%{search}%"
                q = q.filter((Page.title.ilike(like)) | (Page.excerpt.ilike(like)) | (Page.tags.ilike(like)))  # type: ignore
            pages_meta = q.limit(500).all()
            for p in pages_meta:
                tags_list = [t.strip() for t in (p.tags or "").split(',') if t.strip()]
                try:
                    gallery = json.loads(p.gallery) if p.gallery else []
                except Exception:
                    gallery = []
                try:
                    videos = json.loads(p.videos) if p.videos else []
                except Exception:
                    videos = []
                try:
                    personnel = json.loads(p.personnel) if p.personnel else []
                except Exception:
                    personnel = []
                pages_out.append({
                    'slug': p.slug,
                    'title': p.title or p.slug.replace('-', ' '),
                    'subtitle': p.subtitle or '',
                    'excerpt': p.excerpt or '',
                    'tags': tags_list,
                    'feature_image': p.feature_image,
                    'gallery': gallery,
                    'videos': videos,
                    'personnel': personnel
                })
                for t in tags_list:
                    all_tags_set.add(t)
        except Exception:
            current_app.logger.exception("index: DB path failed; falling back to file scan")

    # Fallback: scan page files
    if not pages_out:
        for slug in list_pages_global():
            path = _page_file_path(slug)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    txt = fh.read()
            except Exception:
                txt = ''
            m = re.search(r'<h[1-3][^>]*>(.*?)</h[1-3]>', txt, re.I)
            title = m.group(1).strip() if m else slug.replace('-', ' ')
            excerpt = re.sub(r'<[^>]+>', ' ', txt)[:300].strip()
            tags_list = extract_tags_from_page(path)
            pages_out.append({'slug': slug, 'title': title, 'subtitle': '', 'excerpt': excerpt, 'tags': tags_list, 'feature_image': None, 'gallery': [], 'videos': [], 'personnel': []})
            for t in tags_list:
                all_tags_set.add(t)

    all_tags = sorted(list(all_tags_set), key=lambda s: s.lower())
    return render_template('index.html', pages=pages_out, all_tags=all_tags, search_query=search)


def allowed_file(filename: str) -> bool:
    """چک می‌کند آیا پسوند فایل مجاز است یا نه"""
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'mp4', 'mov', 'webm'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions


@wiki_bp.route('/edit/new', methods=['GET', 'POST'], endpoint='edit_page_new')
@wiki_bp.route('/edit/<path:page_slug>', methods=['GET', 'POST'], endpoint='edit_page')
@login_required
def edit_page(page_slug: Optional[str] = None):
    role = getattr(current_user, 'role', 'user') if current_user.is_authenticated else 'user'
    if role not in ['admin', 'editor']:
        flash('دسترسی ندارید', 'danger')
        return redirect(url_for('wiki.index'))

    is_new = page_slug is None or page_slug == 'new'
    page = None

    # مقادیر پیش‌فرض
    title = ""
    subtitle = ""
    content = ""
    tags = ""
    feature_image = None
    gallery = []
    videos = []
    personnel = []
    excerpt = ""

    # بارگذاری صفحه موجود (اگر ویرایش باشد)
    if not is_new:
        path = _page_file_path(page_slug)
        if os.path.exists(path):
            try:
                if ps and hasattr(ps, 'parse_page_meta_and_body'):
                    parsed = ps.parse_page_meta_and_body(path) or {}
                    content = parsed.get('body', '')
                    meta = parsed.get('meta_fields', {})
                    title = meta.get('title', title)
                    subtitle = meta.get('subtitle', subtitle)
                    excerpt = meta.get('excerpt', excerpt)
                    tags = meta.get('tags', tags)
                    gallery = meta.get('gallery', gallery)
                    videos = meta.get('videos', videos)
                    personnel = meta.get('personnel', personnel)
                else:
                    with open(path, 'r', encoding='utf-8') as f:
                        txt = f.read()
                    m = re.match(r'^(<!--.*?-->)\s*(.*)', txt, re.DOTALL)
                    if m:
                        meta_txt = m.group(1)
                        content = m.group(2).strip()
                        for key in ['TAGS', 'SUBTITLE', 'EXCERPT', 'GALLERY', 'VIDEOS', 'PERSONNEL']:
                            mm = re.search(rf'<!--{key}:(.*?)-->', meta_txt, re.DOTALL)
                            if mm:
                                val = mm.group(1).strip()
                                if key == 'TAGS':
                                    tags = val
                                elif key == 'SUBTITLE':
                                    subtitle = val
                                elif key == 'EXCERPT':
                                    excerpt = val
                                elif key == 'GALLERY':
                                    try: gallery = json.loads(val)
                                    except: gallery = []
                                elif key == 'VIDEOS':
                                    try: videos = json.loads(val)
                                    except: videos = []
                                elif key == 'PERSONNEL':
                                    try: personnel = json.loads(val)
                                    except: personnel = []
                    else:
                        content = txt

                m2 = re.search(r'<h[1-6].*?>(.*?)</h[1-6]>', content, re.I)
                title = m2.group(1).strip() if m2 else title
            except Exception:
                current_app.logger.exception("خطا در خواندن فایل صفحه موجود")

        # Overlay با دیتابیس (اولویت بالاتر)
        if Page is not None:
            try:
                p = Page.query.filter_by(slug=page_slug).first()
                if p:
                    page = p
                    title = p.title or title
                    subtitle = p.subtitle or subtitle
                    excerpt = p.excerpt or excerpt
                    tags = p.tags or tags
                    feature_image = p.feature_image or feature_image
                    gallery = p.get_gallery() or gallery
                    videos = p.get_videos() or videos
                    personnel = p.get_personnel() or personnel
                    content = p.content or content
            except Exception:
                current_app.logger.exception("خطا در لود متادیتا از دیتابیس")

    # پردازش POST (ذخیره)
    if request.method == 'POST':
        try:
            title = request.form.get('page_title', title or 'بدون عنوان').strip()
            subtitle = request.form.get('subtitle', subtitle).strip()
            excerpt = request.form.get('excerpt', excerpt).strip()
            tags = request.form.get('tags', tags).strip()
            content = request.form.get('content', content).strip()

            # ===== دریافت لیست فایل‌های قدیمی از فرم =====
            existing_gallery = []
            existing_videos = []

            if request.form.get('existing_gallery'):
                try:
                    existing_gallery = json.loads(request.form.get('existing_gallery'))
                except json.JSONDecodeError:
                    existing_gallery = []

            if request.form.get('existing_videos'):
                try:
                    existing_videos = json.loads(request.form.get('existing_videos'))
                except json.JSONDecodeError:
                    existing_videos = []
            # ============================================

            # پردازش personnel
            personnel_raw = request.form.get('personnel', '[]')
            try:
                personnel = json.loads(personnel_raw)
                personnel = [p for p in personnel if isinstance(p, dict) and p.get('name')]
            except json.JSONDecodeError:
                personnel = []
                current_app.logger.warning("JSON پرسنل نامعتبر بود")

            # slug جدید
            new_slug = slugify(title, lowercase=True, allow_unicode=True) or uuid.uuid4().hex[:12]

            # ===== پردازش تصویر شاخص =====
            feature_image = None
            if 'feature_image' in request.files:
                file = request.files['feature_image']
                if file and file.filename and allowed_file(file.filename):
                    ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                    unique_name = f"{uuid.uuid4().hex}.{ext}"
                    dest = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
                    file.save(dest)
                    feature_image = unique_name
            # اگر فایل جدیدی آپلود نشده و صفحه قبلاً تصویر داشته، مقدار قبلی را حفظ کن
            if not feature_image and not is_new and page:
                feature_image = page.feature_image

            # ===== پردازش گالری تصاویر =====
            new_gallery = []
            if 'gallery_images[]' in request.files:
                files = request.files.getlist('gallery_images[]')
                for file in files:
                    if file and file.filename and allowed_file(file.filename):
                        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                        unique_name = f"{uuid.uuid4().hex}.{ext}"
                        dest = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_name)
                        file.save(dest)
                        new_gallery.append(unique_name)

            # ترکیب لیست قدیمی و جدید
            gallery = existing_gallery + new_gallery

            # ===== پردازش ویدیوها =====
            new_videos = []
            if 'videos[]' in request.files:
                files = request.files.getlist('videos[]')
                for file in files:
                    if file and file.filename and _allowed_video(file.filename):
                        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                        unique_name = f"{uuid.uuid4().hex}.{ext}"
                        dest = os.path.join(_paths()['VIDEO_FOLDER'], unique_name)
                        file.save(dest)
                        new_videos.append(unique_name)

            videos = existing_videos + new_videos

            # ===== ساخت متا برای فایل (اختیاری) =====
            meta_parts = [
                f"<!--TAGS:{tags}-->",
                f"<!--SUBTITLE:{subtitle}-->",
                f"<!--EXCERPT:{excerpt}-->",
                f"<!--GALLERY:{json.dumps(gallery, ensure_ascii=False)}-->",
                f"<!--VIDEOS:{json.dumps(videos, ensure_ascii=False)}-->",
                f"<!--PERSONNEL:{json.dumps(personnel, ensure_ascii=False)}-->"
            ]
            meta = "\n".join(meta_parts) + "\n"

            # مسیر فایل جدید
            file_path = _page_file_path(new_slug)

            # نوشتن فایل به صورت اتمیک
            tmp_path = Path(file_path).with_suffix('.tmp')
            tmp_path.write_text(meta + content, encoding='utf-8')
            tmp_path.replace(Path(file_path))

            # ===== ذخیره در دیتابیس =====
            if Page is not None:
                try:
                    p = Page.query.filter_by(slug=new_slug).first()
                    if not p:
                        p = Page(slug=new_slug)
                        db.session.add(p)
                    p.title = title
                    p.subtitle = subtitle
                    p.excerpt = excerpt
                    p.tags = tags
                    p.feature_image = feature_image
                    p.gallery = json.dumps(gallery, ensure_ascii=False) if gallery else None
                    p.videos = json.dumps(videos, ensure_ascii=False) if videos else None
                    p.personnel = json.dumps(personnel, ensure_ascii=False) if personnel else None
                    p.content = content
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    current_app.logger.exception("خطا در ذخیره متادیتا در دیتابیس")

            # حذف فایل/رکورد قدیمی اگر slug تغییر کرده
            if not is_new and page_slug != new_slug:
                old_path = _page_file_path(page_slug)
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception:
                    pass
                try:
                    if Page is not None:
                        old_p = Page.query.filter_by(slug=page_slug).first()
                        if old_p:
                            db.session.delete(old_p)
                            db.session.commit()
                except Exception:
                    pass

            flash('صفحه با موفقیت ذخیره شد', 'success')
            return redirect(url_for('wiki.view_page', page_name=new_slug))

        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("خطا در ذخیره صفحه")
            flash(f'خطا در ذخیره: {str(e)}', 'danger')

    # آماده‌سازی برای GET یا خطا در POST
    gallery_urls = []
    for g in gallery:
        if g:
            gallery_urls.append(url_for('auth.uploads_file', filename=g))

    video_urls = []
    for v in videos:
        if v:
            video_urls.append(url_for('wiki.stream_video', filename=v))

    feature_image_url = url_for('auth.uploads_file', filename=feature_image) if feature_image else None

    return render_template(
        'edit.html',
        is_new=is_new,
        page_slug=page_slug,
        title=title,
        subtitle=subtitle,
        content=content,
        tags=tags,
        feature_image=feature_image,
        feature_image_url=feature_image_url,
        gallery=gallery,
        gallery_urls=gallery_urls,
        videos=videos,
        video_urls=video_urls,
        personnel=personnel,
        excerpt=excerpt
    )

# -------------------- API: save / delete --------------------
@wiki_bp.route('/api/page/save', methods=['POST'], endpoint='api_page_save')
@login_required
def api_page_save():
    if getattr(current_user, 'role', 'user') not in ['admin', 'editor']:
        return jsonify({'success': False, 'error': 'forbidden'}), 403

    title = request.form.get('title') or request.form.get('page_title') or 'بدون عنوان'
    subtitle = request.form.get('subtitle') or ''
    excerpt_field = request.form.get('excerpt') or ''
    content = request.form.get('content') or ''
    tags = request.form.get('tags') or ''
    slug_provided = request.form.get('slug')

    try:
        from slugify import slugify as _slugify
        slug = slug_provided or _slugify(title, lowercase=True, allow_unicode=True) or uuid.uuid4().hex
    except Exception:
        slug = slug_provided or uuid.uuid4().hex

    file_path = _page_file_path(slug)

    # remove first heading if present (clients sometimes include it)
    if title and re.search(r'<h[1-6].*?>(.*?)</h[1-6]>', content):
        content = re.sub(r'<h[1-6].*?>(.*?)</h[1-6]>', '', content, count=1).strip()
    if title:
        content = f'<h1>{title}</h1>\n' + content

    feature_image = None
    gallery = []
    videos = []
    personnel = []

    existing = None
    if Page is not None:
        existing = Page.query.filter_by(slug=slug).first()  # type: ignore
    if existing:
        feature_image = existing.feature_image
        try:
            gallery = json.loads(existing.gallery) if existing.gallery else []
        except Exception:
            gallery = []
        try:
            videos = json.loads(existing.videos) if existing.videos else []
        except Exception:
            videos = []
        try:
            personnel = json.loads(existing.personnel) if existing.personnel else []
        except Exception:
            personnel = []

    # feature image
    if 'feature_image' in request.files:
        fimg = request.files['feature_image']
        if fimg and fimg.filename and _allowed_file(fimg.filename):
            try:
                if ps and hasattr(ps, 'process_image_and_save'):
                    res = ps.process_image_and_save(fimg, fimg.filename)
                    feature_image = res.get('filename')
                    if res.get('url') and res['url'] not in content:
                        content = f'<div style="text-align:center;margin-bottom:15px;"><img src="{res["url"]}" class="img-fluid"></div>' + content
                else:
                    outname = _unique_filename(fimg.filename)
                    fimg.save(str(_paths()['UPLOADS_DIR'] / outname))
                    feature_image = outname
                    content = f'<div style="text-align:center;margin-bottom:15px;"><img src="{url_for("wiki.uploaded_file", filename=outname)}" class="img-fluid"></div>' + content
            except Exception:
                current_app.logger.exception("feature image failed")

    # gallery existing + new
    existing_gallery = request.form.getlist('gallery_images') or []
    gallery = [g for g in existing_gallery if g]
    if 'gallery_images' in request.files:
        files = request.files.getlist('gallery_images')
        for fi in files:
            if fi and fi.filename and _allowed_file(fi.filename):
                try:
                    if ps and hasattr(ps, 'process_image_and_save'):
                        r = ps.process_image_and_save(fi, fi.filename)
                        if r.get('filename') and r['filename'] not in gallery:
                            gallery.append(r['filename'])
                    else:
                        out = _unique_filename(fi.filename)
                        fi.save(str(_paths()['UPLOADS_DIR'] / out))
                        if out not in gallery:
                            gallery.append(out)
                except Exception:
                    current_app.logger.exception("gallery save failed")

    # videos
    existing_videos = request.form.getlist('selected_videos') or []
    videos = [v for v in existing_videos if v]
    if 'videos' in request.files:
        files = request.files.getlist('videos')
        for fi in files:
            if fi and fi.filename and _allowed_video(fi.filename):
                fname = _unique_filename(fi.filename)
                dest = _paths()['VIDEO_FOLDER'] / fname
                try:
                    fi.save(str(dest))
                    if fname not in videos:
                        videos.append(fname)
                except Exception:
                    current_app.logger.exception("video save failed")

    # personnel
    personnel_json = request.form.get('personnel')
    if personnel_json:
        try:
            parsed = json.loads(personnel_json)
            personnel = [p for p in parsed if isinstance(p, dict) and p.get('name')]
        except Exception:
            current_app.logger.exception("personnel parse failed")

    meta = f"""<!--TAGS:{tags}-->
<!--SUBTITLE:{subtitle}-->
<!--EXCERPT:{excerpt_field}-->
<!--GALLERY:{json.dumps(gallery, ensure_ascii=False)}-->
<!--VIDEOS:{json.dumps(videos, ensure_ascii=False)}-->
<!--PERSONNEL:{json.dumps(personnel, ensure_ascii=False)}-->
"""
    try:
        # atomic write
        tmp = Path(file_path).with_suffix('.tmp')
        tmp.write_text(meta + content, encoding='utf-8')
        Path(file_path).write_text('', encoding='utf-8')
        tmp.replace(Path(file_path))
    except Exception:
        current_app.logger.exception("api_page_save file write failed")

    excerpt_plain = excerpt_field or re.sub(r'<[^>]+>', ' ', content)[:600].strip()
    try:
        if ps and hasattr(ps, 'ensure_page_metadata'):
            ps.ensure_page_metadata(slug, title, subtitle, excerpt_plain, tags, feature_image, gallery, videos, personnel)
        elif Page is not None:
            p = Page.query.filter_by(slug=slug).first()  # type: ignore
            if not p:
                p = Page(slug=slug, title=title, subtitle=subtitle, excerpt=excerpt_plain, tags=tags, feature_image=feature_image, gallery=json.dumps(gallery, ensure_ascii=False), videos=json.dumps(videos, ensure_ascii=False), personnel=json.dumps(personnel, ensure_ascii=False))  # type: ignore
                db.session.add(p)  # type: ignore
            else:
                p.title = title; p.subtitle = subtitle; p.excerpt = excerpt_plain; p.tags = tags; p.feature_image = feature_image
                p.gallery = json.dumps(gallery, ensure_ascii=False); p.videos = json.dumps(videos, ensure_ascii=False); p.personnel = json.dumps(personnel, ensure_ascii=False)
            db.session.commit()  # type: ignore
    except Exception:
        current_app.logger.exception("api_page_save metadata failed")

    return jsonify({'success': True, 'slug': slug, 'url': url_for('wiki.view_page', page_name=slug)})


@wiki_bp.route('/api/page/delete', methods=['POST'], endpoint='api_page_delete')
@login_required
def api_page_delete():
    if getattr(current_user, 'role', 'user') != 'admin':
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    data = request.get_json(force=True, silent=True) or {}
    slug = data.get('slug') or request.form.get('slug')
    if not slug:
        return jsonify({'success': False, 'error': 'slug required'}), 400
    path = _page_file_path(slug)
    try:
        if os.path.exists(path):
            os.remove(path)
        if Page is not None:
            p = Page.query.filter_by(slug=slug).first()  # type: ignore
            if p:
                db.session.delete(p)  # type: ignore
                db.session.commit()  # type: ignore
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.exception("api_page_delete failed")
        return jsonify({'success': False, 'error': str(e)}), 500


# -------------------- CKEditor upload (single-file) --------------------
@wiki_bp.route('/upload_file', methods=['POST'], endpoint='upload_file')
@login_required
def upload_file():
    file = request.files.get('upload')
    if not file:
        return jsonify({'error': {'message': 'فایل ارسال نشد'}}), 400
    if file.filename == '':
        return jsonify({'error': {'message': 'نام فایل خالی است'}}), 400
    if not _allowed_file(file.filename):
        return jsonify({'error': {'message': 'فرمت مجاز نیست'}}), 400

    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    max_upload = current_app.config.get('CKEDITOR_MAX_UPLOAD', 200 * 1024 * 1024)
    if size > max_upload:
        return jsonify({'error': {'message': 'حجم فایل بیش از حد مجاز است'}}), 413

    ext = file.filename.rsplit('.', 1)[1].lower()
    try:
        if ext in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
            if ps and hasattr(ps, 'process_image_and_save'):
                res = ps.process_image_and_save(file, file.filename)
                url = res.get('url')
            else:
                out = _unique_filename(file.filename)
                path = str(_paths()['UPLOADS_DIR'] / out)
                tmp = path + '.tmp'
                file.stream.seek(0)
                with open(tmp, 'wb') as fh:
                    fh.write(file.stream.read())
                os.replace(tmp, path)
                url = url_for('wiki.uploaded_file', filename=out)
        else:
            fname = _unique_filename(file.filename)
            path = os.path.join(str(_paths()['UPLOADS_DIR']), fname)
            tmp = path + '.tmp'
            file.stream.seek(0)
            with open(tmp, 'wb') as fh:
                fh.write(file.stream.read())
            os.replace(tmp, path)
            url = url_for('wiki.uploaded_file', filename=fname)
        return jsonify({'uploaded': 1, 'fileName': os.path.basename(url), 'url': url})
    except Exception as e:
        current_app.logger.exception("CKEditor upload failed")
        return jsonify({'error': {'message': str(e)}}), 500


# -------------------- Video chunking API (compatibility) --------------------
@wiki_bp.route('/video/upload/start', methods=['POST'], endpoint='video_upload_start')
@login_required
def video_upload_start():
    data = request.get_json(force=True, silent=True) or {}
    filename = data.get('filename')
    total_size = int(data.get('total_size') or 0)
    if not filename or total_size <= 0:
        return jsonify({'error': 'filename and total_size required'}), 400
    if not _allowed_video(filename):
        return jsonify({'error': 'invalid video format'}), 400

    upload_id = uuid.uuid4().hex
    session_dir = os.path.join(str(_paths()['TMP_UPLOADS']), upload_id)
    os.makedirs(session_dir, exist_ok=True)
    meta = {'filename': secure_filename(filename), 'total_size': total_size, 'received_chunks': 0}
    with open(os.path.join(session_dir, 'meta.json'), 'w', encoding='utf-8') as fh:
        json.dump(meta, fh)
    return jsonify({'upload_id': upload_id, 'chunk_size': current_app.config.get('DEFAULT_CHUNK_SIZE', 8 * 1024 * 1024)})


@wiki_bp.route('/video/upload/chunk', methods=['POST'], endpoint='video_upload_chunk')
@login_required
def video_upload_chunk():
    upload_id = request.form.get('upload_id') or request.args.get('upload_id')
    index = request.form.get('index') or request.args.get('index')
    chunk = request.files.get('chunk')
    if not upload_id or index is None or chunk is None:
        return jsonify({'error': 'upload_id, index and chunk required'}), 400
    try:
        idx = int(index)
    except Exception:
        return jsonify({'error': 'index must be int'}), 400

    session_dir = os.path.join(str(_paths()['TMP_UPLOADS']), upload_id)
    if not os.path.exists(session_dir):
        return jsonify({'error': 'invalid upload_id'}), 400

    chunk_path = os.path.join(session_dir, f'chunk_{idx:06d}.part')
    chunk.stream.seek(0)
    with open(chunk_path + '.tmp', 'wb') as f:
        f.write(chunk.stream.read())
    os.replace(chunk_path + '.tmp', chunk_path)

    try:
        meta_path = os.path.join(session_dir, 'meta.json')
        with open(meta_path, 'r+', encoding='utf-8') as fh:
            meta = json.load(fh)
            meta['received_chunks'] = meta.get('received_chunks', 0) + 1
            fh.seek(0); fh.truncate(0); json.dump(meta, fh)
    except Exception:
        current_app.logger.exception("Failed to update meta")

    return jsonify({'ok': True, 'index': idx})


@wiki_bp.route('/video/upload/complete', methods=['POST'], endpoint='video_upload_complete')
@login_required
def video_upload_complete():
    data = request.get_json(force=True, silent=True) or {}
    upload_id = data.get('upload_id')
    if not upload_id:
        return jsonify({'error': 'upload_id required'}), 400
    session_dir = os.path.join(str(_paths()['TMP_UPLOADS']), upload_id)
    meta_path = os.path.join(session_dir, 'meta.json')
    if not os.path.exists(meta_path):
        return jsonify({'error': 'invalid upload_id'}), 400
    with open(meta_path, 'r', encoding='utf-8') as fh:
        meta = json.load(fh)
    original_name = meta.get('filename')
    chunks = sorted([f for f in os.listdir(session_dir) if f.startswith('chunk_') and f.endswith('.part')])
    if not chunks:
        return jsonify({'error': 'no chunks uploaded'}), 400

    final_name = _unique_filename(original_name)
    final_path = os.path.join(str(_paths()['VIDEO_FOLDER']), final_name)

    with open(final_path + '.tmp', 'wb') as out_f:
        for ch in chunks:
            ch_path = os.path.join(session_dir, ch)
            with open(ch_path, 'rb') as cf:
                while True:
                    buf = cf.read(4 * 1024 * 1024)
                    if not buf:
                        break
                    out_f.write(buf)
    os.replace(final_path + '.tmp', final_path)
    actual_size = os.path.getsize(final_path)

    try:
        for f in os.listdir(session_dir):
            os.remove(os.path.join(session_dir, f))
        os.rmdir(session_dir)
    except Exception:
        current_app.logger.exception("Cleanup failed for session %s", upload_id)

    media_url = url_for('wiki.stream_video', filename=final_name)
    return jsonify({'success': True, 'filename': final_name, 'url': media_url, 'size': actual_size})


# -------------------- Serve uploads & videos --------------------
@wiki_bp.route('/uploads/<path:filename>', endpoint='uploaded_file')
def uploaded_file(filename: str):
    """
    Serve files from uploads or media root safely.

    اولویت‌ها:
    1. فایل واقعی در uploads یا media
    2. default_avatar.png در uploads (اگر وجود داشت)
    3. default_avatar.png در static (اگر در uploads نبود)
    4. در نهایت 404 ساده (بدون کرش)

    ویژگی‌ها:
    - حفاظت کامل در برابر path traversal
    - لاگ فقط برای موارد مهم (warning/info)
    - هیچ exception کلی وجود ندارد → پایدار
    """
    # مسیرهای پایه (مطلق و امن)
    uploads_root = os.path.abspath(str(_paths()['UPLOADS_DIR']))
    media_root = os.path.abspath(str(_paths()['MEDIA_ROOT']))
    static_root = os.path.abspath(current_app.static_folder or '')

    # نام پیش‌فرض آواتار (از config یا ثابت)
    default_name = current_app.config.get('DEFAULT_AVATAR', 'default_avatar.png')

    # 1. حفاظت در برابر path traversal
    candidate_upload = os.path.normpath(os.path.join(uploads_root, filename))
    if not candidate_upload.startswith(uploads_root + os.sep):
        current_app.logger.warning(f"Path traversal attempt: {filename}")
        abort(403)

    # 2. فایل در uploads → سرو مستقیم
    if os.path.isfile(candidate_upload):
        current_app.logger.debug(f"Serving from uploads: {filename}")
        return send_from_directory(uploads_root, filename)

    # 3. فایل در media (ویدیوها و فایل‌های بزرگ)
    candidate_media = os.path.normpath(os.path.join(media_root, filename))
    if candidate_media.startswith(media_root + os.sep) and os.path.isfile(candidate_media):
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        mime = {
            'mp4': 'video/mp4',
            'm4v': 'video/mp4',
            'mov': 'video/quicktime',
            'webm': 'video/webm',
        }.get(ext, 'application/octet-stream')
        current_app.logger.debug(f"Serving media file: {filename}")
        return send_file_partial(candidate_media, mimetype=mime)

    # 4. پیش‌فرض: اول در uploads نگاه کن
    default_upload = os.path.join(uploads_root, default_name)
    if os.path.isfile(default_upload):
        current_app.logger.info(f"Missing file → serving default from uploads: {filename}")
        return send_from_directory(uploads_root, default_name)

    # 5. اگر در uploads نبود → در static چک کن
    default_static = os.path.join(static_root, default_name)
    if os.path.isfile(default_static):
        current_app.logger.info(f"Missing file → serving default from static: {filename}")
        return send_from_directory(static_root, default_name)

    # 6. هیچ چیز پیدا نشد → 404 ساده + لاگ یک‌خطی
    current_app.logger.warning(f"File not found and no default available: {filename}")
    abort(404)


@wiki_bp.route('/media/videos/<path:filename>', endpoint='stream_video')
def stream_video(filename: str):
    path = str(_paths()['VIDEO_FOLDER'] / filename)
    if not os.path.exists(path):
        return "Not found", 404
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    mime = 'video/mp4' if ext in ('mp4', 'm4v') else ('video/webm' if ext == 'webm' else 'application/octet-stream')
    return send_file_partial(path, mimetype=mime)


# -------------------- Media list / delete endpoints --------------------
@wiki_bp.route('/media/list', endpoint='media_list')
@login_required
def media_list():
    try:
        files = sorted(os.listdir(str(_paths()['VIDEO_FOLDER'])), reverse=True)
        items = []
        for f in files:
            items.append({
                'filename': f,
                'url': url_for('wiki.stream_video', filename=f),
                'size': os.path.getsize(os.path.join(str(_paths()['VIDEO_FOLDER']), f))
            })
        return jsonify({'success': True, 'items': items})
    except Exception:
        current_app.logger.exception("media_list failed")
        return jsonify({'success': False, 'items': []})


@wiki_bp.route('/media/delete', methods=['POST'], endpoint='media_delete')
@login_required
def media_delete():
    if getattr(current_user, 'role', 'user') != 'admin':
        return jsonify({'success': False, 'error': 'forbidden'}), 403
    filename = request.form.get('filename') or (request.json and request.json.get('filename'))
    if not filename:
        return jsonify({'success': False, 'error': 'filename required'}), 400
    path = str(_paths()['VIDEO_FOLDER'] / filename)
    if os.path.exists(path):
        try:
            os.remove(path)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)}), 500
    return jsonify({'success': False, 'error': 'not found'}), 404


# -------------------- Comments API --------------------
def build_comment_html(comment_obj) -> str:
    user = getattr(comment_obj, 'user', None)
    if not user:
        username = 'کاربر'
        avatar = current_app.config.get('DEFAULT_AVATAR', 'default_avatar.png')
    else:
        username = getattr(user, 'username', 'کاربر')
        avatar = getattr(user, 'avatar', current_app.config.get('DEFAULT_AVATAR', 'default_avatar.png'))

    avatar_url = url_for('wiki.uploaded_file', filename=avatar) + f'?v={int(getattr(user, "created_at", datetime.utcnow()).timestamp() if getattr(user, "created_at", None) else (uuid.uuid4().int & 0xffffffff))}'
    created = getattr(comment_obj, 'created_at', datetime.utcnow()).strftime('%Y-%m-%d %H:%M')
    content = getattr(comment_obj, 'content', '') if not getattr(comment_obj, 'deleted', False) else '[حذف‌شده]'

    can_edit = (current_user.is_authenticated and (getattr(current_user, 'id', None) == getattr(comment_obj, 'user_id', None) or getattr(current_user, 'role', None) == 'admin'))
    edit_buttons = ''
    if current_user.is_authenticated:
        edit_buttons += f'<a href="#" class="small js-reply" data-id="{getattr(comment_obj, "id", "")}">پاسخ</a>'
    if can_edit:
        edit_buttons += f' <a href="#" class="small ms-2 js-comment-edit" data-id="{getattr(comment_obj, "id", "")}">ویرایش</a>'
        edit_buttons += f' <a href="#" class="small text-danger ms-2 js-comment-delete" data-id="{getattr(comment_obj, "id", "")}">حذف</a>'

    children_html = ''
    for ch in getattr(comment_obj, 'children', []) or []:
        children_html += build_comment_html(ch)

    html = f'''
<div class="comment" id="comment-{getattr(comment_obj, "id", "")}">
  <div class="d-flex align-items-start mb-2">
    <img src="{avatar_url}" class="rounded-circle me-2" style="width:40px;height:40px;object-fit:cover;" alt="avatar">
    <div style="flex:1;">
      <div class="small text-muted"><strong>{username}</strong> <span class="text-secondary">· {created}</span></div>
      <div class="comment-body mt-1">{content}</div>
      <div class="mt-2">{edit_buttons}</div>
      <div class="replies mt-3">{children_html}</div>
    </div>
  </div>
</div>
'''
    return html


@wiki_bp.route('/api/comments/<path:page_name>', endpoint='api_comments')
def api_comments(page_name: str):
    """
    بازگشت لیست کامنت‌ها به صورت درختی (root + children) برای یک صفحه خاص.
    - فقط کامنت‌های حذف‌نشده (deleted=False) را برمی‌گرداند
    - رابطه user را لود می‌کند تا username و avatar در دسترس باشد
    - ساختار بازگشتی مناسب برای نمایش درختی در فرانت‌اند
    - مدیریت خطا با لاگ و پاسخ 500 امن
    """
    if Comment is None:
        return jsonify({
            'success': True,
            'comments': [],
            'message': 'سیستم کامنت فعال نیست'
        }), 200

    try:
        # لود تمام کامنت‌های صفحه (root + replies)
        comments = Comment.query.filter_by(
            page=page_name
        ).order_by(
            Comment.created_at.asc()
        ).all()

        # ساخت دیکشنری id → کامنت برای دسترسی سریع به parent
        comment_map = {c.id: c for c in comments}

        # ساخت ساختار درختی
        roots = []
        for comment in comments:
            # لود رابطه user (برای جلوگیری از lazy load در to_dict)
            _ = comment.user

            # فقط rootها را جمع می‌کنیم
            if comment.parent_id is None:
                roots.append(comment)

        def to_dict(c: Comment) -> dict:
            """
            تبدیل یک کامنت به دیکشنری قابل سریال‌سازی
            """
            user_obj = getattr(c, 'user', None)
            user_data = {
                'id': user_obj.id if user_obj else None,
                'username': user_obj.username if user_obj else 'کاربر ناشناس',
                'avatar_url': (
                    url_for('wiki.uploaded_file', filename=user_obj.avatar) +
                    f'?v={int(datetime.utcnow().timestamp())}'
                ) if user_obj and user_obj.avatar else
                  url_for('static', filename='images/default_avatar.png')
            }

            children = []
            # پیدا کردن تمام بچه‌های مستقیم این کامنت
            for child in comments:
                if child.parent_id == c.id and not getattr(child, 'deleted', False):
                    children.append(to_dict(child))

            return {
                'id': c.id,
                'page': c.page,
                'user': user_data,
                'parent_id': c.parent_id,
                'content': c.content or '',
                'created_at': c.created_at.isoformat() if c.created_at else None,
                'edited_at': c.edited_at.isoformat() if c.edited_at else None,
                'deleted': getattr(c, 'deleted', False),
                'can_edit': (
                    current_user.is_authenticated and
                    (current_user.id == c.user_id or getattr(current_user, 'role', None) == 'admin')
                ),
                'children': children
            }

        # فقط rootهایی که حذف نشده‌اند + فرزندانشان
        result = [
            to_dict(root)
            for root in roots
            if not getattr(root, 'deleted', False)
        ]

        return jsonify({
            'success': True,
            'comments': result,
            'count': len(result),
            'total_comments': len(comments)
        })

    except Exception as exc:
        current_app.logger.exception(
            f"خطا در بارگذاری کامنت‌های صفحه {page_name!r}: {exc}"
        )
        return jsonify({
            'success': False,
            'error': 'خطای سرور در بارگذاری کامنت‌ها',
            'message': str(exc) if current_app.debug else None
        }), 500


from datetime import datetime, timezone
from typing import Dict, Any




@wiki_bp.route('/page/<path:page_name>', methods=['GET'], endpoint='view_page')
def view_page(page_name: str):
    page = Page.query.filter_by(slug=page_name).first()
    if not page:
        flash('صفحه یافت نشد', 'danger')
        return redirect(url_for('wiki.index'))

    # دریافت لیست فایل‌ها از مدل
    gallery = page.get_gallery() or []
    videos = page.get_videos() or []
    personnel = page.get_personnel() or []

    # ساخت URL تصویر شاخص (در صورت وجود)
    feature_image_url = url_for('wiki.uploaded_file', filename=page.feature_image) if page.feature_image else None

    # ---------- دریافت و ساخت درخت کامنت‌ها ----------
    root_comments = []
    if Comment is not None:
        try:
            # همه کامنت‌های صفحه (حذف‌نشده) به ترتیب زمان
            comments = Comment.query.filter_by(
                page=page_name,
                deleted=False
            ).order_by(Comment.created_at.asc()).all()

            # لود رابطه user برای همه کامنت‌ها (جلوگیری از N+1)
            for c in comments:
                _ = c.user

            # دیکشنری برای دسترسی سریع فرزندان هر کامنت
            children_map = {}
            for c in comments:
                if c.parent_id not in children_map:
                    children_map[c.parent_id] = []
                children_map[c.parent_id].append(c)

            # ریشه‌ها (کامنت‌های بدون والد)
            root_comments = children_map.get(None, [])

            # به هر کامنت لیست فرزندانش را به‌صورت ویژگی اضافه می‌کنیم
            for c in comments:
                c.children = children_map.get(c.id, [])
        except Exception:
            current_app.logger.exception("خطا در دریافت کامنت‌ها برای صفحه %s", page_name)
            root_comments = []
    # ------------------------------------------------

    return render_template(
        'page.html',
        page=page,
        page_name=page_name,
        title=page.title,
        subtitle=page.subtitle,
        content=page.content,
        tags=page.tags.split(',') if page.tags else [],
        feature_image=page.feature_image,  # اضافه شد
        feature_image_url=feature_image_url,
        gallery=gallery,
        videos=videos,
        personnel=personnel,
        excerpt=page.excerpt,
        root_comments=root_comments
    )


@wiki_bp.route('/page/<path:page_name>/comment', methods=['POST'], endpoint='add_comment')
@login_required
def add_comment(page_name: str):
    content = request.form.get('content', '').strip()
    parent_id = request.form.get('parent_id', type=int, default=None)

    if not content:
        return jsonify({
            'success': False,
            'error': 'نظر نمی‌تواند خالی باشد'
        }), 400

    comment = Comment(
        page=page_name,
        user_id=current_user.id,
        content=content,
        parent_id=parent_id
    )
    db.session.add(comment)
    db.session.commit()

    # بارگذاری اطلاعات کاربر برای پاسخ
    user = current_user
    avatar_url = url_for('wiki.uploaded_file', filename=user.avatar) if user.avatar else url_for('static', filename='images/default_avatar.png')
    avatar_url += f'?v={int(datetime.utcnow().timestamp())}'  # جلوگیری از کش

    comment_data = {
        'id': comment.id,
        'parent_id': comment.parent_id,
        'content': comment.content,
        'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M'),
        'user': {
            'username': user.username,
            'avatar_url': avatar_url
        },
        'can_edit': True  # چون خود کاربر ارسال کرده
    }

    return jsonify({
        'success': True,
        'comment': comment_data
    }), 201





@wiki_bp.route('/comment/<int:c_id>/edit', methods=['POST'])
@login_required
def edit_comment(c_id: int) -> tuple[Dict[str, Any], int]:
    """
    ویرایش یک کامنت موجود.

    - فقط صاحب کامنت یا ادمین می‌تواند ویرایش کند
    - اعتبارسنجی محتوا (خالی نبودن، طول مجاز)
    - به‌روزرسانی فیلد edited_at
    - بازگشت اطلاعات به‌روزشده برای فرانت‌اند
    """
    if Comment is None:
        return jsonify({
            'success': False,
            'error': 'سیستم کامنت فعال نیست'
        }), 500

    try:
        comment = db.session.get(Comment, c_id)
        if not comment:
            return jsonify({
                'success': False,
                'error': 'کامنت یافت نشد'
            }), 404

        # چک مجوز ویرایش
        if comment.user_id != current_user.id and getattr(current_user, 'role', None) != 'admin':
            return jsonify({
                'success': False,
                'error': 'شما اجازه ویرایش این کامنت را ندارید'
            }), 403

        content = (request.form.get('content') or '').strip()
        if not content:
            return jsonify({
                'success': False,
                'error': 'محتوای کامنت نمی‌تواند خالی باشد'
            }), 400

        max_length = current_app.config.get('MAX_COMMENT_LENGTH', 4000)
        if len(content) > max_length:
            return jsonify({
                'success': False,
                'error': f'طول کامنت بیش از حد مجاز است (حداکثر {max_length} کاراکتر)'
            }), 400

        # اعمال تغییرات
        comment.content = content
        comment.edited_at = datetime.now(timezone.utc)

        db.session.commit()

        # لود مجدد برای اطمینان
        db.session.refresh(comment)
        _ = comment.user

        # ساخت HTML به‌روزشده
        html = build_comment_html(comment)

        # آواتار با timestamp
        avatar_filename = current_user.avatar if current_user.avatar else 'default_avatar.png'
        avatar_url = url_for('wiki.uploaded_file', filename=avatar_filename)
        avatar_url += f'?v={int(datetime.now(timezone.utc).timestamp())}'

        # پاسخ کامل برای فرانت‌اند
        comment_payload: Dict[str, Any] = {
            'id': comment.id,
            'parent_id': comment.parent_id,
            'content': comment.content,
            'html': html,
            'avatar_url': avatar_url,
            'user': {
                'username': current_user.username,
                'avatar_url': avatar_url
            },
            'created_at': (
                comment.created_at.strftime('%Y-%m-%d %H:%M')
                if comment.created_at else datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')
            ),
            'edited_at': (
                comment.edited_at.strftime('%Y-%m-%d %H:%M')
                if comment.edited_at else None
            ),
            'can_edit': True
        }

        return jsonify({
            'success': True,
            'comment': comment_payload
        }), 200

    except Exception as exc:
        db.session.rollback()
        logger.exception(f"خطا در ویرایش کامنت {c_id}: {exc}")
        return jsonify({
            'success': False,
            'error': 'خطای سرور در ویرایش کامنت',
            'message': str(exc) if current_app.debug else None
        }), 500


@wiki_bp.route('/page/<path:page_name>/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(page_name, comment_id):
    comment = Comment.query.get(comment_id)  # بدون get_or_404

    if not comment:
        return jsonify({
            'success': False,
            'error': 'کامنت یافت نشد یا قبلاً حذف شده است'
        }), 404

    if comment.user_id != current_user.id and getattr(current_user, 'role', None) != 'admin':
        return jsonify({
            'success': False,
            'error': 'شما اجازه حذف این کامنت را ندارید'
        }), 403

    try:
        db.session.delete(comment)
        db.session.commit()
        logger.info(f"کامنت {comment_id} در صفحه {page_name} توسط {current_user.username} حذف شد")
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logger.exception(f"خطا در حذف کامنت {comment_id}")
        return jsonify({
            'success': False,
            'error': 'خطا در حذف کامنت'
        }), 500



# -------------------- Suggest / Discover --------------------
@wiki_bp.route('/api/suggest', endpoint='api_suggest')
def api_suggest():
    q = request.args.get('q', '').strip()
    results: List[Dict[str, Any]] = []
    if not q:
        return jsonify({'results': []})
    try:
        if Page is not None:
            pages = Page.query.filter((Page.title.ilike(f'%{q}%')) | (Page.excerpt.ilike(f'%{q}%')) | (Page.tags.ilike(f'%{q}%'))).limit(20).all()  # type: ignore
            for p in pages:
                results.append({'title': p.title or p.slug, 'subtitle': (p.excerpt[:140] + '...') if p.excerpt and len(p.excerpt) > 140 else (p.excerpt or ''), 'type': 'صفحه', 'url': url_for('wiki.view_page', page_name=p.slug)})
                if len(results) >= 12:
                    break
    except Exception:
        current_app.logger.exception("api_suggest DB query failed")

    if len(results) < 12:
        for slug in list_pages_global():
            path = _page_file_path(slug)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    txt = fh.read()
            except Exception:
                continue
            title_m = re.search(r'<h[1-6].*?>(.*?)</h[1-6]>', txt, re.I)
            title = title_m.group(1).strip() if title_m else slug.replace('-', ' ')
            plain = re.sub(r'<[^>]+>', ' ', txt)
            if q.lower() in title.lower() or q.lower() in plain.lower():
                excerpt = plain[:140].strip()
                results.append({'title': title, 'subtitle': excerpt, 'type': 'صفحه', 'url': url_for('wiki.view_page', page_name=slug)})
            if len(results) >= 12:
                break

    return jsonify({'results': results})


@wiki_bp.route('/discover', endpoint='discover')
def discover():
    q = (request.args.get('q') or '').strip()
    tag_filter = (request.args.get('tag') or '').strip()
    page_num = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 12, type=int)

    items: List[Dict[str, Any]] = []
    tagset = set()
    # prefer DB
    if Page is not None:
        try:
            query = Page.query
            if q:
                like = f"%{q}%"
                query = query.filter((Page.title.ilike(like)) | (Page.excerpt.ilike(like)) | (Page.tags.ilike(like)))  # type: ignore
            pages_all = query.order_by(Page.updated_at.desc()).all()
            for p in pages_all:
                tags_list = [t.strip() for t in (p.tags or "").split(',') if t.strip()]
                for t in tags_list: tagset.add(t)
                items.append({'slug': p.slug, 'title': p.title or p.slug.replace('-', ' '), 'excerpt': p.excerpt or '', 'tags': tags_list, 'url': url_for('wiki.view_page', page_name=p.slug)})
        except Exception:
            current_app.logger.exception("discover DB fallback")
    # fallback to files
    if not items:
        for slug in list_pages_global():
            path = _page_file_path(slug)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    txt = fh.read()
            except Exception:
                txt = ''
            title_m = re.search(r'<h[1-3].*?>(.*?)</h[1-3]>', txt, re.I)
            title = title_m.group(1).strip() if title_m else slug.replace('-', ' ')
            excerpt = re.sub(r'<[^>]+>', ' ', txt)[:320].strip()
            tags_list = extract_tags_from_page(path)
            for t in tags_list: tagset.add(t)
            items.append({'slug': slug, 'title': title, 'excerpt': excerpt, 'tags': tags_list, 'url': url_for('wiki.view_page', page_name=slug)})

    if tag_filter:
        items = [it for it in items if tag_filter in it['tags']]

    if q:
        qlow = q.lower()
        items = [it for it in items if qlow in it['title'].lower() or qlow in it['excerpt'].lower() or any(qlow in t.lower() for t in it['tags'])]

    items.sort(key=lambda x: x['title'].lower())
    total = len(items)
    start = (page_num - 1) * per_page
    end = start + per_page
    page_items = items[start:end]
    all_tags = sorted(list(tagset), key=lambda s: s.lower())
    total_pages = max(1, (total + per_page - 1) // per_page)
    pagination = {'page': page_num, 'per_page': per_page, 'total': total, 'total_pages': total_pages}

    return render_template('discover.html', q=q, tag_filter=tag_filter, results=page_items, all_tags=all_tags, pagination=pagination)


# -------------------- Compatibility / convenience aliases --------------------
# Some templates call url_for('edit_page') without args.
# We provide a simple alias route name 'edit_page' that points to '/edit/new'.
try:
    wiki_bp.add_url_rule(
        '/edit/new',
        endpoint='edit_page',            # templates calling url_for('edit_page') will resolve (app registers alias)
        view_func=edit_page,
        methods=['GET', 'POST'],
        defaults={'page_slug': None}
    )
except Exception:
    # if blueprint already registered or alias exists, ignore
    current_app.logger.debug("Alias endpoint edit_page already exists or couldn't be added")
