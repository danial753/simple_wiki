# FILE: app/services/page_service.py
import os
import re
import json
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any

from PIL import Image, ImageOps
from werkzeug.utils import secure_filename
from flask import current_app, url_for

from ..extensions import db
from ..models import Page

# ---------------- Helpers / Constants ----------------

def _get_config(key: str, default=None):
    """Read config from current_app (safe when app context exists)."""
    try:
        return current_app.config.get(key, default)
    except RuntimeError:
        # not in app context — fall back to provided default
        return default

def _resample_filter():
    """Return a PIL resampling filter that works across Pillow versions."""
    try:
        return Image.Resampling.LANCZOS
    except AttributeError:
        return Image.LANCZOS

def allowed_file(filename: str) -> bool:
    exts = _get_config('ALLOWED_EXTENSIONS', {'png','jpg','jpeg','gif','webp','pdf','mp4','webm','mov','mkv','avi','svg','doc','docx'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in exts

def allowed_video(filename: str) -> bool:
    exts = _get_config('ALLOWED_VIDEO_EXT', {'mp4','webm','mov','mkv','avi'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in exts

def unique_filename(filename: str) -> str:
    safe = secure_filename(filename)
    if '.' in safe:
        ext = safe.rsplit('.', 1)[1].lower()
        return f"{uuid.uuid4().hex}.{ext}"
    return uuid.uuid4().hex

# ---------------- Paths ----------------

def _paths() -> Dict[str, Path]:
    """
    Compute and ensure on-disk directories used by the service.
    Returns dict with keys: BASE_DIR, PAGES_DIR, UPLOADS_DIR, MEDIA_ROOT, VIDEO_FOLDER, TMP_UPLOADS
    """
    base_dir = Path(_get_config('BASE_DIR', Path.cwd()))
    pages_dir = Path(_get_config('PAGES_DIR', str(base_dir / 'pages')))
    uploads_dir = Path(_get_config('UPLOAD_FOLDER', str(base_dir / 'static' / 'uploads')))
    media_root = Path(_get_config('MEDIA_ROOT', str(base_dir / 'media')))
    video_folder = media_root / 'videos'
    tmp_uploads = media_root / 'tmp_uploads'

    # Ensure directories exist
    for p in (pages_dir, uploads_dir, media_root, video_folder, tmp_uploads):
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            try:
                current_app.logger.exception("Failed to create path: %s", p)
            except Exception:
                pass

    return {
        'BASE_DIR': base_dir,
        'PAGES_DIR': pages_dir,
        'UPLOADS_DIR': uploads_dir,
        'MEDIA_ROOT': media_root,
        'VIDEO_FOLDER': video_folder,
        'TMP_UPLOADS': tmp_uploads
    }

# ---------------- Page file helpers ----------------

def _page_file_path(slug: str) -> str:
    paths = _paths()
    return str(paths['PAGES_DIR'] / f"{slug}.html")

def list_pages() -> List[str]:
    paths = _paths()
    try:
        return sorted([f[:-5] for f in os.listdir(paths['PAGES_DIR']) if f.endswith('.html')])
    except Exception:
        try:
            current_app.logger.exception("list_pages failed")
        except Exception:
            pass
        return []

def extract_tags_from_page(path: str) -> List[str]:
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            txt = fh.read()
        m = re.search(r'<!--TAGS:(.*?)-->', txt, re.S)
        if m:
            return [t.strip() for t in m.group(1).split(',') if t.strip()]
    except Exception:
        try:
            current_app.logger.exception("extract_tags_from_page failed for %s", path)
        except Exception:
            pass
    return []

def save_page_file_atomic(slug: str, meta: str, body: str) -> None:
    """
    Write page file atomically (write to tmp then replace).
    """
    file_path = _page_file_path(slug)
    tmp = file_path + '.tmp'
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(meta + body)
    os.replace(tmp, file_path)

# ---------------- Image processing ----------------

def process_image_and_save(file_storage, filename_hint: str) -> Dict[str, Optional[str]]:
    """
    Save uploaded image, create thumbnail and webp if configured.
    Returns dict with keys: filename, url, thumbnail, webp
    """
    cfg = {
        'IMAGE_MAX_DIM': int(_get_config('IMAGE_MAX_DIM', 2400)),
        'THUMBNAIL_SIZE': tuple(_get_config('THUMBNAIL_SIZE', (400, 400))),
        'CREATE_WEBP': _get_config('CREATE_WEBP', True)
    }
    paths = _paths()
    base_name = unique_filename(filename_hint)
    path = paths['UPLOADS_DIR'] / base_name

    try:
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream).convert('RGB')

        resample = _resample_filter()
        if max(img.size) > cfg['IMAGE_MAX_DIM']:
            img.thumbnail((cfg['IMAGE_MAX_DIM'], cfg['IMAGE_MAX_DIM']), resample=resample)

        ext = base_name.rsplit('.', 1)[1].lower()
        # Save original (JPEG for compatibility, PNG otherwise)
        try:
            if ext in ('jpg', 'jpeg'):
                img.save(path, 'JPEG', quality=90, optimize=True)
            else:
                img.save(path, 'PNG', optimize=True)
        except Exception:
            img.save(path, 'JPEG', quality=90, optimize=True)

        out: Dict[str, Optional[str]] = {'filename': base_name, 'url': f"/uploads/{base_name}"}

        # Thumbnail
        try:
            thumb = ImageOps.fit(img, cfg['THUMBNAIL_SIZE'], method=resample)
            thumb_name = f"thumb_{base_name.rsplit('.',1)[0]}.webp"
            thumb_path = paths['UPLOADS_DIR'] / thumb_name
            thumb.save(thumb_path, 'WEBP', quality=85, method=6)
            out['thumbnail'] = f"/uploads/{thumb_name}"
        except Exception:
            out['thumbnail'] = None

        # WebP copy
        if cfg['CREATE_WEBP']:
            try:
                webp_name = f"{base_name.rsplit('.',1)[0]}.webp"
                webp_path = paths['UPLOADS_DIR'] / webp_name
                img.save(webp_path, 'WEBP', quality=90, method=6)
                out['webp'] = f"/uploads/{webp_name}"
            except Exception:
                out['webp'] = None

        return out
    except Exception:
        try:
            current_app.logger.exception("process_image_and_save failed")
        except Exception:
            pass
        raise

# ---------------- Metadata (DB) ----------------

def PageService_upsert(slug: str,
                       title: Optional[str],
                       subtitle: Optional[str],
                       excerpt: Optional[str],
                       tags: Optional[str],
                       feature_image: Optional[str],
                       gallery: Optional[List]=None,
                       videos: Optional[List]=None,
                       personnel: Optional[List]=None) -> Page:
    """
    Insert or update Page metadata in DB.
    """
    gallery_json = json.dumps(gallery or [], ensure_ascii=False) if gallery is not None else None
    videos_json = json.dumps(videos or [], ensure_ascii=False) if videos is not None else None
    personnel_json = json.dumps(personnel or [], ensure_ascii=False) if personnel is not None else None

    try:
        p = Page.query.filter_by(slug=slug).first()
        if not p:
            p = Page(
                slug=slug,
                title=title,
                subtitle=subtitle,
                excerpt=excerpt,
                tags=tags,
                feature_image=feature_image,
                gallery=gallery_json,
                videos=videos_json,
                personnel=personnel_json
            )
            db.session.add(p)
        else:
            if title is not None:
                p.title = title
            if subtitle is not None:
                p.subtitle = subtitle
            if excerpt is not None:
                p.excerpt = excerpt
            if tags is not None:
                p.tags = tags
            if feature_image is not None:
                p.feature_image = feature_image
            if gallery is not None:
                p.gallery = gallery_json
            if videos is not None:
                p.videos = videos_json
            if personnel is not None:
                p.personnel = personnel_json

        db.session.commit()
        return p
    except Exception:
        try:
            current_app.logger.exception("PageService_upsert ORM commit failed — rolling back")
        except Exception:
            pass
        db.session.rollback()
        raise

def ensure_page_metadata(slug: str,
                         title: Optional[str],
                         subtitle: Optional[str],
                         excerpt: Optional[str],
                         tags: Optional[str],
                         feature_image: Optional[str],
                         gallery: Optional[List]=None,
                         videos: Optional[List]=None,
                         personnel: Optional[List]=None) -> Page:
    """
    Wrapper for upsert; kept as public API name compatible with previous code.
    """
    return PageService_upsert(slug, title, subtitle, excerpt, tags, feature_image, gallery, videos, personnel)

# ---------------- Utility for parsing meta from file content ----------------

def parse_page_meta_and_body(file_path: str) -> Dict[str, Any]:
    """
    Read file, split leading <!--...--> metadata block (if present) from body,
    and return a dict: {'meta_block': str or '', 'body': str, 'meta_fields': {...}}
    meta_fields includes TAGS, SUBTITLE, EXCERPT, GALLERY, VIDEOS, PERSONNEL if present.
    """
    out = {'meta_block': '', 'body': '', 'meta_fields': {}}
    try:
        with open(file_path, 'r', encoding='utf-8') as fh:
            txt = fh.read()
        m = re.match(r'^(<!--.*?-->)\s*(.*)$', txt, re.S)
        if m:
            meta_block = m.group(1)
            body = m.group(2).strip()
            out['meta_block'] = meta_block
            out['body'] = body
        else:
            out['body'] = txt

        # extract fields
        fields = {}
        for name in ('TAGS', 'SUBTITLE', 'EXCERPT', 'GALLERY', 'VIDEOS', 'PERSONNEL'):
            mm = re.search(rf'<!--{name}:(.*?)-->', out.get('meta_block', ''), re.S)
            if mm:
                val = mm.group(1).strip()
                if name in ('GALLERY', 'VIDEOS', 'PERSONNEL'):
                    try:
                        fields[name.lower()] = json.loads(val)
                    except Exception:
                        fields[name.lower()] = []
                else:
                    fields[name.lower()] = val
        out['meta_fields'] = fields
    except Exception:
        try:
            current_app.logger.exception("parse_page_meta_and_body failed for %s", file_path)
        except Exception:
            pass
    return out
