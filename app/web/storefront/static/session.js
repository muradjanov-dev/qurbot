/* Bootstrap once: verified Telegram identity when available, otherwise a visitor. */
window.QB.ready = (async () => {
  const qb = window.QB;
  try {
    sessionStorage.removeItem('qb_telegram_init_data');
    sessionStorage.removeItem('qb_telegram_auth_attempted');
  } catch (_) { /* Storage is optional; identity never depends on it. */ }
  const notice = document.querySelector('[data-telegram-auth]');
  const adminEntry = location.pathname === '/login' || location.pathname.startsWith('/operator');
  if (qb.authed && (!adminEntry || qb.verified)) return true;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  const options = {credentials: 'same-origin', signal: controller.signal, cache: 'no-store'};
  try {
    // Telegram's CDN is optional, not a render-blocking dependency.
    for (let i = 0; i < 8 && !window.Telegram?.WebApp; i++) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    const tg = window.Telegram?.WebApp;
    tg?.ready(); tg?.expand();
    let accepted = false;
    if (tg?.initData) {
      const response = await fetch('/auth/webapp', {...options, method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({init_data: tg.initData, next: location.pathname})});
      if (response.status === 403) throw new Error('blocked');
      accepted = response.ok;
    }
    if (!accepted && !adminEntry) {
      const response = await fetch('/api/session', {...options, method: 'POST',
        headers: {'X-QurBot-Bootstrap': '1', 'Content-Type': 'application/json'}, body: '{}'});
      if (!response.ok) throw new Error('session');
      accepted = true;
    }
    if (!accepted) return false; // Admin login remains explicit and protected.
    const check = await fetch('/api/cart', options);
    if (!check.ok || !(await check.json()).ok) throw new Error('cookie');
    const next = document.querySelector('[data-login-next]')?.dataset.loginNext;
    const target = next && next.startsWith('/') && !next.startsWith('//') && !next.includes('\\')
      ? next : location.pathname + location.search;
    location.replace(target === '/login' ? '/operator' : target);
  } catch (_) {
    if (notice) { notice.textContent = notice.dataset.error; notice.hidden = false; }
  } finally { clearTimeout(timeout); }
  return false;
})();
