// discover.js — client side suggestions + tag cloud + interactions
(function(){

  const pages = (DISCOVER_DATA && DISCOVER_DATA.pages) ? DISCOVER_DATA.pages.slice() : [];
  const tagsFromServer = (DISCOVER_DATA && DISCOVER_DATA.tags) ? DISCOVER_DATA.tags.slice() : [];

  const input = document.getElementById('discoverInput');
  const suggestions = document.getElementById('suggestions');
  const tagCloud = document.getElementById('tagCloud');
  const form = document.getElementById('discoverForm');

  // Build tag cloud from server tags OR infer from pages (simple rotation)
  function buildTagCloud(){
    if(tagsFromServer && tagsFromServer.length){
      tagsFromServer.slice(0,24).forEach(t=>{
        const el = document.createElement('button');
        el.type = 'button';
        el.className = 'tag-chip btn';
        el.textContent = t;
        el.addEventListener('click', ()=> onTagClick(t));
        tagCloud.appendChild(el);
      });
      return;
    }

    // fallback: create tags by slicing words from page names
    const inferred = new Set();
    pages.forEach(p=>{
      p.split(/[\-\_ ]+/).slice(0,3).forEach(w=>{
        if(w.length>2) inferred.add(w);
      });
    });

    Array.from(inferred).slice(0,24).forEach(t=>{
      const el = document.createElement('button');
      el.type = 'button';
      el.className = 'tag-chip btn';
      el.textContent = t;
      el.addEventListener('click', ()=> onTagClick(t));
      tagCloud.appendChild(el);
    });
  }

  function onTagClick(tag){
    input.value = tag;
    showSuggestions(tag);
    // optionally auto-submit after small delay
    setTimeout(()=> form.submit(), 600);
  }

  function showSuggestions(q){
    const qlow = (q || input.value || '').toLowerCase().trim();
    if(!qlow){
      hideSuggestions();
      return;
    }

    const matches = pages.filter(p=> p.toLowerCase().includes(qlow)).slice(0,12);

    suggestions.innerHTML = '';
    if(matches.length === 0){
      const n = document.createElement('div');
      n.className = 'suggestion-item text-muted';
      n.textContent = 'نتیجه‌ای یافت نشد. Enter را برای جستجوی کامل فشار دهید.';
      suggestions.appendChild(n);
    } else {
      matches.forEach(m=>{
        const row = document.createElement('div');
        row.className = 'suggestion-item';
        row.textContent = m.replace(/\-/g,' ');
        row.addEventListener('click', ()=> {
          // go to page
          window.location.href = `/page/${m}`;
        });
        suggestions.appendChild(row);
      });
    }

    suggestions.style.display = 'block';
    suggestions.setAttribute('aria-hidden','false');
  }

  function hideSuggestions(){
    suggestions.style.display = 'none';
    suggestions.setAttribute('aria-hidden','true');
  }

  if(input){
    let debounceTimer = null;
    input.addEventListener('input', (e)=>{
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(()=> showSuggestions(e.target.value), 120);
    });

    input.addEventListener('focus', ()=>{
      if(input.value) showSuggestions(input.value);
    });

    input.addEventListener('keydown', (e)=>{
      if(e.key === 'Escape') hideSuggestions();
      if(e.key === 'Enter' && input.value.trim()){
        // allow form submit to run normally
      }
    });

    // click outside closes suggestions
    document.addEventListener('click', (ev)=>{
      if(!suggestions.contains(ev.target) && ev.target !== input){
        hideSuggestions();
      }
    });
  }

  // on submit -> redirect to index with search param
  window.onDiscoverSearch = function(ev){
    ev.preventDefault();
    const q = input.value.trim();
    if(!q) return false;
    // navigate to index with search query (index route handles the search)
    const url = new URL(window.location.origin + '{{ url_for("index") }}');
    url.searchParams.set('search', q);
    window.location.href = url.toString();
    return false;
  };

  // initialize
  buildTagCloud();

})();
