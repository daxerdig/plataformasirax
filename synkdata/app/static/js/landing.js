/* =============================================================================
   SynkData Landing — Animaciones JS
   Estilo Babel Street: partículas, network graph, scroll reveals, contadores
   ============================================================================= */
(function () {
  'use strict';

  /* ── Cursor glow ───────────────────────────────────────────────────────── */
  function initCursorGlow() {
    const glow = document.createElement('div');
    glow.className = 'cursor-glow';
    glow.style.opacity = '0';
    document.body.appendChild(glow);

    let targetX = window.innerWidth / 2;
    let targetY = window.innerHeight / 2;
    let currentX = targetX;
    let currentY = targetY;

    document.addEventListener('mousemove', (e) => {
      targetX = e.clientX;
      targetY = e.clientY;
      glow.style.opacity = '1';
    });
    document.addEventListener('mouseleave', () => {
      glow.style.opacity = '0';
    });

    function animate() {
      currentX += (targetX - currentX) * 0.1;
      currentY += (targetY - currentY) * 0.1;
      glow.style.left = currentX + 'px';
      glow.style.top = currentY + 'px';
      requestAnimationFrame(animate);
    }
    animate();
  }

  /* ── Hero particles canvas ─────────────────────────────────────────────── */
  function initHeroParticles() {
    const canvas = document.getElementById('heroParticles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let particles = [];
    let mouse = { x: null, y: null, radius: 150 };

    function resize() {
      canvas.width = canvas.offsetWidth;
      canvas.height = canvas.offsetHeight;
    }
    resize();
    window.addEventListener('resize', resize);

    const PARTICLE_COUNT = Math.min(80, Math.floor((canvas.width * canvas.height) / 15000));

    class Particle {
      constructor() {
        this.x = Math.random() * canvas.width;
        this.y = Math.random() * canvas.height;
        this.vx = (Math.random() - 0.5) * 0.4;
        this.vy = (Math.random() - 0.5) * 0.4;
        this.size = Math.random() * 2 + 0.5;
        this.baseColor = Math.random() > 0.5 ? '0, 217, 255' : '37, 99, 235';
      }
      update() {
        this.x += this.vx;
        this.y += this.vy;
        if (this.x < 0 || this.x > canvas.width) this.vx *= -1;
        if (this.y < 0 || this.y > canvas.height) this.vy *= -1;

        if (mouse.x !== null) {
          const dx = mouse.x - this.x;
          const dy = mouse.y - this.y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < mouse.radius) {
            const force = (mouse.radius - dist) / mouse.radius;
            this.x -= dx * force * 0.02;
            this.y -= dy * force * 0.02;
          }
        }
      }
      draw() {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(' + this.baseColor + ', 0.8)';
        ctx.fill();
      }
    }

    function init() {
      particles = [];
      for (let i = 0; i < PARTICLE_COUNT; i++) particles.push(new Particle());
    }
    init();

    function connect() {
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120) {
            const opacity = (1 - dist / 120) * 0.3;
            ctx.strokeStyle = 'rgba(0, 217, 255, ' + opacity + ')';
            ctx.lineWidth = 0.5;
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.stroke();
          }
        }
      }
    }

    function animate() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      particles.forEach(p => { p.update(); p.draw(); });
      connect();
      requestAnimationFrame(animate);
    }
    animate();

    canvas.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
    });
    canvas.addEventListener('mouseleave', () => {
      mouse.x = null; mouse.y = null;
    });
  }

  /* ── Scroll reveal (IntersectionObserver) ──────────────────────────────── */
  function initScrollReveal() {
    const reveals = document.querySelectorAll('.reveal, .timeline-item');
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -50px 0px' });

    reveals.forEach(el => observer.observe(el));
  }

  /* ── Animated counters ─────────────────────────────────────────────────── */
  function animateCounter(el) {
    const target = parseFloat(el.dataset.target);
    const suffix = el.dataset.suffix || '';
    const decimals = parseInt(el.dataset.decimals || '0');
    const duration = 2000;
    const start = performance.now();

    function update(now) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = target * eased;
      el.innerHTML = current.toLocaleString('es-MX', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      }) + (suffix ? '<span class="stat-suffix">' + suffix + '</span>' : '');
      if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
  }

  function initCounters() {
    const counters = document.querySelectorAll('[data-target]');
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          animateCounter(entry.target);
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.5 });
    counters.forEach(c => observer.observe(c));
  }

  /* ── Navbar scroll state ───────────────────────────────────────────────── */
  function initNavbarScroll() {
    const nav = document.querySelector('.landing-nav');
    if (!nav) return;
    const onScroll = () => {
      if (window.scrollY > 50) nav.classList.add('scrolled');
      else nav.classList.remove('scrolled');
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();
  }

  /* ── Network graph (SVG animado) ───────────────────────────────────────── */
  function initNetworkGraph() {
    const svg = document.getElementById('networkGraph');
    if (!svg) return;

    // Centrar + nodos orbitando
    const nodes = svg.querySelectorAll('.net-node:not(.center)');
    nodes.forEach((node, i) => {
      const angle = (i / nodes.length) * Math.PI * 2;
      const radius = 140;
      const cx = 250 + Math.cos(angle) * radius;
      const cy = 250 + Math.sin(angle) * radius;
      node.setAttribute('cx', cx);
      node.setAttribute('cy', cy);
      node.style.transformOrigin = cx + 'px ' + cy + 'px';
      // Pulse con delay escalonado
      node.style.animationDelay = (i * 0.3) + 's';
      node.classList.add('pulse');
    });

    // Etiquetas
    const labels = svg.querySelectorAll('.net-label');
    labels.forEach((label, i) => {
      const angle = (i / labels.length) * Math.PI * 2;
      const radius = 175;
      const x = 250 + Math.cos(angle) * radius;
      const y = 250 + Math.sin(angle) * radius + 4;
      label.setAttribute('x', x);
      label.setAttribute('y', y);
    });

    // Aristas hacia el centro
    const edges = svg.querySelectorAll('.net-edge');
    edges.forEach((edge, i) => {
      const angle = (i / nodes.length) * Math.PI * 2;
      const radius = 140;
      const x = 250 + Math.cos(angle) * radius;
      const y = 250 + Math.sin(angle) * radius;
      edge.setAttribute('d', 'M 250 250 L ' + x + ' ' + y);
      edge.style.animationDelay = (i * 0.2) + 's';
    });
  }

  /* ── 3D Tilt en feature cards ──────────────────────────────────────────── */
  function initTilt() {
    const cards = document.querySelectorAll('.feature-card');
    cards.forEach(card => {
      card.addEventListener('mousemove', (e) => {
        const rect = card.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const cx = rect.width / 2;
        const cy = rect.height / 2;
        const rotateX = ((y - cy) / cy) * -4;
        const rotateY = ((x - cx) / cx) * 4;
        card.style.transform =
          'translateY(-8px) perspective(1000px) rotateX(' + rotateX + 'deg) rotateY(' + rotateY + 'deg)';
      });
      card.addEventListener('mouseleave', () => {
        card.style.transform = '';
      });
    });
  }

  /* ── Typing effect en hero subtitle ────────────────────────────────────── */
  function initTyping() {
    const el = document.getElementById('typedText');
    if (!el) return;
    const phrases = [
      'verificación de identidad',
      'cumplimiento normativo KYC/AML',
      'screening de listas restrictivas',
      'inteligencia de riesgo',
    ];
    let phraseIdx = 0;
    let charIdx = 0;
    let deleting = false;

    function tick() {
      const current = phrases[phraseIdx];
      if (deleting) {
        charIdx--;
        el.textContent = current.substring(0, charIdx);
        if (charIdx === 0) {
          deleting = false;
          phraseIdx = (phraseIdx + 1) % phrases.length;
          setTimeout(tick, 400);
          return;
        }
        setTimeout(tick, 40);
      } else {
        charIdx++;
        el.textContent = current.substring(0, charIdx);
        if (charIdx === current.length) {
          deleting = true;
          setTimeout(tick, 2200);
          return;
        }
        setTimeout(tick, 70);
      }
    }
    setTimeout(tick, 1000);
  }

  /* ── Form submission ───────────────────────────────────────────────────── */
  function initForm() {
    const form = document.getElementById('accessForm');
    if (!form) return;

    const showToast = (msg, type) => {
      const toast = document.createElement('div');
      toast.className = 'toast ' + (type || '');
      toast.innerHTML =
        '<span style="font-size:1.2rem">' +
          (type === 'success' ? '✓' : type === 'error' ? '⚠' : 'ℹ') +
        '</span><span>' + msg + '</span>';
      document.body.appendChild(toast);
      setTimeout(() => {
        toast.style.animation = 'toastSlide 0.3s reverse forwards';
        setTimeout(() => toast.remove(), 300);
      }, 4000);
    };

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submitBtn = form.querySelector('.form-submit');
      const originalText = submitBtn.innerHTML;
      submitBtn.disabled = true;
      submitBtn.innerHTML =
        '<span class="form-submit-spinner"></span> Enviando solicitud...';

      const data = Object.fromEntries(new FormData(form).entries());
      if (data.expected_volume) data.expected_volume = parseInt(data.expected_volume);
      else delete data.expected_volume;

      try {
        const resp = await fetch('/api/v1/access/request', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
        if (resp.ok) {
          showToast('¡Solicitud enviada! Un administrador la revisará pronto.', 'success');
          setTimeout(() => {
            window.location.href = '/api/v1/access/success';
          }, 1200);
        } else {
          const err = await resp.json().catch(() => ({}));
          const msg = err.detail || 'No se pudo enviar la solicitud.';
          showToast(Array.isArray(msg) ? msg.map(m => m.msg || m).join(', ') : msg, 'error');
        }
      } catch (err) {
        showToast('Error de red: ' + err.message, 'error');
      } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
      }
    });
  }

  /* ── Init on DOM ready ─────────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', () => {
    initCursorGlow();
    initHeroParticles();
    initScrollReveal();
    initCounters();
    initNavbarScroll();
    initNetworkGraph();
    initTilt();
    initTyping();
    initForm();
  });
})();
