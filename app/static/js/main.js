// static/js/main.js
document.addEventListener('DOMContentLoaded', function(){

  /* ---------- Avatar preview on profile ---------- */
  const avatarInput = document.querySelector('input[name="avatar"]');
  if (avatarInput) {
    avatarInput.addEventListener('change', function(e){
      const file = e.target.files[0];
      if (!file) return;
      const r = new FileReader();
      r.onload = function(){ const img = document.getElementById('avatar-preview'); if (img) img.src = r.result + '?v=' + Date.now(); };
      r.readAsDataURL(file);
    });
  }

  /* ---------- Comments AJAX (on page view) ---------- */
  const commentForm = document.getElementById('comment-form');
  if (commentForm) {
    commentForm.addEventListener('submit', async function(ev){
      ev.preventDefault();
      const txt = document.getElementById('comment-content');
      if (!txt) return;
      const content = txt.value.trim();
      if (!content) { alert('نظر خالی است'); return; }

      const page = (typeof PAGE_NAME !== 'undefined') ? PAGE_NAME : window.location.pathname.split('/').pop();
      const fd = new FormData();
      fd.append('content', content);

      try {
        const res = await fetch(`/page/${encodeURIComponent(page)}/comment`, {
          method: 'POST',
          body: fd,
          credentials: 'same-origin',
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        const data = await res.json();
        if (res.status === 201 && data.success) {
          // insert comment HTML (server returns comment data or we render a simple block)
          const list = document.getElementById('comments-list');
          if (list) {
            const html = `
              <div id="comment-${data.comment.id}" class="comment mb-2">
                <div class="d-flex">
                  <img src="${data.comment.user.avatar_url}" class="avatar-sm me-2">
                  <div>
                    <div class="meta"><strong>${data.comment.user.username}</strong> · الان</div>
                    <div class="mt-1 body">${escapeHtml(data.comment.content)}</div>
                  </div>
                </div>
              </div>
            `;
            list.insertAdjacentHTML('afterbegin', html);
          }
          txt.value = '';
        } else {
          alert(data.error || 'خطا در ارسال کامنت');
        }
      } catch (e) {
        console.error(e);
        alert('خطا در ارسال');
      }
    });
  }

  /* ---------- Comment delete/edit (delegated) ---------- */
  document.body.addEventListener('click', async (ev) => {
    const t = ev.target;
    if (t.matches('.js-comment-delete')) {
      ev.preventDefault();
      if (!confirm('آیا حذف شود؟')) return;
      const id = t.dataset.id;
      try {
        const res = await fetch(`/comment/${id}/delete`, { method:'POST', credentials:'same-origin' });
        const data = await res.json();
        if (data.success) {
          const el = document.getElementById('comment-' + id);
          if (el) el.remove();
        } else alert(data.error || 'خطا');
      } catch (e) { console.error(e); alert('خطا'); }
    }
    if (t.matches('.js-comment-edit')) {
      ev.preventDefault();
      const id = t.dataset.id;
      const el = document.getElementById('comment-' + id);
      if (!el) return;
      const current = el.querySelector('.body').innerText;
      const newText = prompt('ویرایش نظر:', current);
      if (newText === null) return;
      const fd = new FormData();
      fd.append('content', newText);
      try {
        const res = await fetch(`/comment/${id}/edit`, { method:'POST', body:fd, credentials:'same-origin' });
        const data = await res.json();
        if (data.success) {
          el.querySelector('.body').innerText = newText;
        } else alert(data.error || 'خطا');
      } catch (e) { console.error(e); alert('خطا'); }
    }
  });

  /* ---------- Discover tag-filter buttons (delegated) ---------- */
  document.body.addEventListener('click', function(ev){
    const t = ev.target;
    if (t.matches('.tag-filter-btn')) {
      const tag = t.dataset.tag;
      // navigate to discover with tag param
      const url = new URL(window.location.origin + '/discover');
      url.searchParams.set('tag', tag);
      window.location.href = url.toString();
    }
  });

  /* ---------- helper ---------- */
  function escapeHtml(s){ if(!s) return ''; return String(s).replace(/[&<>"']/g, function(m){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}[m]}); }

});
