// search.js — autocomplete + keyboard nav + mobile modal integration
document.addEventListener('DOMContentLoaded', function(){

  const input = document.getElementById('globalSearch');
  const suggestionsBox = document.getElementById('searchSuggestions');
  const searchBtn = document.getElementById('searchBtn');
  const mobileSearchBtn = document.getElementById('mobileSearchBtn');
  const mobileModal = new bootstrap.Modal(document.getElementById('mobileSearchModal'));
  const mobileInput = document.getElementById('mobileSearchInput');
  const mobileSug = document.getElementById('mobileSearchSuggestions');

  let currentFocus = -1;
  let suggestions = [];

  function renderSuggestions(list, targetBox){
    targetBox.innerHTML = '';
    if(!list || list.length === 0){
      targetBox.style.display = 'none';
      return;
    }
    list.forEach((it, idx)=>{
      const row = document.createElement('div');
      row.className = 'suggestion-row';
      row.tabIndex = 0;
      row.dataset.idx = idx;
      row.innerHTML = `<div>
                         <div class="suggestion-title">${it.title}</div>
                         <div class="suggestion-sub">${it.subtitle || ''}</div>
                       </div>
                       <div class="text-muted small">${it.type}</div>`;
      row.addEventListener('click', ()=> onPick(it));
      row.addEventListener('mouseover', ()=> setFocus(idx, targetBox));
      targetBox.appendChild(row);
    });
    targetBox.style.display = 'block';
  }

  function setFocus(i, box){
    // remove previous
    const rows = box.querySelectorAll('.suggestion-row');
    rows.forEach(r=> r.classList.remove('suggestion-focused'));
    if(i >= 0 && rows[i]) rows[i].classList.add('suggestion-focused');
    currentFocus = i;
  }

  function onPick(item){
    // item.url might be page route or search
    if(item.url){
      window.location.href = item.url;
    } else if(item.query){
      // go to index with search query
      const u = new URL(window.location.origin + '{{ url_for("index") }}');
      u.searchParams.set('search', item.query);
      window.location.href = u.toString();
    }
  }

  async function fetchSuggestions(q){
    if(!q || q.trim().length < 1){
      suggestions = [];
      renderSuggestions([], suggestionsBox);
      return;
    }
    try{
      const res = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
      if(!res.ok) return;
      const data = await res.json();
      suggestions = data.results || [];
      renderSuggestions(suggestions, suggestionsBox);
    }catch(e){
      console.error(e);
    }
  }

  // debounce
  let debounce = null;
  if(input){
    input.addEventListener('input', (e)=>{
      clearTimeout(debounce);
      debounce = setTimeout(()=> fetchSuggestions(e.target.value), 150);
    });

    input.addEventListener('keydown', (e)=>{
      const rows = suggestionsBox.querySelectorAll('.suggestion-row');
      if(e.key === 'ArrowDown'){
        e.preventDefault();
        currentFocus = Math.min(currentFocus + 1, rows.length - 1);
        setFocus(currentFocus, suggestionsBox);
      } else if(e.key === 'ArrowUp'){
        e.preventDefault();
        currentFocus = Math.max(currentFocus - 1, 0);
        setFocus(currentFocus, suggestionsBox);
      } else if(e.key === 'Enter'){
        e.preventDefault();
        if(currentFocus > -1 && suggestions[currentFocus]){
          onPick(suggestions[currentFocus]);
        } else {
          // fallback: go to index with query
          const q = input.value.trim();
          if(q) {
            const u = new URL(window.location.origin + '{{ url_for("index") }}');
            u.searchParams.set('search', q);
            window.location.href = u.toString();
          }
        }
      } else if(e.key === 'Escape'){
        suggestionsBox.style.display = 'none';
      }
    });
  }

  // button click
  if(searchBtn){
    searchBtn.addEventListener('click', ()=>{
      const q = input.value.trim();
      if(q){
        const u = new URL(window.location.origin + '{{ url_for("index") }}');
        u.searchParams.set('search', q);
        window.location.href = u.toString();
      }
    });
  }

  // mobile
  if(mobileSearchBtn){
    mobileSearchBtn.addEventListener('click', ()=>{
      mobileModal.show();
      setTimeout(()=> mobileInput.focus(), 250);
    });
  }

  if(mobileInput){
    mobileInput.addEventListener('input', debounceMobile);
  }

  let mobileTimer = null;
  function debounceMobile(e){
    clearTimeout(mobileTimer);
    mobileTimer = setTimeout(()=> fetchMobileSuggestions(e.target.value), 160);
  }

  async function fetchMobileSuggestions(q){
    if(!q) { mobileSug.innerHTML = ''; return; }
    try{
      const res = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
      const data = await res.json();
      mobileSug.innerHTML = '';
      (data.results || []).forEach(it=>{
        const r = document.createElement('div');
        r.className = 'suggestion-row';
        r.innerHTML = `<div>
                        <div class="suggestion-title">${it.title}</div>
                        <div class="suggestion-sub">${it.subtitle || ''}</div>
                       </div>`;
        r.addEventListener('click', ()=> {
          onPick(it);
          mobileModal.hide();
        });
        mobileSug.appendChild(r);
      });
    }catch(e){console.error(e);}
  }

  // click outside to close suggestions
  document.addEventListener('click', (ev)=>{
    if(!suggestionsBox.contains(ev.target) && ev.target !== input){
      suggestionsBox.style.display = 'none';
      currentFocus = -1;
    }
  });

});
