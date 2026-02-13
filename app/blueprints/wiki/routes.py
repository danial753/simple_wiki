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


@wiki_bp.route('/page/<path:page_name>', endpoint='view_page')
def view_page(page_name: str):
    """
    Render a page from file (and DB meta if available).
    """
    path = _page_file_path(page_name)
    if not os.path.exists(path):
        flash('صفحه یافت نشد', 'warning')
        return redirect(url_for('wiki.index'))

    parsed = {}
    if ps and hasattr(ps, 'parse_page_meta_and_body'):
        try:
            parsed = ps.parse_page_meta_and_body(path) or {}
        except Exception:
            current_app.logger.exception("ps.parse_page_meta_and_body failed; fallback to manual read")

    content = parsed.get('body', '')
    if content == '':
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                content = fh.read()
        except Exception:
            content = ''

    title = page_name.replace('-', ' ').title()
    subtitle = ''
    excerpt = ''
    tags = extract_tags_from_page(path)
    feature_image = ''
    gallery: List[str] = []
    videos: List[str] = []
    personnel: List[dict] = []

    if Page is not None:
        try:
            p = Page.query.filter_by(slug=page_name).first()  # type: ignore
            if p:
                title = p.title or title
                subtitle = p.subtitle or subtitle
                excerpt = p.excerpt or excerpt
                tags = [t.strip() for t in (p.tags or "").split(',') if t.strip()] or tags
                feature_image = p.feature_image or feature_image
                try:
                    gallery = json.loads(p.gallery) if p.gallery else gallery
                except Exception:
                    gallery = gallery
                try:
                    videos = json.loads(p.videos) if p.videos else videos
                except Exception:
                    videos = videos
                try:
                    personnel = json.loads(p.personnel) if p.personnel else personnel
                except Exception:
                    personnel = personnel
        except Exception:
            current_app.logger.exception("view_page: DB meta overlay failed")

    root_comments = []
    if Comment is not None:
        try:
            root_comments = Comment.query.filter_by(page=page_name, parent_id=None).order_by(Comment.created_at.asc()).all()  # type: ignore
            for c in root_comments:
                _ = c.user
        except Exception:
            current_app.logger.exception("view_page: loading comments failed")

    paths = _paths()
    gallery_urls: List[str] = []
    for g in gallery:
        if not g:
            continue
        full_path = str(paths['UPLOADS_DIR'] / g)
        if os.path.exists(full_path):
            gallery_urls.append(url_for('wiki.uploaded_file', filename=g))
        else:
            current_app.logger.warning("Gallery image not found: %s", g)

    video_urls: List[str] = []
    for v in videos:
        if not v:
            continue
        full_path = str(paths['VIDEO_FOLDER'] / v)
        if os.path.exists(full_path):
            video_urls.append(url_for('wiki.stream_video', filename=v))
        else:
            current_app.logger.warning("Video not found: %s", v)

    feature_image_url = url_for('wiki.uploaded_file', filename=feature_image) if feature_image else ''

    return render_template(
        'page.html',
        page_name=page_name,
        content=content,
        tags=tags,
        root_comments=root_comments,
        subtitle=subtitle,
        gallery=gallery,
        gallery_urls=gallery_urls,
        videos=videos,
        video_urls=video_urls,
        personnel=personnel,
        page_meta=None,
        title=title,
        excerpt=excerpt,
        feature_image=feature_image,
        feature_image_url=feature_image_url
    )


