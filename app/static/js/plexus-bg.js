// static/js/plexus-bg.js
// نسخه نهایی نرم و روان – انیمیشن دلتا تایم + حرکت طبیعی + محو تدریجی

document.addEventListener('DOMContentLoaded', () => {
  console.log("→ plexus-bg.js لود شد");

  const canvas = document.getElementById('plexus-canvas');
  if (!canvas) {
    console.error("× canvas پیدا نشد! چک کن id='plexus-canvas' در HTML باشد.");
    return;
  }

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    console.error("× context 2D گرفته نشد!");
    return;
  }

  // تنظیم اندازه canvas
  function resizeCanvas() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
  }

  window.addEventListener('resize', resizeCanvas);
  resizeCanvas();

  // تست سریع کوتاه (۰.۵ ثانیه)
  function drawQuickTest() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);  // به جای fillRect
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.font = 'bold 70px Vazirmatn, Arial';
    ctx.fillStyle = '#0d6efd';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('Azin Teb', canvas.width / 2, canvas.height / 2);
  }

  drawQuickTest();

  // تنظیمات ذرات – تعداد بیشتر + سرعت کمتر برای حس نرم
  const particles = [];
  const PARTICLE_COUNT = 120;
  const MAX_DISTANCE = 180;

  class Particle {
    constructor() {
      this.reset();
    }

    reset() {
      this.x = Math.random() * canvas.width;
      this.y = Math.random() * canvas.height;
      this.vx = (Math.random() - 0.5) * 0.8;  // سرعت کمتر = نرم‌تر
      this.vy = (Math.random() - 0.5) * 0.8;
    }

    update(delta) {
      // استفاده از delta برای حرکت مستقل از FPS
      this.x += this.vx * delta * 0.06;
      this.y += this.vy * delta * 0.06;

      // برگشت نرم و بدون پرش (با کاهش سرعت)
      if (this.x < 0 || this.x > canvas.width) {
        this.vx *= -0.85;
        this.x = Math.max(0, Math.min(canvas.width, this.x));
      }
      if (this.y < 0 || this.y > canvas.height) {
        this.vy *= -0.85;
        this.y = Math.max(0, Math.min(canvas.height, this.y));
      }
    }

    draw() {
      ctx.beginPath();
      ctx.arc(this.x, this.y, 3.2, 0, Math.PI * 2);
      ctx.fillStyle = '#000000';
      ctx.fill();

      // درخشش نرم و طبیعی
      ctx.shadowBlur = 8;
      ctx.shadowColor = 'rgba(13, 110, 253, 0.4)';
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }

  // ایجاد ذرات
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    particles.push(new Particle());
  }

  let lastTime = performance.now();

  // انیمیشن اصلی – نرم و روان با delta time
  function animate(currentTime) {
    const delta = currentTime - lastTime;
    lastTime = currentTime;

    // محو تدریجی – مقدار 0.09 تا 0.12 بهترین تعادل برای نرم بودن و محو مسیرها
    ctx.fillStyle = 'rgba(248, 249, 252, 0.10)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // بروزرسانی و رسم ذرات
    particles.forEach(p => {
      p.update(delta);
      p.draw();
    });

    // رسم خطوط اتصال نئونی
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const distance = Math.hypot(dx, dy);

        if (distance < MAX_DISTANCE) {
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);

          const opacity = 0.38 * (1 - distance / MAX_DISTANCE);
          ctx.strokeStyle = `rgba(13, 110, 253, ${opacity})`;
          ctx.lineWidth = 1.3;
          ctx.stroke();
        }
      }
    }

    requestAnimationFrame(animate);
  }

  // شروع انیمیشن بعد از تست اولیه کوتاه
  setTimeout(() => {
    console.log("→ انیمیشن نرم و روان شروع شد");
    requestAnimationFrame(animate);
  }, 600); // ۰.۶ ثانیه کافی است برای دیدن تست
});