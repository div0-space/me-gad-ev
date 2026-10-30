/* Semantic links remain visible without JS. No remote requests or dependencies. */
(() => {
  'use strict';
  const site = document.querySelector('.journal-site');
  if (!site) return;
  // Resume a closed return intent only after the server served a protected page.
  // This changes navigation, never authentication or access policy.
  if (site.classList.contains('member-site') && location.pathname === '/members/journal/') {
    let destination = null;
    try {
      destination = sessionStorage.getItem('journal.member-return');
      sessionStorage.removeItem('journal.member-return');
    } catch { /* Storage is optional; the authenticated archive remains usable. */ }
    if (typeof destination === 'string' &&
        /^\/members\/(?:pl\/)?journal\/(?:[a-z0-9]+(?:-[a-z0-9]+)*\/)?$(?![\s\S])/.test(destination) &&
        destination !== location.pathname) {
      location.replace(destination);
      return;
    }
  }
  const toggle = site.querySelector('.menu-toggle');
  const nav = site.querySelector('#primary-nav');
  if (toggle && nav && toggle.getAttribute('aria-controls') === nav.id) {
    const mobile = window.matchMedia('(max-width: 767px)');
    const setOpen = (open, restoreFocus = false) => {
      toggle.setAttribute('aria-expanded', String(open));
      nav.classList.toggle('is-open', open);
      if (restoreFocus) toggle.focus();
    };
    toggle.addEventListener('click', () => setOpen(toggle.getAttribute('aria-expanded') !== 'true'));
    site.addEventListener('keydown', event => {
      if (event.key === 'Escape' && mobile.matches && toggle.getAttribute('aria-expanded') === 'true') {
        setOpen(false, true);
      }
    });
    nav.addEventListener('click', event => {
      if (mobile.matches && event.target.closest('a')) setOpen(false);
    });
    // Do not hide the focused navigation when crossing the mobile breakpoint.
    mobile.addEventListener('change', () => setOpen(mobile.matches && nav.contains(document.activeElement)));
    setOpen(false);
    site.classList.add('nav-enhanced');
  }
  const toc = site.querySelector('.article-toc');
  if (!toc || !('IntersectionObserver' in window)) return;
  const targets = new Map();
  for (const link of toc.querySelectorAll('a[href^="#"]')) {
    let id;
    try { id = decodeURIComponent(link.hash.slice(1)); } catch { continue; }
    const heading = document.getElementById(id);
    if (heading) targets.set(heading, link);
  }
  if (!targets.size) return;
  const visible = new Set();
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.isIntersecting) visible.add(entry.target);
      else visible.delete(entry.target);
    }
    const active = [...targets.keys()].find(heading => visible.has(heading));
    if (!active) return;
    for (const [heading, link] of targets) {
      if (heading === active) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    }
  }, { rootMargin: '-100px 0px -45% 0px' });
  for (const heading of targets.keys()) observer.observe(heading);
})();