# -------------------- Edit page (GET / POST) --------------------
# Note: templates sometimes call url_for('edit_page') without args.
# We'll ensure an alias exists later (in create_app or below).
@wiki_bp.route('/edit/new', methods=['GET', 'POST'], endpoint='edit_page_new')
@wiki_bp.route('/edit/<path:page_slug>', methods=['GET', 'POST'], endpoint='edit_page')
@login_required
def edit_page(page_slug: Optional[str] = None):
    role = getattr(current_user, 'role', 'user') if current_user else 'user'
    if role not in ['admin', 'editor']:
        flash('دسترسی ندارید', 'danger')
        return redirect(url_for('wiki.index'))

    is_new = page_slug is None
    content = ""
    title = ""
    subtitle = ""
    tags = ""
    feature_image = None
    gallery = []
    videos = []
    personnel = []
    excerpt_field = ""

    # load existing file if editing
    if page_slug:
        path = _page_file_path(page_slug)
        if os.path.exists(path):
            try:
                if ps and hasattr(ps, 'parse_page_meta_and_body'):
                    parsed = ps.parse_page_meta_and_body(path) or {}
                    content = parsed.get('body', '')
                    meta = parsed.get('meta_fields', {})
                    tags = meta.get('tags', tags)
                    subtitle = meta.get('subtitle', subtitle)
                    excerpt_field = meta.get('excerpt', excerpt_field)
                    gallery = meta.get('gallery', gallery)
                    videos = meta.get('videos', videos)
                    personnel = meta.get('personnel', personnel)
                else:
                    txt = Path(path).read_text(encoding='utf-8') if os.path.exists(path) else ''
                    m = re.match(r'^(<!--.*?-->)\s*(.*)', txt, re.S)
                    if m:
                        meta_txt = m.group(1)
                        content = m.group(2).strip()
                        tm = re.search(r'<!--TAGS:(.*?)-->', meta_txt, re.S)
                        if tm: tags = tm.group(1).strip()
                        sm = re.search(r'<!--SUBTITLE:(.*?)-->', meta_txt, re.S)
                        if sm: subtitle = sm.group(1).strip()
                        exm = re.search(r'<!--EXCERPT:(.*?)-->', meta_txt, re.S)
                        if exm: excerpt_field = exm.group(1).strip()
                        gm = re.search(r'<!--GALLERY:(.*?)-->', meta_txt, re.S)
                        if gm:
                            try:
                                gallery = json.loads(gm.group(1).strip())
                            except Exception:
                                gallery = []
                        vm = re.search(r'<!--VIDEOS:(.*?)-->', meta_txt, re.S)
                        if vm:
                            try:
                                videos = json.loads(vm.group(1).strip())
                            except Exception:
                                videos = []
                        pm = re.search(r'<!--PERSONNEL:(.*?)-->', meta_txt, re.S)
                        if pm:
                            try:
                                personnel = json.loads(pm.group(1).strip())
                            except Exception:
                                personnel = []
                    else:
                        content = txt
                m2 = re.search(r'<h[1-6].*?>(.*?)</h[1-6]>', content, re.I)
                title = m2.group(1).strip() if m2 else title
            except Exception:
                current_app.logger.exception("Failed to read existing page file")
        if Page is not None:
            try:
                p = Page.query.filter_by(slug=page_slug).first()  # type: ignore
                if p:
                    title = p.title or title
                    subtitle = p.subtitle or subtitle
                    excerpt_field = p.excerpt or excerpt_field
                    tags = p.tags or tags
                    feature_image = p.feature_image or feature_image
                    try:
                        gallery = json.loads(p.gallery) if getattr(p, 'gallery', None) else gallery
                    except Exception:
                        gallery = gallery
                    try:
                        videos = json.loads(p.videos) if getattr(p, 'videos', None) else videos
                    except Exception:
                        videos = videos
                    try:
                        personnel = json.loads(p.personnel) if getattr(p, 'personnel', None) else personnel
                    except Exception:
                        personnel = personnel
            except Exception:
                current_app.logger.exception("Overlay DB metadata failed")

    # handle POST (save)
    if request.method == 'POST':
        try:
            title = request.form.get('page_title', title or 'بدون عنوان').strip()
            subtitle = request.form.get('subtitle', subtitle or '').strip()
            excerpt_field = request.form.get('excerpt', excerpt_field or '').strip()
            tags = request.form.get('tags', tags or '').strip()
            body = request.form.get('content', content or '').strip()
            personnel_json = request.form.get('personnel_json', '')

            try:
                from slugify import slugify as _slugify  # type: ignore
                slug = _slugify(title, lowercase=True, allow_unicode=True) or uuid.uuid4().hex
            except Exception:
                slug = uuid.uuid4().hex

            file_path = _page_file_path(slug)

            # feature image upload
            fimg = request.files.get('feature_image')
            if fimg and fimg.filename and _allowed_file(fimg.filename):
                try:
                    if ps and hasattr(ps, 'process_image_and_save'):
                        res = ps.process_image_and_save(fimg, fimg.filename)
                        feature_image = res.get('filename', feature_image)
                        if res.get('url') and res['url'] not in body:
                            body = f'<img src="{res["url"]}" alt="feature" class="img-fluid mb-3">\n' + body
                    else:
                        outname = _unique_filename(fimg.filename)
                        dest = _paths()['UPLOADS_DIR'] / outname
                        fimg.save(str(dest))
                        feature_image = outname
                        body = f'<img src="{url_for("wiki.uploaded_file", filename=feature_image)}" alt="feature" class="img-fluid mb-3">\n' + body
                except Exception:
                    current_app.logger.exception("feature image save failed")

            # gallery uploads
            gallery = request.form.getlist('existing_gallery') or gallery
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
                                outname = _unique_filename(fi.filename)
                                fi.save(str(_paths()['UPLOADS_DIR'] / outname))
                                if outname not in gallery:
                                    gallery.append(outname)
                        except Exception:
                            current_app.logger.exception("gallery image save failed")

            # videos
            videos = request.form.getlist('existing_videos') or videos
            if 'videos' in request.files:
                files = request.files.getlist('videos')
                for fi in files:
                    if fi and fi.filename and _allowed_video(fi.filename):
                        outname = _unique_filename(fi.filename)
                        dest = _paths()['VIDEO_FOLDER'] / outname
                        try:
                            fi.save(str(dest))
                            if outname not in videos:
                                videos.append(outname)
                        except Exception:
                            current_app.logger.exception("video save failed")

            # personnel
            if personnel_json:
                try:
                    personnel = json.loads(personnel_json)
                except Exception:
                    personnel = []

            # normalize body/title
            if title and body.startswith(f'<h1>{title}</h1>'):
                body = body[len(f'<h1>{title}</h1>'):].strip()
            body = f'<h1>{title}</h1>\n' + body if title else body

            meta_parts = [
                f"<!--TAGS:{tags}-->",
                f"<!--SUBTITLE:{subtitle}-->",
                f"<!--EXCERPT:{excerpt_field}-->",
                f"<!--GALLERY:{json.dumps(gallery, ensure_ascii=False)}-->",
                f"<!--VIDEOS:{json.dumps(videos, ensure_ascii=False)}-->",
                f"<!--PERSONNEL:{json.dumps(personnel, ensure_ascii=False)}-->"
            ]
            meta = "\n".join(meta_parts) + "\n"

            # write atomically to avoid partial writes
            tmp_path = Path(file_path).with_suffix('.tmp')
            tmp_path.write_text(meta + body, encoding='utf-8')
            Path(file_path).write_text('', encoding='utf-8')  # ensure exists on Windows
            tmp_path.replace(Path(file_path))

            # attempt DB metadata upsert
            try:
                if ps and hasattr(ps, 'ensure_page_metadata'):
                    ps.ensure_page_metadata(slug, title, subtitle, excerpt_field, tags, feature_image, gallery, videos, personnel)
                elif Page is not None:
                    p = Page.query.filter_by(slug=slug).first()  # type: ignore
                    if not p:
                        p = Page(slug=slug, title=title, subtitle=subtitle, excerpt=excerpt_field, tags=tags, feature_image=feature_image, gallery=json.dumps(gallery, ensure_ascii=False), videos=json.dumps(videos, ensure_ascii=False), personnel=json.dumps(personnel, ensure_ascii=False))  # type: ignore
                        db.session.add(p)  # type: ignore
                    else:
                        p.title = title; p.subtitle = subtitle; p.excerpt = excerpt_field; p.tags = tags; p.feature_image = feature_image
                        p.gallery = json.dumps(gallery, ensure_ascii=False); p.videos = json.dumps(videos, ensure_ascii=False); p.personnel = json.dumps(personnel, ensure_ascii=False)
                    db.session.commit()  # type: ignore
            except Exception:
                current_app.logger.exception("DB metadata upsert failed")

            # delete old page if slug changed
            if page_slug and page_slug != slug:
                old_path = _page_file_path(page_slug)
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception:
                    pass
                try:
                    if Page is not None:
                        old_p = Page.query.filter_by(slug=page_slug).first()  # type: ignore
                        if old_p:
                            db.session.delete(old_p)  # type: ignore
                            db.session.commit()  # type: ignore
                except Exception:
                    pass

            flash('صفحه ذخیره شد', 'success')
            return redirect(url_for('wiki.view_page', page_name=slug))
        except Exception:
            current_app.logger.exception("Save failed")
            try:
                if db is not None:
                    db.session.rollback()
            except Exception:
                pass
            flash('خطا در ذخیره', 'danger')

    gallery_urls = [url_for('wiki.uploaded_file', filename=g) for g in gallery]
    video_urls = [url_for('wiki.stream_video', filename=v) for v in videos]
    feature_image_url = url_for('wiki.uploaded_file', filename=feature_image) if feature_image else None

    return render_template(
        'edit.html',
        is_new=is_new,
        page_slug=page_slug,
        page_title=title,
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
        excerpt=excerpt_field
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


@wiki_bp.route('/api/comments/<page_name>', endpoint='api_comments')
def api_comments(page_name: str):
    if Comment is None:
        return jsonify({'success': True, 'comments': []})
    try:
        comments = Comment.query.filter_by(page=page_name).order_by(Comment.created_at.asc()).all()  # type: ignore
        def to_dict(c):
            return {
                'id': c.id,
                'page': c.page,
                'user': {'id': c.user.id, 'username': c.user.username, 'avatar': c.user.avatar},
                'parent_id': c.parent_id,
                'content': c.content,
                'created_at': c.created_at.isoformat(),
                'edited_at': c.edited_at.isoformat() if c.edited_at else None,
                'deleted': c.deleted,
                'children': [to_dict(ch) for ch in c.children]
            }
        out = [to_dict(c) for c in comments if c.parent_id is None]
        return jsonify({'success': True, 'comments': out})
    except Exception:
        current_app.logger.exception("api_comments failed")
        return jsonify({'success': False, 'comments': []}), 500


@wiki_bp.route('/page/<path:page_name>/comment', methods=['POST'], endpoint='add_comment')
@login_required
def add_comment(page_name: str):
    try:
        content = (request.form.get('content') or '').strip()
        parent_id = request.form.get('parent_id') or None
        if not content:
            return jsonify({'success': False, 'error': 'empty'}), 400
        max_len = current_app.config.get('MAX_COMMENT_LENGTH', 4000)
        if len(content) > max_len:
            return jsonify({'success': False, 'error': 'too_long'}), 400
        page_file = _page_file_path(page_name)
        if not os.path.exists(page_file):
            return jsonify({'success': False, 'error': 'page_not_found'}), 404
        if Comment is None:
            return jsonify({'success': False, 'error': 'comments not enabled'}), 500
        comment = Comment(page=page_name, user_id=current_user.id, content=content)  # type: ignore
        if parent_id:
            try:
                pid = int(parent_id)
                parent = db.session.get(Comment, pid)  # type: ignore
                if parent and parent.page == page_name:
                    comment.parent_id = pid
            except Exception:
                current_app.logger.exception("bad parent_id")
        db.session.add(comment)  # type: ignore
        db.session.commit()  # type: ignore
        _ = comment.user
        html = build_comment_html(comment)
        avatar_url = url_for('wiki.uploaded_file', filename=current_user.avatar) + f'?v={int(getattr(current_user, "created_at", datetime.utcnow()).timestamp() if getattr(current_user, "created_at", None) else (uuid.uuid4().int & 0xffffffff))}'
        return jsonify({'success': True, 'comment': {'id': comment.id, 'parent_id': comment.parent_id, 'html': html, 'avatar_url': avatar_url}}), 201
    except Exception:
        current_app.logger.exception("add_comment failed")
        try:
            if db is not None:
                db.session.rollback()
        except Exception:
            pass
        return jsonify({'success': False, 'error': 'internal'}), 500


@wiki_bp.route('/comment/<int:c_id>/edit', methods=['POST'], endpoint='edit_comment')
@login_required
def edit_comment(c_id: int):
    if Comment is None:
        return jsonify({'success': False, 'error': 'not enabled'}), 500
    try:
        comment = db.session.get(Comment, c_id)  # type: ignore
        if not comment:
            return jsonify({'success': False, 'error': 'not found'}), 404
        if comment.user_id != current_user.id and getattr(current_user, 'role', None) != 'admin':
            return jsonify({'success': False, 'error': 'forbidden'}), 403
        content = request.form.get('content','').strip()
        if not content:
            return jsonify({'success': False, 'error': 'empty'}), 400
        max_len = current_app.config.get('MAX_COMMENT_LENGTH', 4000)
        if len(content) > max_len:
            return jsonify({'success': False, 'error': 'too_long'}), 400
        comment.content = content
        comment.edited_at = datetime.utcnow()
        db.session.commit()  # type: ignore
        return jsonify({'success': True, 'id': comment.id, 'edited_at': comment.edited_at.isoformat()})
    except Exception:
        current_app.logger.exception("edit_comment failed")
        return jsonify({'success': False, 'error': 'internal'}), 500


@wiki_bp.route('/comment/<int:c_id>/delete', methods=['POST'], endpoint='delete_comment')
@login_required
def delete_comment(c_id: int):
    if Comment is None:
        return jsonify({'success': False, 'error': 'not enabled'}), 500
    try:
        comment = db.session.get(Comment, c_id)  # type: ignore
        if not comment:
            return jsonify({'success': False, 'error': 'not found'}), 404
        if comment.user_id != current_user.id and getattr(current_user, 'role', None) != 'admin':
            return jsonify({'success': False, 'error': 'forbidden'}), 403
        comment.deleted = True
        comment.deleted_at = datetime.utcnow()
        comment.content = '[حذف‌شده]'
        db.session.commit()  # type: ignore
        return jsonify({'success': True, 'id': comment.id})
    except Exception:
        current_app.logger.exception("delete_comment failed")
        return jsonify({'success': False, 'error': 'internal'}), 500


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
