
// static/js/comments.js
// Requires jQuery (or adapt to fetch). Minimal code to:
// - submit new comment via AJAX
// - insert returned comment HTML into DOM
// - submit edit/delete via AJAX and update DOM
(function(){
  function ajaxPost(url, data, cb, failCb){
    var xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
    // For form-encoded
    if (data instanceof FormData) {
      // let browser set content-type
    } else {
      xhr.setRequestHeader('Content-Type', 'application/json;charset=UTF-8');
      data = JSON.stringify(data);
    }
    xhr.onload = function(){
      var ok = xhr.status >=200 && xhr.status < 300;
      try {
        var res = JSON.parse(xhr.responseText || '{}');
      } catch(e){ var res = null; }
      if (ok) cb && cb(res, xhr);
      else failCb && failCb(res, xhr);
    };
    xhr.onerror = function(){ failCb && failCb(null, xhr); };
    xhr.send(data);
  }

  function insertCommentHtml(pageName, commentHtml, parentId){
    // if parentId provided, append inside reply container, otherwise prepend to root list
    var container = document.querySelector('#comments-root');
    if (!container) {
      // fallback: find by id "comments"
      container = document.querySelector('#comments');
    }
    if (!container) return;
    var temp = document.createElement('div');
    temp.innerHTML = commentHtml;
    var node = temp.firstElementChild;
    if (parentId) {
      var parent = document.querySelector('#comment-' + parentId);
      if (parent) {
        var replies = parent.querySelector('.replies');
        if (!replies) {
          replies = document.createElement('div'); replies.className = 'replies ml-4';
          parent.appendChild(replies);
        }
        replies.appendChild(node);
        return;
      }
    }
    // root insert at top
    container.insertBefore(node, container.firstChild);
  }

  // handle new comment forms
  document.addEventListener('submit', function(e){
    var f = e.target;
    if (f && f.matches && f.matches('.js-comment-form')) {
      e.preventDefault();
      var page = f.dataset.page;
      var action = f.action;
      var formData = new FormData(f);
      ajaxPost(action, formData, function(res){
        if (res && res.success && res.comment && res.comment.html) {
          insertCommentHtml(page, res.comment.html, res.comment.parent_id);
          // clear textarea
          var ta = f.querySelector('textarea[name="content"]');
          if (ta) ta.value = '';
        } else {
          alert('خطا در ثبت کامنت');
        }
      }, function(){
        alert('خطا در ارسال کامنت');
      });
    }
  }, false);

  // handle edit / delete buttons via delegation
    document.addEventListener('click', function(e){
        var btn = e.target;

        // ====================== DELETE COMMENT ======================
        if (btn && btn.matches && btn.matches('.js-comment-delete')) {
            e.preventDefault();
            if (!confirm('آیا از حذف این کامنت مطمئن هستید؟')) return;

            var commentId = btn.dataset.commentId || btn.dataset.id;   // هر دو حالت رو قبول کن
            var pageSlug   = window.currentPageSlug || btn.dataset.pageSlug || '';

            if (!commentId || commentId === 'undefined' || !pageSlug) {
                alert('خطا: شناسه کامنت یا صفحه پیدا نشد! (undefined)');
                console.error('commentId:', commentId, 'pageSlug:', pageSlug);
                return;
            }

            var url = `/page/${pageSlug}/comment/${commentId}/delete/`;

            ajaxPost(url, {}, function(res){
                if (res && res.success) {
                    var el = document.querySelector('#comment-' + commentId);
                    if (el) el.remove();           // کامل حذف از صفحه
                    else location.reload();        // fallback
                } else {
                    alert('حذف موفق نبود');
                }
            }, function(){
                alert('خطا در ارتباط با سرور (احتمالاً CSRF)');
            });
        }

        // ====================== EDIT COMMENT (بدون تغییر نگه دار یا بعداً فیکس کن) ======================
        if (btn && btn.matches && btn.matches('.js-comment-edit')) {
            // ... کد ویرایش قبلی‌ت رو اینجا بذار (تغییر خاصی لازم نداره)
        }
    }, false);

})();
