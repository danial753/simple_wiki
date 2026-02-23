class CircularText {
  constructor(elementId, text = "azin.teb*", radius = 92) {
    this.element = document.getElementById(elementId);
    if (!this.element) return;
    
    this.text = text;
    this.radius = radius;
    this.init();
  }

  init() {
    this.element.innerHTML = '';
    this.element.classList.add('circular-text', 'spinning');

    const letters = this.text.split('');
    letters.forEach((letter, i) => {
      const span = document.createElement('span');
      span.textContent = letter === ' ' ? '\u00A0' : letter;
      const angle = (i / letters.length) * 360;
      span.style.transform = `rotate(${angle}deg) translate(${this.radius}px) rotate(-${angle}deg)`;
      this.element.appendChild(span);
    });
  }
}

// راه‌اندازی خودکار
document.addEventListener('DOMContentLoaded', () => {
  new CircularText('circularLoader');
  
  // مخفی کردن لودینگ بعد از لود کامل صفحه
  const overlay = document.getElementById('fullPageLoader');
  if (overlay) {
    window.addEventListener('load', () => {
      overlay.style.opacity = '0';
      setTimeout(() => overlay.remove(), 700);
    });
  }
});