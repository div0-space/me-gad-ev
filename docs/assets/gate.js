/* The backend alone verifies enrollment and grants access. */
(() => {
  'use strict';
  const prompt = document.getElementById('agent-prompt');
  const copy = document.getElementById('copy-prompt');
  const copyStatus = document.getElementById('copy-status');
  const verdict = document.getElementById('verdict');
  const go = document.getElementById('go');
  const retry = document.getElementById('retry');
  const actions = document.getElementById('gate-actions');
  if (!prompt || !copy || !copyStatus || !verdict || !go || !retry || !actions) return;

  const language = document.documentElement.lang === 'pl' ? 'pl' : 'en';
  const messages = {
    pl: {
      loading: 'Ładowanie połączenia do sprawdzenia uczestnictwa…',
      unavailable: 'Logowanie nie jest skonfigurowane albo jest teraz niedostępne. Prywatne wpisy pozostają zamknięte. Publiczne historie są dostępne.',
      ready: 'Możesz przejść do oficjalnego MEGA.dev, zalogować się i zatwierdzić sprawdzenie uczestnictwa.',
      failed: 'Nie udało się pobrać poprawnych danych logowania. Spróbuj ponownie albo przeczytaj publiczne historie. Dostęp nie został przyznany.',
      opening: 'Otwieranie oficjalnej strony logowania…',
      copied: 'Skopiowano. Wklej tekst do rozmowy z agentem.',
      manual: 'Automatyczne kopiowanie jest niedostępne. Zaznacz i skopiuj powyższy tekst do rozmowy z agentem.',
      prompt: (handshake, destination) => `Przeczytaj ${handshake}. Pomóż mi zalogować się w tej przeglądarce przez oficjalny MEGA.dev i zatwierdzić świeże połączenie OAuth, a potem otworzyć ${destination}. Samodzielnie zaloguję się i zatwierdzę dostęp, jeśli będzie to potrzebne. Nie kopiuj istniejących danych logowania z mojego środowiska ani nie proś o wklejanie tokenów. Użyj adresu logowania zwróconego przez handshake; backend musi sprawdzić uczestnictwo.`,
    },
    en: {
      loading: 'Loading the enrollment handshake…',
      unavailable: 'Sign-in is not configured or is currently unavailable. Private records remain closed. Public stories are available.',
      ready: 'Continue to official MEGA.dev to sign in and approve the enrollment check.',
      failed: 'Could not load a valid enrollment handshake. Retry or read the public stories. No access has been granted.',
      opening: 'Opening official sign-in…',
      copied: 'Copied. Paste the text into your agent conversation.',
      manual: 'Automatic copy is unavailable. Select and copy the text above into your agent conversation.',
      prompt: (handshake, destination) => `Read ${handshake}. Help me sign in through official MEGA.dev and approve a fresh OAuth connection in this browser, then open ${destination}. I will sign in and approve access myself if needed. Do not copy existing harness credentials or ask me to paste tokens. Use the handshake login URL; the backend must verify enrollment.`,
    },
  }[language];

  // Closed local paths only: no origins, encodings, traversal, queries or fragments.
  const memberPath = /^\/members\/(?:pl\/)?journal\/(?:[a-z0-9]+(?:-[a-z0-9]+)*\/)?$(?![\s\S])/;
  const requested = new URLSearchParams(location.search).getAll('next');
  const raw = requested.length === 1 ? requested[0] : '';
  const canonical = raw.endsWith('/') ? raw : raw + '/';
  const isMember = memberPath.test(canonical);
  const isChallenge = canonical === '/challenge/' || /^\/challenge\/s01e0[1-3]\/entry\/$(?![\s\S])/.test(canonical);
  const destination = isMember || isChallenge ? canonical : (language === 'pl' ? '/members/pl/journal/' : '/members/journal/');

  // The unchanged production gate sends all anonymous member requests here.
  if (isMember && canonical.startsWith('/members/pl/') && location.pathname === '/gate/') {
    location.replace('/pl/gate/?' + new URLSearchParams({ next: canonical }));
    return;
  }
  for (const link of document.querySelectorAll('.language-switch a')) {
    // Preserve only the validated closed return path, never arbitrary query data.
    const target = new URL(link.href, location.origin);
    const translated = memberPath.test(destination)
      ? destination.replace(/^\/members\/(?:pl\/)?/, link.hreflang === 'pl' ? '/members/pl/' : '/members/')
      : destination;
    target.searchParams.set('next', translated);
    link.href = target.href;
  }

  // Production OAuth accepts the existing member archive, not localized stories.
  const next = memberPath.test(destination) ? '/members/journal/' : destination;
  const handshake = new URL('/gate/handshake', location.origin);
  handshake.searchParams.set('next', next);
  prompt.textContent = messages.prompt(handshake.href, new URL(destination, location.origin).href);
  let loginUrl = null;
  const returnKey = 'journal.member-return';
  try { sessionStorage.removeItem(returnKey); } catch { /* Storage is optional. */ }

  function rememberReturn() {
    try {
      sessionStorage.removeItem(returnKey);
      if (memberPath.test(destination) && destination !== next) sessionStorage.setItem(returnKey, destination);
    } catch { /* Without storage, login returns to the English member archive. */ }
  }

  function selectPrompt() {
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(prompt);
    if (selection) {
      selection.removeAllRanges();
      selection.addRange(range);
    }
    prompt.focus();
    copyStatus.textContent = messages.manual;
  }

  copy.addEventListener('click', () => {
    rememberReturn();
    if (!navigator.clipboard || !navigator.clipboard.writeText) {
      selectPrompt();
      return;
    }
    navigator.clipboard.writeText(prompt.textContent).then(() => {
      copyStatus.textContent = messages.copied;
    }).catch(selectPrompt);
  });

  function validatedLogin(value) {
    if (typeof value !== 'string' || !value.startsWith('/gate/login?')) return null;
    const url = new URL(value, location.origin);
    if (url.origin !== location.origin || url.pathname !== '/gate/login' ||
        url.username || url.password || url.hash ||
        url.searchParams.getAll('next').length !== 1 ||
        url.searchParams.get('next') !== next ||
        Array.from(url.searchParams.keys()).some(key => key !== 'next')) return null;
    return url.href;
  }

  function loadHandshake() {
    loginUrl = null;
    go.disabled = true;
    retry.hidden = true;
    retry.disabled = true;
    actions.setAttribute('aria-busy', 'true');
    verdict.textContent = messages.loading;
    fetch(handshake.href, { cache: 'no-store', credentials: 'same-origin', redirect: 'error' })
      .then(response => {
        if (!response.ok) throw new Error('Handshake unavailable');
        return response.json();
      }).then(body => {
        if (!body || body.available !== true || body.configured !== true) {
          verdict.textContent = messages.unavailable;
          return;
        }
        loginUrl = validatedLogin(body.login_url);
        if (!loginUrl) throw new Error('Invalid login route');
        go.disabled = false;
        verdict.textContent = messages.ready;
      }).catch(() => {
        loginUrl = null;
        go.disabled = true;
        verdict.textContent = messages.failed;
      }).finally(() => {
        actions.setAttribute('aria-busy', 'false');
        retry.disabled = false;
        retry.hidden = !go.disabled;
      });
  }

  retry.addEventListener('click', loadHandshake);
  go.addEventListener('click', () => {
    if (go.disabled || !loginUrl) return;
    rememberReturn();
    go.disabled = true;
    verdict.textContent = messages.opening;
    location.assign(loginUrl);
  });
  loadHandshake();
})();
