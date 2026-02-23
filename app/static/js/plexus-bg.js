// static/js/plexus-bg.js
// نسخه حرفه‌ای 2026 – پس‌زمینه متحرک نقاط + خطوط اتصال + تعامل موس

document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('plexus-canvas');
  if (!canvas || !canvas.getContext) return;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // تنظیمات اصلی – همه چیز اینجا قابل تغییر است
  const CONFIG = {
    particleCount: 100,            // تعداد ذرات (70–150 مناسب است)
    maxDistance: 170,              // حداکثر فاصله برای رسم خط
    baseLineOpacity: 0.25,         // شفافیت پایه خطوط
    particleRadius: 2.5,           // اندازه نقاط
    particleGlow: true,            // درخشش نرم دور نقاط
    speed: 0.7,                    // سرعت پایه حرکت
    trailOpacity: 0.08,            // شدت محو شدن پس‌زمینه
    lineColor: [13, 110, 253],     // rgb رنگ خطوط (آبی اصلی)
    mouseAttraction: 0.004,        // قدرت کشش ذرات به سمت موس
    mouseRadius: 220,              // شعاع اثر موس
    reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches
  };

  let width = 0;
  let height = 0;
  let particles = [];
  let mouse = { x: null, y: null, active: false };
  let lastTime = 0;

  // تنظیم اندازه canvas
  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }

  // Debounce resize
  let resizeTimeout;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(resize, 150);
  });

  // موقعیت موس
  const updateMouse = (e) => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
    mouse.active = true;
  };
  window.addEventListener('mousemove', updateMouse);
  window.addEventListener('touchmove', e => updateMouse(e.touches[0]), { passive: true });

  window.addEventListener('mouseout', () => {
    mouse.active = false;
  });

  // کلاس ذره
  class Particle {
    constructor() {
      this.reset();
    }

    reset() {
      this.x = Math.random() * width;
      this.y = Math.random() * height;
      this.vx = (Math.random() - 0.5) * CONFIG.speed;
      this.vy = (Math.random() - 0.5) * CONFIG.speed;
    }

    update() {
      // کشش به سمت موس (اگر فعال باشد)
      if (mouse.active && mouse.x !== null && mouse.y !== null) {
        const dx = mouse.x - this.x;
        const dy = mouse.y - this.y;
        const dist = Math.hypot(dx, dy);

        if (dist < CONFIG.mouseRadius && dist > 1) {
          const force = CONFIG.mouseAttraction * (CONFIG.mouseRadius - dist) / CONFIG.mouseRadius;
          this.vx += dx * force;
          this.vy += dy * force;
        }
      }

      this.x += this.vx;
      this.y += this.vy;

      // اگر از مرز خارج شد، از سمت مقابل ظاهر شود (حلقه‌ای)
      if (this.x < -20) this.x = width + 20;
      if (this.x > width + 20) this.x = -20;
      if (this.y < -20) this.y = height + 20;
      if (this.y > height + 20) this.y = -20;
    }

    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, CONFIG.particleRadius, 0, Math.PI * 2);

      if (CONFIG.particleGlow) {
        ctx.shadowBlur = 8;
        ctx.shadowColor = 'rgba(0,0,0,0.4)';
      }

      ctx.fillStyle = '#000000';
      ctx.fill();

      // ریست سایه بعد از رسم
      ctx.shadowBlur = 0;
    }
  }

  // ایجاد ذرات
  function init() {
    particles = [];
    for (let i = 0; i < CONFIG.particleCount; i++) {
      particles.push(new Particle());
    }
  }

  // رسم اتصالات
  function drawLines() {
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const p1 = particles[i];
        const p2 = particles[j];
        const dx = p1.x - p2.x;
        const dy = p1.y - p2.y;
        const dist = Math.hypot(dx, dy);

        if (dist >= CONFIG.maxDistance) continue;

        let opacity = CONFIG.baseLineOpacity * (1 - dist / CONFIG.maxDistance);

        // اثر موس (اختیاری)
        if (CONFIG.mouseAttraction && mouse.active && mouse.x !== null) {
          const md1 = Math.hypot(p1.x - mouse.x, p1.y - mouse.y);
          const md2 = Math.hypot(p2.x - mouse.x, p2.y - mouse.y);
          if (md1 < CONFIG.mouseRadius || md2 < CONFIG.mouseRadius) {
            opacity = Math.min(0.7, opacity + 0.4);
          }
        }

        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.strokeStyle = `rgba(${CONFIG.lineColor.join(',')}, ${opacity})`;
        ctx.lineWidth = 1.2;
        ctx.stroke();
      }
    }
  }

  // حلقه اصلی انیمیشن
  function animate(timestamp) {
    if (!lastTime) lastTime = timestamp;
    const delta = timestamp - lastTime;

    // محدود کردن به ~60fps + احترام به prefers-reduced-motion
    if (delta > 16) {
      if (document.visibilityState === 'visible' && !CONFIG.reducedMotion) {
        ctx.fillStyle = `rgba(248, 249, 252, ${CONFIG.trailOpacity})`;
        ctx.fillRect(0, 0, width, height);

        particles.forEach(p => {
          p.update();
          p.draw();
        });

        drawLines();
      }

      lastTime = timestamp;
    }

    requestAnimationFrame(animate);
  }

  // راه‌اندازی
  resize();
  init();
  requestAnimationFrame(animate);
});