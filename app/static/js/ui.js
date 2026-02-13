// ui.js — theme toggle + help FAB + simple guided tour
(function(){
  // ---------- theme toggle ----------
  const themeToggle = document.getElementById('themeToggle');
  const themeIcon = document.getElementById('themeIcon');
  const stored = localStorage.getItem('theme');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const isDark = stored ? stored === 'dark' : prefersDark;

  function applyTheme(dark){
    if(dark){
      document.documentElement.setAttribute('data-theme','dark');
      if(themeIcon) themeIcon.className = 'bi bi-sun';
    } else {
      document.documentElement.removeAttribute('data-theme');
      if(themeIcon) themeIcon.className = 'bi bi-moon';
    }
  }
  applyTheme(isDark);

  if(themeToggle){
    themeToggle.addEventListener('click', ()=>{
      const cur = document.documentElement.getAttribute('data-theme') === 'dark';
      applyTheme(!cur);
      localStorage.setItem('theme', !cur ? 'dark' : 'light');
    });
  }

  // ---------- help FAB & offcanvas ----------
  const helpFab = document.getElementById('helpFab');
  const helpOffcanvasEl = document.getElementById('helpOffcanvas');
  const helpOff = helpOffcanvasEl ? new bootstrap.Offcanvas(helpOffcanvasEl) : null;

  if(helpFab){
    helpFab.addEventListener('click', ()=>{
      if(helpOff) helpOff.toggle();
    });
  }

  // quick contact button
  const contactBtn = document.getElementById('contactBtn');
  if(contactBtn){
    contactBtn.addEventListener('click', ()=>{
      // open mail client (you can change email address)
      window.location.href = "mailto:support@example.com?subject=درخواست%20پشتیبانی%20Simple%20Wiki";
    });
  }

  // ---------- Simple Guided Tour ----------
  const startTourBtn = document.getElementById('startTourBtn');
  const overlay = document.getElementById('tourOverlay');
  const tooltip = document.getElementById('tourTooltip');
  const tooltipContent = document.getElementById('tourTooltipContent');
  const btnNext = document.getElementById('tourNext');
  const btnPrev = document.getElementById('tourPrev');
  const btnEnd = document.getElementById('tourEnd');

  let tourSteps = [];
  let tourIndex = 0;

  function buildTour(){
    // collect elements with data-tour attribute and build steps
    const nodes = document.querySelectorAll('[data-tour]');
    tourSteps = [];
    nodes.forEach((el)=>{
      const key = el.getAttribute('data-tour');
      // define default titles/messages per key (can be extended)
      const map = {
        'nav': { title: 'ناوبری', text: 'در این نوار می‌توانی صفحات را جستجو و وارد بخش‌های مهم شوی.' },
        'search': { title: 'جستجو', text: 'اینجا می‌توانی سریع داخل صفحات متنی جستجو کنی.' },
        'new-page': { title: 'صفحه جدید', text: 'با این دکمه می‌توانی صفحه جدید بسازی و محتوا را ذخیره کنی.' }
      };
      const info = map[key] || { title: 'راهنما', text: 'این بخش توضیح ندارد.' };
      tourSteps.push({ el, info });
    });
  }

  function showStep(i){
    if(!tourSteps.length) return;
    const step = tourSteps[i];
    if(!step) return;
    const rect = step.el.getBoundingClientRect();

    // position tooltip near element (prefer right top)
    const tooltipWidth = 340;
    let left = rect.left - tooltipWidth - 18;
    let top = rect.top;
    // if not enough space on left, show to the right
    if(left < 12){
      left = rect.right + 12;
    }
    // if top off screen, clamp
    if(top < 12) top = 12;

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
    tooltipContent.innerHTML = `<h6 style="margin:0 0 6px 0;">${step.info.title}</h6><div style="font-size:0.95rem;color:var(--muted)">${step.info.text}</div>`;

    overlay.style.display = 'block';
    tooltip.style.display = 'block';
    // highlight element (simple)
    step.el.classList.add('tour-highlight');
    // scroll into view
    step.el.scrollIntoView({behavior:'smooth', block:'center'});
  }

  function hideStep(i){
    if(!tourSteps.length) return;
    const step = tourSteps[i];
    if(step && step.el) step.el.classList.remove('tour-highlight');
  }

  function endTour(){
    overlay.style.display = 'none';
    tooltip.style.display = 'none';
    // remove highlights
    tourSteps.forEach(s => s.el.classList.remove('tour-highlight'));
    tourIndex = 0;
  }

  if(startTourBtn){
    startTourBtn.addEventListener('click', ()=>{
      // close offcanvas if open
      if(helpOff) helpOff.hide();
      buildTour();
      if(!tourSteps.length){
        alert('موردی برای تور پیدا نشد!');
        return;
      }
      tourIndex = 0;
      showStep(tourIndex);
    });
  }

  if(btnNext){
    btnNext.addEventListener('click', ()=>{
      hideStep(tourIndex);
      tourIndex++;
      if(tourIndex >= tourSteps.length) tourIndex = tourSteps.length - 1;
      showStep(tourIndex);
    });
  }

  if(btnPrev){
    btnPrev.addEventListener('click', ()=>{
      hideStep(tourIndex);
      tourIndex--;
      if(tourIndex < 0) tourIndex = 0;
      showStep(tourIndex);
    });
  }

  if(btnEnd){
    btnEnd.addEventListener('click', endTour);
  }

  // clicking overlay ends the tour
  if(overlay){
    overlay.addEventListener('click', endTour);
  }

  // small CSS helper: add a class for highlighted element
  const style = document.createElement('style');
  style.innerHTML = `
    .tour-highlight{ position:relative; z-index:1220; box-shadow:0 20px 60px rgba(99,102,241,0.22); border-radius:8px; outline:3px solid rgba(124,58,237,0.18); }
  `;
  document.head.appendChild(style);

})();
