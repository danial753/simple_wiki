// ============================================
// main.js – نسخه نهایی با پشتیبانی از CSRF اختیاری
// ============================================

window.mainJsActive = true;
let _bodyClickListenerAttached = false;

document.addEventListener('DOMContentLoaded', function () {
  'use strict';

  // ---------- 1. پیش‌نمایش آواتار ----------
  const avatarInput = document.querySelector('input[name="avatar"]');
  if (avatarInput) {
    avatarInput.addEventListener('change', function (e) {
      const file = e.target.files[0];
      if (!file) return;
      if (!file.type.startsWith('image/')) {
        alert('لطفاً یک فایل تصویری انتخاب کنید.');
        this.value = '';
        return;
      }
      const reader = new FileReader();
      reader.onload = function (ev) {
        const img = document.getElementById('avatar-preview');
        if (img) img.src = ev.target.result + '?v=' + Date.now();
      };
      reader.readAsDataURL(file);
    });
  }

  // ---------- 2. سیستم کامنت‌ها ----------
  const commentForm = document.getElementById('comment-form');
  const commentList = document.getElementById('comments-list');
  const parentIdInput = document.getElementById('comment-parent-id');
  const cancelReplyBtn = document.getElementById('comment-cancel');
  const submitBtn = document.getElementById('comment-submit');
  const contentInput = document.getElementById('comment-content');

  // pageName از meta یا URL (برای حذف)
  let pageName = null;
  const metaPage = document.querySelector('meta[name="page-name"]');
  if (metaPage) {
    pageName = metaPage.content;
  } else {
    const match = window.location.pathname.match(/\/page\/([^\/]+)/);
    if (match) pageName = match[1];
  }
  window.pageName = pageName;

  // توکن CSRF از meta (اختیاری)
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  if (!csrfToken) {
    console.warn('⚠️ توکن CSRF یافت نشد. درخواست‌ها بدون ارسال توکن انجام خواهند شد.');
  }

  // ---------- ارسال کامنت (با FormData) ----------
  if (commentForm && !commentForm._ajaxListenerAttached) {
    commentForm._ajaxListenerAttached = true;
    let isSubmitting = false;

    commentForm.addEventListener('submit', async function (ev) {
      ev.preventDefault();
      if (isSubmitting) return;

      const content = contentInput?.value.trim();
      if (!content) {
        alert('لطفاً متن نظر را وارد کنید.');
        return;
      }

      isSubmitting = true;
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span> در حال ارسال...';
      }

      const formData = new FormData();
      formData.append('content', content);
      if (parentIdInput?.value) formData.append('parent_id', parentIdInput.value);

      try {
        const headers = {
          'X-Requested-With': 'XMLHttpRequest',
        };
        if (csrfToken) headers['X-CSRFToken'] = csrfToken;

        const response = await fetch(commentForm.action, {
          method: 'POST',
          body: formData,
          headers: headers,
          credentials: 'same-origin'
        });

        let data = { success: false };
        try { data = await response.json(); } catch {}

        if (response.ok && data.success) {
          addCommentToList(data.comment);
          commentForm.reset();
          if (parentIdInput) parentIdInput.value = '';
          if (cancelReplyBtn) cancelReplyBtn.style.display = 'none';
          alert('نظر با موفقیت ثبت شد!');
        } else {
          alert(data.error || data.message || 'خطا در ارسال کامنت');
        }
      } catch (err) {
        console.error(err);
        alert('خطا در ارتباط با سرور');
      } finally {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.innerHTML = 'ارسال نظر';
        }
        isSubmitting = false;
      }
    });
  }

  // ---------- 3. افزودن کامنت به DOM ----------
  function addCommentToList(comment) {
    if (!commentList) return;
    const existing = document.getElementById(`comment-${comment.id}`);
    if (existing) existing.remove();

    const div = document.createElement('div');
    div.className = 'comment mb-4 p-3 border rounded bg-light';
    div.id = `comment-${comment.id}`;

    const user = comment.user || {};
    const avatarUrl = user.avatar_url || '/static/images/default_avatar.png';
    const username = escapeHtml(user.username || 'کاربر ناشناس');
    const contentEscaped = escapeHtml(comment.content || '').replace(/\n/g, '<br>');
    const createdAt = comment.created_at || 'الان';
    const canEdit = comment.can_edit || false;

    div.innerHTML = `
      <div class="d-flex align-items-start">
        <img src="${avatarUrl}" alt="${username}" class="rounded-circle me-3" width="48" height="48" style="object-fit:cover;">
        <div class="flex-grow-1">
          <div class="d-flex justify-content-between align-items-baseline mb-1">
            <strong class="text-dark">${username}</strong>
            <small class="text-muted">${createdAt}</small>
          </div>
          <div class="comment-body mb-2">${contentEscaped}</div>
          <div class="small">
            <a href="#" class="reply-link text-primary me-3" data-id="${comment.id}">پاسخ</a>
            ${canEdit ? `
              <a href="#" class="edit-comment-link text-warning me-3" data-id="${comment.id}">ویرایش</a>
              <a href="#" class="delete-comment-link text-danger" data-id="${comment.id}">حذف</a>
            ` : ''}
          </div>
        </div>
      </div>
    `;

    if (comment.parent_id) {
      const parent = document.getElementById(`comment-${comment.parent_id}`);
      if (parent) {
        let replies = parent.querySelector('.replies-container');
        if (!replies) {
          replies = document.createElement('div');
          replies.className = 'ms-5 mt-3 border-start ps-3 replies-container';
          parent.querySelector('.flex-grow-1').appendChild(replies);
        }
        replies.appendChild(div);
      }
    } else {
      commentList.prepend(div);
    }
  }

  // ---------- 4. Event Delegation (پاسخ، ویرایش، حذف، انصراف) ----------
  if (!_bodyClickListenerAttached) {
    _bodyClickListenerAttached = true;

    document.body.addEventListener('click', async function (e) {
      const target = e.target.closest('.reply-link, .edit-comment-link, .delete-comment-link, #comment-cancel');
      if (!target) return;
      e.preventDefault();

      // انصراف از پاسخ
      if (target.id === 'comment-cancel') {
        if (parentIdInput) parentIdInput.value = '';
        if (cancelReplyBtn) cancelReplyBtn.style.display = 'none';
        if (contentInput) contentInput.placeholder = 'نظر خود را اینجا بنویسید...';
        return;
      }

      const link = target;
      const commentId = link.dataset.id;

      // پاسخ
      if (link.classList.contains('reply-link')) {
        if (parentIdInput) parentIdInput.value = commentId;
        if (cancelReplyBtn) cancelReplyBtn.style.display = 'inline-block';
        if (contentInput) {
          contentInput.focus();
          contentInput.placeholder = 'پاسخ شما به این نظر...';
        }
        return;
      }

      // ویرایش (با آدرس /comment/[id]/edit و FormData)
      if (link.classList.contains('edit-comment-link')) {
        const commentDiv = document.getElementById(`comment-${commentId}`);
        if (!commentDiv) return;

        const bodyDiv = commentDiv.querySelector('.comment-body');
        if (bodyDiv.querySelector('textarea')) {
          bodyDiv.querySelector('textarea').focus();
          return;
        }

        const originalText = bodyDiv.innerHTML.replace(/<br\s*\/?>/gi, '\n');

        bodyDiv.innerHTML = `
          <textarea class="form-control mb-2" rows="4">${originalText}</textarea>
          <div class="mt-2">
            <button class="btn btn-sm btn-success me-2 save-edit">ذخیره</button>
            <button class="btn btn-sm btn-secondary cancel-edit">انصراف</button>
          </div>
        `;

        const textarea = bodyDiv.querySelector('textarea');
        const saveBtn = bodyDiv.querySelector('.save-edit');
        const cancelBtn = bodyDiv.querySelector('.cancel-edit');

        textarea.focus();

        saveBtn.onclick = async (ev) => {
          ev.preventDefault();
          const newContent = textarea.value.trim();
          if (!newContent) {
            alert('متن نمی‌تواند خالی باشد');
            return;
          }

          const formData = new FormData();
          formData.append('content', newContent);

          try {
            const headers = {
              'X-Requested-With': 'XMLHttpRequest',
            };
            if (csrfToken) headers['X-CSRFToken'] = csrfToken;

            const response = await fetch(`/comment/${commentId}/edit`, {
              method: 'POST',
              body: formData,
              headers: headers,
              credentials: 'same-origin'
            });

            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
              const text = await response.text();
              throw new Error(`پاسخ سرور JSON نیست (کد ${response.status})`);
            }

            const data = await response.json();

            if (response.ok && data.success) {
              bodyDiv.innerHTML = newContent.replace(/\n/g, '<br>');
              alert('ویرایش با موفقیت انجام شد');
            } else {
              alert(data.error || 'خطا در ویرایش');
              bodyDiv.innerHTML = originalText.replace(/\n/g, '<br>');
            }
          } catch (err) {
            console.error(err);
            alert('خطا: ' + err.message);
            bodyDiv.innerHTML = originalText.replace(/\n/g, '<br>');
          }
        };

        cancelBtn.onclick = (ev) => {
          ev.preventDefault();
          bodyDiv.innerHTML = originalText.replace(/\n/g, '<br>');
        };
        return;
      }

      // حذف (با آدرس /page/[pageName]/comment/[id]/delete)
      if (link.classList.contains('delete-comment-link')) {
        if (!confirm('آیا مطمئن هستید که می‌خواهید این نظر را حذف کنید؟')) return;

        // بررسی وجود pageName
        if (!window.pageName) {
          alert('خطا: نام صفحه یافت نشد.');
          return;
        }

        try {
          const headers = {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
          };
          if (csrfToken) headers['X-CSRFToken'] = csrfToken;

          const response = await fetch(`/page/${window.pageName}/comment/${commentId}/delete`, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({})
          });

          const contentType = response.headers.get('content-type');
          if (!contentType || !contentType.includes('application/json')) {
            const text = await response.text();
            throw new Error(`پاسخ سرور JSON نیست (کد ${response.status})`);
          }

          const data = await response.json();

          if (response.ok && data.success) {
            const commentDiv = document.getElementById(`comment-${commentId}`);
            if (commentDiv) commentDiv.remove();
            alert('نظر با موفقیت حذف شد');
          } else {
            alert('خطا: ' + (data.error || 'مشکلی پیش آمد'));
          }
        } catch (err) {
          console.error(err);
          alert('خطا در ارتباط با سرور: ' + err.message);
        }
      }
    });
  }

  // ---------- 5. فیلتر برچسب (discover) ----------
  if (!window._tagFilterListenerAttached) {
    window._tagFilterListenerAttached = true;
    document.body.addEventListener('click', function (ev) {
      const btn = ev.target.closest('.tag-filter-btn');
      if (btn) {
        ev.preventDefault();
        const tag = btn.dataset.tag;
        const url = new URL(window.location.origin + '/discover');
        url.searchParams.set('tag', tag);
        window.location.href = url.toString();
      }
    });
  }

  // ---------- 6. escape HTML ----------
  function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
});