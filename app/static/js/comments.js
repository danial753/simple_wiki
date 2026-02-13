
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
    // delete
    if (btn && btn.matches && btn.matches('.js-comment-delete')) {
      e.preventDefault();
      if (!confirm('آیا از حذف مطمئن هستید؟')) return;
      var id = btn.dataset.id;
      ajaxPost('/comment/' + id + '/delete', {}, function(res){
        if (res && res.success) {
          var el = document.querySelector('#comment-' + res.id);
          if (el) {
            // mark deleted
            var body = el.querySelector('.comment-body');
            if (body) body.innerText = '[حذف‌شده]';
            el.classList.add('comment-deleted');
          }
        } else {
          alert('حذف موفق نبود');
        }
      }, function(){ alert('خطا در حذف'); });
    }

    // edit: toggle edit form or submit edit via AJAX
    if (btn && btn.matches && btn.matches('.js-comment-edit')) {
      e.preventDefault();
      var id = btn.dataset.id;
      var el = document.querySelector('#comment-' + id);
      if (!el) return;
      // if there's already an edit form, do nothing
      if (el.querySelector('.comment-edit-form')) return;
      var body = el.querySelector('.comment-body');
      var current = body ? body.innerText : '';
      var form = document.createElement('form');
      form.className = 'comment-edit-form';
      form.innerHTML = '<textarea name="content" rows="3" class="form-control">' + current + '</textarea>' +
                       '<div class="mt-2"><button class="btn btn-sm btn-primary js-submit-edit">ذخیره</button> ' +
                       '<button class="btn btn-sm btn-secondary js-cancel-edit" type="button">لغو</button></div>';
      el.appendChild(form);
      // handle submit
      form.addEventListener('click', function(ev){
        if (ev.target && ev.target.matches('.js-submit-edit')) {
          ev.preventDefault();
          var content = form.querySelector('textarea[name="content"]').value;
          var fd = new FormData();
          fd.append('content', content);
          ajaxPost('/comment/' + id + '/edit', fd, function(res){
            if (res && res.success) {
              var body = el.querySelector('.comment-body');
              if (body) body.innerText = content;
              var editForm = el.querySelector('.comment-edit-form');
              if (editForm) editForm.remove();
            } else {
              alert(res && res.error ? res.error : 'خطا در ویرایش');
            }
          }, function(){ alert('خطا در ویرایش'); });
        } else if (ev.target && ev.target.matches('.js-cancel-edit')) {
          ev.preventDefault();
          form.remove();
        }
      });
    }
  }, false);

})();
