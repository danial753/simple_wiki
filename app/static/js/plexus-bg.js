// static/js/plexus-bg.js

document.addEventListener('DOMContentLoaded', () => {
  const canvas = document.getElementById('plexus-canvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  // تنظیمات نهایی - نرم، سریع و تمیز
  const CONFIG = {
    particleCount: 185,
    maxDistance: 185,
    speed: 2.5,              // حرکت سریع‌تر (طبق درخواست)
    particleRadius: 2.7,
    lineOpacity: 0.5,        // شفافیت خطوط
    trailOpacity: 4.2,       // محو ملایم پس‌زمینه برای حس نرم بودن
    particleColor: '#1e88e5', // آبی نقاط
    lineColor: '#1e88e5'      // آبی خطوط
  };

  let width, height;
  let particles = [];

  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }

  window.addEventListener('resize', resize);
  resize();

  class Particle {
    constructor() {
      this.x = Math.random() * width;
      this.y = Math.random() * height;
      this.vx = (Math.random() - 0.5) * CONFIG.speed;
      this.vy = (Math.random() - 0.5) * CONFIG.speed;
    }

    update() {
      this.x += this.vx;
      this.y += this.vy;

      // برگشت نرم و طبیعی از لبه‌ها
      if (this.x < 0 || this.x > width) this.vx *= -0.88;
      if (this.y < 0 || this.y > height) this.vy *= -0.88;

      this.x = Math.max(0, Math.min(width, this.x));
      this.y = Math.max(0, Math.min(height, this.y));
    }

    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, CONFIG.particleRadius, 0, Math.PI * 2);
      ctx.fillStyle = CONFIG.particleColor;
      ctx.fill();
    }
  }

  // ایجاد ذرات
  for (let i = 0; i < CONFIG.particleCount; i++) {
    particles.push(new Particle());
  }

  function animate() {
    // محو ملایم پس‌زمینه (برای حس نرم و تمیز بودن)
    ctx.fillStyle = `rgba(255, 255, 255, ${CONFIG.trailOpacity})`;
    ctx.fillRect(0, 0, width, height);

    // بروزرسانی و رسم نقاط
    particles.forEach(p => {
      p.update();
      p.draw();
    });

    // رسم خطوط اتصال نرم و زیبا
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.hypot(dx, dy);

        if (dist < CONFIG.maxDistance) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);

          const opacity = CONFIG.lineOpacity * (1 - dist / CONFIG.maxDistance);
          ctx.strokeStyle = `rgba(30, 136, 229, ${opacity})`;
          ctx.lineWidth = 1.15;
          ctx.stroke();
        }
      }
    }

    requestAnimationFrame(animate);
  }

  animate();
});