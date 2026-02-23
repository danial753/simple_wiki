// static/js/plexus-bg.js
// نسخه فوق پیشرفته 2027 – افکت نئونی + flocking + ripple چندلایه + هوشمند

document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('plexus-canvas');
  if (!canvas || !canvas.getContext) return;

  const ctx = canvas.getContext('2d', { alpha: true });
  if (!ctx) return;

  // تنظیمات اصلی – همه چیز قابل تنظیم
  const CONFIG = {
    particleCount: window.innerWidth < 768 ? 70 : 40,
    maxDistance: 190,
    cohesion: 0.0008,           // تمایل به نزدیک موندن (flocking)
    alignment: 0.015,           // هم‌جهت شدن با همسایه‌ها
    separation: 0.05,           // دوری از همسایه‌های خیلی نزدیک
    perceptionRadius: 80,       // شعاع دید ذرات برای flocking
    baseLineOpacity: 0.18,
    lineGlow: true,
    particlePulse: true,
    pulseSpeed: 0.0018,
    particleRadius: 2.6,
    glowIntensity: 14,
    trailOpacity: 0.09,
    lineColorStart: [59, 130, 246],   // آبی روشن
    lineColorMid: [29, 78, 216],      // آبی متوسط
    lineColorEnd: [13, 110, 253],     // آبی تیره
    mouseAttraction: 0.006,
    mouseRadius: 260,
    ripple: { enabled: true, layers: 3, speed: 0.9, maxRadius: 450, opacity: 0.15 },
    reducedMotion: window.matchMedia('(prefers-reduced-motion: reduce)').matches
  };

  let width = 0, height = 0;
  let particles = [];
  let mouse = { x: null, y: null, active: false, rippleStart: 0 };
  let lastTime = performance.now();
  let globalTime = 0;

  const isDarkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;

  // تنظیم اندازه
  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
    CONFIG.particleCount = window.innerWidth < 768 ? 70 : 40;
    initParticles();
  }

  let resizeTimer;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(resize, 200);
  });

  // موس و تاچ
  const onPointerMove = e => {
    mouse.x = e.clientX ?? e.touches?.[0]?.clientX;
    mouse.y = e.clientY ?? e.touches?.[0]?.clientY;
    mouse.active = true;
    if (CONFIG.ripple.enabled) mouse.rippleStart = performance.now();
  };

  window.addEventListener('pointermove', onPointerMove);
  window.addEventListener('pointerout', () => mouse.active = false);

  class Particle {
    constructor() {
      this.reset();
      this.phase = Math.random() * Math.PI * 2;
      this.neighbours = [];
    }

    reset() {
      this.x = Math.random() * width;
      this.y = Math.random() * height;
      this.vx = (Math.random() - 0.5) * 1.2;
      this.vy = (Math.random() - 0.5) * 1.2;
      this.alpha = 0;
      this.speed = 0;
    }

    update(delta, time) {
      // fade-in
      this.alpha = Math.min(1, this.alpha + delta * 0.0012);

      // flocking behavior
      let steerX = 0, steerY = 0;
      let count = 0;

      for (const other of particles) {
        if (other === this) continue;
        const dx = other.x - this.x;
        const dy = other.y - this.y;
        const dist = Math.hypot(dx, dy);

        if (dist < CONFIG.perceptionRadius && dist > 0) {
          count++;
          // cohesion (به مرکز گروه برو)
          steerX += other.x;
          steerY += other.y;
          // separation (دوری از خیلی نزدیک‌ها)
          if (dist < 35) {
            steerX -= dx * CONFIG.separation;
            steerY -= dy * CONFIG.separation;
          }
          // alignment (هم‌جهت شو)
          steerX += other.vx;
          steerY += other.vy;
        }
      }

      if (count > 0) {
        steerX = (steerX / count - this.x) * CONFIG.cohesion;
        steerY = (steerY / count - this.y) * CONFIG.cohesion;
        steerX += (steerX / count - this.vx) * CONFIG.alignment;
        steerY += (steerY / count - this.vy) * CONFIG.alignment;
        this.vx += steerX;
        this.vy += steerY;
      }

      // موس
      if (mouse.active && mouse.x && mouse.y) {
        const dx = mouse.x - this.x;
        const dy = mouse.y - this.y;
        const dist = Math.hypot(dx, dy);
        if (dist < CONFIG.mouseRadius && dist > 5) {
          const force = CONFIG.mouseAttraction * (CONFIG.mouseRadius - dist) / CONFIG.mouseRadius;
          this.vx += dx * force;
          this.vy += dy * force;
        }
      }

      this.x += this.vx * (CONFIG.reducedMotion ? 0.3 : 1);
      this.y += this.vy * (CONFIG.reducedMotion ? 0.3 : 1);

      // wrap around + کمی چرخش
      if (this.x < -40) this.x = width + 40;
      if (this.x > width + 40) this.x = -40;
      if (this.y < -40) this.y = height + 40;
      if (this.y > height + 40) this.y = -40;

      // محاسبه سرعت برای تغییر رنگ/اندازه
      this.speed = Math.hypot(this.vx, this.vy);
    }

    draw(time) {
      const pulse = CONFIG.particlePulse && !CONFIG.reducedMotion
        ? 1 + Math.sin(time * CONFIG.pulseSpeed + this.phase) * 0.4
        : 1;

      const r = CONFIG.particleRadius * pulse * this.alpha;

      ctx.save();
      ctx.globalAlpha = this.alpha;

      if (CONFIG.glowIntensity) {
        ctx.shadowBlur = CONFIG.glowIntensity * pulse * (1 + this.speed * 0.5);
        ctx.shadowColor = `rgba(13,110,253,${0.6 + this.speed * 0.2})`;
      }

      ctx.beginPath();
      ctx.arc(this.x, this.y, r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(0,0,0,${0.9 * this.alpha})`;
      ctx.fill();

      ctx.restore();
    }
  }

  function initParticles() {
    particles = [];
    for (let i = 0; i < CONFIG.particleCount; i++) {
      particles.push(new Particle());
    }
  }

  function drawConnections() {
    ctx.lineWidth = 1.3;
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const p1 = particles[i];
        const p2 = particles[j];
        const dx = p1.x - p2.x;
        const dy = p1.y - p2.y;
        const dist = Math.hypot(dx, dy);

        if (dist >= CONFIG.maxDistance) continue;

        const opacity = CONFIG.baseLineOpacity * (1 - dist / CONFIG.maxDistance) * p1.alpha * p2.alpha;

        const gradient = ctx.createLinearGradient(p1.x, p1.y, p2.x, p2.y);
        gradient.addColorStop(0, `rgba(${CONFIG.lineColorStart.join(',')},${opacity})`);
        gradient.addColorStop(0.5, `rgba(${CONFIG.lineColorMid.join(',')},${opacity * 0.9})`);
        gradient.addColorStop(1, `rgba(${CONFIG.lineColorEnd.join(',')},${opacity * 0.7})`);

        if (CONFIG.lineGlow) {
          ctx.shadowBlur = 10;
          ctx.shadowColor = `rgba(59,130,246,${opacity * 0.8})`;
        }

        ctx.beginPath();
        ctx.moveTo(p1.x, p1.y);
        ctx.lineTo(p2.x, p2.y);
        ctx.strokeStyle = gradient;
        ctx.stroke();
      }
    }
    ctx.shadowBlur = 0;
  }

  function drawRipples() {
    if (!CONFIG.ripple.enabled || !mouse.active || !mouse.x || !mouse.y) return;

    const elapsed = performance.now() - mouse.rippleStart;
    if (elapsed > CONFIG.ripple.maxRadius * 3) return;

    for (let i = 0; i < CONFIG.ripple.layers; i++) {
      const delay = i * 300;
      if (elapsed < delay) continue;

      const radius = ((elapsed - delay) * CONFIG.ripple.speed) % (CONFIG.ripple.maxRadius * 1.5);
      const opacity = Math.max(0, (1 - radius / CONFIG.ripple.maxRadius) * CONFIG.ripple.opacity * (1 - i * 0.3));

      ctx.beginPath();
      ctx.arc(mouse.x, mouse.y, radius, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(13,110,253,${opacity})`;
      ctx.lineWidth = 2 + opacity * 10;
      ctx.stroke();
    }
  }

  // حلقه انیمیشن
  function animate(now) {
    const delta = now - lastTime;
    globalTime += delta * 0.001;
    lastTime = now;

    if (delta > 16 && document.visibilityState === 'visible' && !CONFIG.reducedMotion) {
      ctx.fillStyle = `rgba(248,249,252,${CONFIG.trailOpacity})`;
      ctx.fillRect(0, 0, width, height);

      particles.forEach(p => {
        p.update(delta, globalTime);
        p.draw(globalTime);
      });

      drawConnections();
      drawRipples();
    }

    requestAnimationFrame(animate);
  }

  // راه‌اندازی نهایی
  resize();
  initParticles();
  requestAnimationFrame(animate);
});