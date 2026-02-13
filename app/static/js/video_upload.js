// video_upload.js — chunked upload (8MB chunks) + UI for edit.html
(function(){
  const CHUNK_SIZE = 8 * 1024 * 1024; // 8MB, should match server DEFAULT_CHUNK_SIZE
  const selectBtn = document.getElementById('selectVideoBtn');
  const fileInput = document.getElementById('videoFileInput');
  const dropArea = document.getElementById('videoDropArea');
  const uploadList = document.getElementById('uploadList');
  const openMediaBtn = document.getElementById('openMediaBtn');
  const mediaModalEl = document.getElementById('mediaModal');
  const mediaGrid = document.getElementById('mediaGrid');
  const mediaModal = new bootstrap.Modal(mediaModalEl);

  selectBtn.addEventListener('click', ()=> fileInput.click());
  fileInput.addEventListener('change', (e)=> {
    if(e.target.files && e.target.files[0]) startUpload(e.target.files[0]);
  });

  // drag & drop
  ;['dragenter','dragover'].forEach(evt=>{
    dropArea.addEventListener(evt, (e)=>{
      e.preventDefault(); e.stopPropagation();
      dropArea.classList.add('drag-over');
    });
  });
  ;['dragleave','drop'].forEach(evt=>{
    dropArea.addEventListener(evt, (e)=>{
      e.preventDefault(); e.stopPropagation();
      dropArea.classList.remove('drag-over');
    });
  });
  dropArea.addEventListener('drop', (e)=>{
    if(e.dataTransfer.files && e.dataTransfer.files[0]) startUpload(e.dataTransfer.files[0]);
  });

  // open media library
  openMediaBtn.addEventListener('click', ()=>{
    loadMediaLibrary();
    mediaModal.show();
  });

  function el(tag, cls=''){ const node=document.createElement(tag); if(cls) node.className=cls; return node; }

  function startUpload(file){
    // validate video extension
    const ext = (file.name.split('.').pop()||'').toLowerCase();
    if(!['mp4','webm','mov','mkv','avi'].includes(ext)){
      alert('فرمت ویدیو مجاز نیست');
      return;
    }
    if(file.size > 2 * 1024 * 1024 * 1024){
      alert('حجم ویدیو نباید بیشتر از 2GB باشد');
      return;
    }

    const item = el('div','upload-item card p-2');
    const title = el('div','fw-bold'); title.textContent = file.name;
    const progressWrap = el('div','progress mt-2');
    const progressBar = el('div','progress-bar'); progressBar.style.width='0%';
    progressWrap.appendChild(progressBar);
    const actions = el('div','mt-2 d-flex gap-2');
    const insertBtn = el('button','btn btn-sm btn-primary'); insertBtn.textContent='درج در محتوا'; insertBtn.disabled=true;
    const cancelBtn = el('button','btn btn-sm btn-outline-danger'); cancelBtn.textContent='لغو';
    actions.appendChild(insertBtn); actions.appendChild(cancelBtn);

    item.appendChild(title);
    item.appendChild(progressWrap);
    item.appendChild(actions);
    uploadList.prepend(item);

    // start session
    fetch('/video/upload/start', {
      method:'POST',
      headers:{ 'Content-Type':'application/json' },
      body: JSON.stringify({ filename: file.name, total_size: file.size })
    }).then(r=>r.json()).then(async data=>{
      if(data.error){ alert(data.error); return; }
      const upload_id = data.upload_id;
      const chunk_size = data.chunk_size || CHUNK_SIZE;
      // upload sequentially
      const totalChunks = Math.ceil(file.size / chunk_size);
      let uploaded = 0;
      // upload chunks
      for(let idx=0; idx<totalChunks; idx++){
        const start = idx * chunk_size;
        const end = Math.min(start + chunk_size, file.size);
        const blob = file.slice(start, end);
        const form = new FormData();
        form.append('upload_id', upload_id);
        form.append('index', idx);
        form.append('chunk', blob, `chunk_${idx}`);
        try {
          const resp = await fetch('/video/upload/chunk', { method:'POST', body: form });
          const resjson = await resp.json();
          if(resjson.error){ throw new Error(resjson.error); }
        } catch(err){
          alert('خطا در آپلود تکه: ' + err.message);
          return;
        }
        uploaded += (end - start);
        const perc = Math.round((uploaded / file.size) * 100);
        progressBar.style.width = perc + '%';
      }

      // complete
      const comp = await fetch('/video/upload/complete', {
        method:'POST',
        headers:{ 'Content-Type':'application/json' },
        body: JSON.stringify({ upload_id: upload_id })
      }).then(r=>r.json());

      if(comp && comp.success){
        insertBtn.disabled = false;
        insertBtn.onclick = ()=>{
          // insert video tag into CKEditor (global editorInstance)
          const url = comp.url;
          if(window.editorInstance){
            const html = `<video controls width="100%"><source src="${url}"></video>`;
            window.editorInstance.model.change(writer=>{
              const viewFragment = window.editorInstance.data.processor.toView(html);
              const modelFragment = window.editorInstance.data.toModel(viewFragment);
              window.editorInstance.model.insertContent(modelFragment, window.editorInstance.model.document.selection);
            });
          } else {
            // fallback: append to textarea content
            const ta = document.querySelector('#editor');
            if(ta) ta.value = ta.value + `\n\n<video controls width="100%"><source src="${url}"></video>\n\n`;
          }
        };
        title.textContent += ' — آپلود شد';
      } else {
        alert('خطا در نهایی‌سازی آپلود: ' + (comp && comp.error ? comp.error : 'unknown'));
      }
    }).catch(err=>{
      alert('خطا در شروع آپلود: ' + err.message);
    });

    cancelBtn.addEventListener('click', ()=>{
      item.remove();
      // note: server-side cleanup not implemented for cancelled sessions
    });
  }

  // load media library
  function loadMediaLibrary(){
    mediaGrid.innerHTML = '<div class="text-center p-3">در حال بارگذاری...</div>';
    fetch('/media/list').then(r=>r.json()).then(data=>{
      mediaGrid.innerHTML = '';
      if(!data.success || !data.items.length){
        mediaGrid.innerHTML = '<div class="text-muted p-3">هیچ ویدیویی موجود نیست.</div>';
        return;
      }
      data.items.forEach(it=>{
        const col = el('div','col-md-4');
        const card = el('div','card p-2 h-100');
        const vwrap = el('div','ratio ratio-16x9');
        const video = el('video'); video.controls = true;
        const src = el('source'); src.src = it.url; video.appendChild(src);
        vwrap.appendChild(video);
        const meta = el('div','mt-2 d-flex justify-content-between align-items-center');
        const name = el('div','small text-truncate'); name.textContent = it.filename;
        const actions = el('div');
        const insert = el('button','btn btn-sm btn-primary me-2'); insert.textContent='درج';
        const del = el('button','btn btn-sm btn-outline-danger'); del.textContent='حذف';
        actions.appendChild(insert); actions.appendChild(del);
        meta.appendChild(name); meta.appendChild(actions);
        card.appendChild(vwrap); card.appendChild(meta);
        col.appendChild(card);
        mediaGrid.appendChild(col);

        insert.addEventListener('click', ()=>{
          const url = it.url;
          if(window.editorInstance){
            const html = `<video controls width="100%"><source src="${url}"></video>`;
            window.editorInstance.model.change(writer=>{
              const viewFragment = window.editorInstance.data.processor.toView(html);
              const modelFragment = window.editorInstance.data.toModel(viewFragment);
              window.editorInstance.model.insertContent(modelFragment, window.editorInstance.model.document.selection);
            });
          }
          mediaModal.hide();
        });

        del.addEventListener('click', async ()=>{
          if(!confirm('آیا می‌خواهید این ویدیو حذف شود؟ (فقط ادمین می‌تواند)')) return;
          const resp = await fetch('/media/delete', {
            method:'POST',
            headers:{ 'Content-Type':'application/json' },
            body: JSON.stringify({ filename: it.filename })
          }).then(r=>r.json());
          if(resp.success){ loadMediaLibrary(); } else { alert('حذف موفق نبود: ' + (resp.error||'')); }
        });
      });
    }).catch(err=>{
      mediaGrid.innerHTML = '<div class="text-danger p-3">خطا در بارگذاری</div>';
    });
  }

})();
