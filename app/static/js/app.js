// static/js/app.js
document.addEventListener('DOMContentLoaded', () => {
  // Comment form submit (on page view)
  const commentForm = document.getElementById('comment-form');
  if (commentForm) {
    commentForm.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const textarea = document.getElementById('comment-content');
      const content = textarea.value.trim();
      if (!content) return alert('متن خالی است');
      const page = typeof PAGE_NAME !== 'undefined' ? PAGE_NAME : (window.location.pathname.split('/').pop());
      try {
        const form = new FormData();
        form.append('content', content);
        const res = await fetch(`/page/${encodeURIComponent(page)}/comment`, {
          method: 'POST',
          credentials: 'same-origin',
          body: form,
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        const data = await res.json();
        if (data.success) {
          // append HTML
          const list = document.getElementById('comments-list');
          if (list) {
            // if reply add under parent
            if (data.comment.parent_id) {
              const parent = document.getElementById('comment-' + data.comment.parent_id);
              let container = parent ? parent.querySelector('.replies') : null;
              if (!container && parent) {
                container = document.createElement('div');
                container.className = 'replies ms-4 mt-3';
                parent.appendChild(container);
              }
              if (container) container.insertAdjacentHTML('beforeend', data.comment.html);
            } else {
              list.insertAdjacentHTML('afterbegin', data.comment.html);
            }
            // reset
            textarea.value = '';
            // update avatar src to bust cache
            const myAvatar = document.getElementById('my-avatar');
            if (myAvatar) {
              const src = myAvatar.src.split('?')[0] + '?v=' + Date.now();
              myAvatar.src = src;
            }
          }
        } else {
          alert('خطا: ' + (data.error || 'ناشناخته'));
        }
      } catch (e) {
        console.error(e);
        alert('خطا در ارسال کامنت');
      }
    });
  }

  // Delegate comment edit/delete/reply buttons (event delegation)
  document.body.addEventListener('click', async (ev) => {
    const target = ev.target;
    // reply
    if (target.matches('.js-reply')) {
      ev.preventDefault();
      const id = target.getAttribute('data-id');
      const parent = document.getElementById('comment-' + id);
      if (!parent) return;
      // show simple inline reply form
      if (parent.querySelector('.reply-form')) return; // already open
      const form = document.createElement('form');
      form.className = 'reply-form';
      form.innerHTML = `
        <textarea class="form-control mb-2" rows="2" name="content" placeholder="پاسخ شما..."></textarea>
        <div class="d-flex gap-2">
          <button class="btn btn-sm btn-primary" type="submit">ارسال</button>
          <button class="btn btn-sm btn-outline-light js-reply-cancel" type="button">لغو</button>
        </div>
      `;
      parent.appendChild(form);
      form.querySelector('.js-reply-cancel').addEventListener('click', () => form.remove());
      form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const content = form.querySelector('textarea').value.trim();
        if (!content) return alert('متن خالی است');
        const page = typeof PAGE_NAME !== 'undefined' ? PAGE_NAME : (window.location.pathname.split('/').pop());
        const fd = new FormData();
        fd.append('content', content);
        fd.append('parent_id', id);
        try {
          const res = await fetch(`/page/${encodeURIComponent(page)}/comment`, {
            method: 'POST',
            body: fd,
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
          });
          const data = await res.json();
          if (data.success) {
            // append reply
            const container = parent.querySelector('.replies') || (() => {
              const c = document.createElement('div'); c.className='replies ms-4 mt-3'; parent.appendChild(c); return c;
            })();
            container.insertAdjacentHTML('beforeend', data.comment.html);
            form.remove();
          } else alert('خطا: ' + (data.error || 'ناشناخته'));
        } catch (err) { console.error(err); alert('خطا در ارسال'); }
      });
    }

    // delete comment
    if (target.matches('.js-comment-delete')) {
      ev.preventDefault();
      if (!confirm('آیا از حذف مطمئن هستید؟')) return;
      const id = target.getAttribute('data-id');
      try {
        const res = await fetch(`/comment/${id}/delete`, { method:'POST', credentials:'same-origin' });
        const data = await res.json();
        if (data.success) {
          const el = document.getElementById('comment-' + id);
          if (el) el.querySelector('.comment-body') ? (el.querySelector('.comment-body').innerText = '[حذف‌شده]') : (el.remove());
        } else alert('خطا: ' + (data.error || 'ناشناخته'));
      } catch (e) { console.error(e); alert('خطا در حذف'); }
    }

    // edit comment (simple prompt-based)
    if (target.matches('.js-comment-edit')) {
      ev.preventDefault();
      const id = target.getAttribute('data-id');
      const el = document.getElementById('comment-' + id);
      if (!el) return;
      // find current text
      const body = el.querySelector('.comment-body') ? el.querySelector('.comment-body').innerText : el.innerText;
      const newText = prompt('ویرایش نظر:', body);
      if (newText === null) return;
      try {
        const fd = new FormData();
        fd.append('content', newText);
        const res = await fetch(`/comment/${id}/edit`, { method:'POST', body: fd, credentials:'same-origin' });
        const data = await res.json();
        if (data.success) {
          if (el.querySelector('.comment-body')) el.querySelector('.comment-body').innerText = newText;
        } else alert('خطا: ' + (data.error || 'ناشناخته'));
      } catch (e) { console.error(e); alert('خطا'); }
    }

    // page delete (admin) — live delete using API
    if (target.matches('#btn-delete-page')) {
      ev.preventDefault();
      if (!confirm('صفحه حذف شود؟')) return;
      const slug = typeof PAGE_NAME !== 'undefined' ? PAGE_NAME : (window.location.pathname.split('/').pop());
      try {
        const res = await fetch('/api/page/delete', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({slug}),
          credentials: 'same-origin'
        });
        const data = await res.json();
        if (data.success) {
          alert('حذف شد');
          window.location.href = '/';
        } else alert('خطا: ' + (data.error || 'ناشناخته'));
      } catch (e) { console.error(e); alert('خطا'); }
    }
  });

  // Avatar preview on profile page
  const avatarInput = document.querySelector('input[name="avatar"]');
  if (avatarInput) {
    avatarInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = () => {
        const img = document.getElementById('avatar-preview');
        if (img) img.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  }

  // simple fallback: update any <img> with data-src lazy loading (if used)
  document.querySelectorAll('img[data-src]').forEach(img=>{
    img.src = img.dataset.src;
    img.removeAttribute('data-src');
  });
});
