// static/js/page.js
document.addEventListener('DOMContentLoaded', function () {
  // Comment submit via AJAX (no refresh)
  const commentForm = document.getElementById('comment-form');
  if (commentForm) {
    commentForm.addEventListener('submit', function (e) {
      e.preventDefault();
      const btn = document.getElementById('comment-submit');
      btn.disabled = true;
      const content = document.getElementById('comment-content').value.trim();
      const parent_id = document.getElementById('comment-parent-id').value || '';
      if (!content) {
        alert('متن کامنت خالی است');
        btn.disabled = false;
        return;
      }
      const formData = new FormData();
      formData.append('content', content);
      if (parent_id) formData.append('parent_id', parent_id);
      const pagePath = window.location.pathname.replace('/page/', '');
      fetch(`/page/${encodeURIComponent(pagePath)}/comment`, {
        method: 'POST',
        headers: {'X-Requested-With': 'XMLHttpRequest'},
        body: formData
      }).then(r => r.json()).then(j => {
        btn.disabled = false;
        if (j.success && j.comment && j.comment.html) {
          if (j.comment.parent_id) {
            // insert under parent replies
            const parentEl = document.getElementById('comment-' + j.comment.parent_id);
            if (parentEl) {
              let replies = parentEl.querySelector('.replies');
              if (!replies) {
                replies = document.createElement('div');
                replies.className = 'replies ms-4 mt-3';
                parentEl.appendChild(replies);
              }
              replies.insertAdjacentHTML('beforeend', j.comment.html);
            } else {
              document.getElementById('comments-list').insertAdjacentHTML('beforeend', j.comment.html);
            }
          } else {
            document.getElementById('comments-list').insertAdjacentHTML('beforeend', j.comment.html);
          }
          // clear form
          document.getElementById('comment-content').value = '';
          document.getElementById('comment-parent-id').value = '';
          const cancelBtn = document.getElementById('comment-cancel-reply');
          if (cancelBtn) cancelBtn.style.display = 'none';
        } else {
          alert('ارسال ناموفق');
        }
      }).catch(err => {
        btn.disabled = false;
        console.error(err);
        alert('خطا در ارسال');
      });
    });

    // reply handling: delegate
    document.body.addEventListener('click', function (e) {
      if (e.target.matches('.js-reply')) {
        e.preventDefault();
        const id = e.target.getAttribute('data-id');
        document.getElementById('comment-parent-id').value = id;
        document.getElementById('comment-content').focus();
        const cancelBtn = document.getElementById('comment-cancel-reply');
        if (cancelBtn) {
          cancelBtn.style.display = 'inline-block';
          cancelBtn.onclick = function () {
            document.getElementById('comment-parent-id').value = '';
            cancelBtn.style.display = 'none';
          };
        }
      }
      // delete comment
      if (e.target.matches('.js-delete-comment')) {
        e.preventDefault();
        if (!confirm('آیا مایل به حذف این نظر هستید؟')) return;
        const id = e.target.getAttribute('data-id');
        fetch(`/comment/${id}/delete`, {method: 'POST', headers: {'X-Requested-With':'XMLHttpRequest'}})
          .then(r => r.json()).then(j => {
            if (j.success) {
              const el = document.getElementById('comment-' + id);
              if (el) el.remove();
            } else {
              alert('خطا: ' + (j.error || ''));
            }
          }).catch(err => { console.error(err); alert('خطا'); });
      }
      // edit comment: prompt then post
      if (e.target.matches('.js-edit-comment')) {
        e.preventDefault();
        const id = e.target.getAttribute('data-id');
        const el = document.getElementById('comment-' + id);
        if (!el) return;
        const old = el.querySelector('.comment-body') ? el.querySelector('.comment-body').innerText : '';
        const newText = prompt('ویرایش نظر:', old);
        if (newText === null) return;
        fetch(`/comment/${id}/edit`, {
          method: 'POST',
          headers: {'Content-Type':'application/x-www-form-urlencoded', 'X-Requested-With':'XMLHttpRequest'},
          body: `content=${encodeURIComponent(newText)}`
        }).then(r => r.json()).then(j => {
          if (j.success) {
            if (el.querySelector('.comment-body')) el.querySelector('.comment-body').innerText = newText;
          } else {
            alert('خطا: ' + (j.error || ''));
          }
        }).catch(err => { console.error(err); alert('خطا'); });
      }
    });
  }
});
