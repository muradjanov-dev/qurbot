/* Browser-bound Telegram login. The bot confirms by webhook; the browser owns polling. */
(function () {
  'use strict';

  const root = document.querySelector('[data-bot-login][data-bot-login-enabled="1"]');
  const stringsNode = document.getElementById('bot-login-strings');
  if (!root || !stringsNode) return;

  const strings = JSON.parse(stringsNode.textContent);
  const flow = root.querySelector('[data-bot-login-flow]');
  const startButton = flow?.querySelector('[data-bot-start]');
  const statusNode = flow?.querySelector('[data-bot-status]');
  const sessionNode = flow?.querySelector('[data-bot-session]');
  const codeNode = flow?.querySelector('[data-bot-code]');
  const promptNode = flow?.querySelector('[data-bot-prompt]');
  const countdownNode = flow?.querySelector('[data-bot-countdown]');
  const openLink = flow?.querySelector('[data-bot-open]');
  const checkButton = flow?.querySelector('[data-bot-check]');
  const cancelButton = flow?.querySelector('[data-bot-cancel]');
  const retryButton = flow?.querySelector('[data-bot-retry]');
  if (!flow || !startButton || !statusNode || !sessionNode || !codeNode
      || !promptNode || !countdownNode || !openLink || !checkButton
      || !cancelButton || !retryButton) return;

  let active = false;
  let busy = false;
  let checking = false;
  let completing = false;
  let started = false;
  let expiresAt = 0;
  let pollTimer = 0;
  let countdownTimer = 0;
  let telegramWindow = null;

  function visible() {return document.visibilityState === 'visible';}
  function stopTimers() {
    clearTimeout(pollTimer);
    clearInterval(countdownTimer);
    pollTimer = 0;
    countdownTimer = 0;
  }
  function status(message, state) {
    statusNode.textContent = message;
    statusNode.hidden = !message;
    statusNode.dataset.state = state || '';
  }
  function safeNext() {
    const raw = root.dataset.loginNext || '/';
    if (!raw.startsWith('/') || raw.startsWith('//') || raw.includes('\\')
        || /[\u0000-\u001f]/.test(raw)) return '/';
    try {
      const target = new URL(raw, window.location.origin);
      return target.origin === window.location.origin ? target.pathname + target.search + target.hash : '/';
    } catch (_) { return '/'; }
  }
  function safeRedirect(raw) {
    if (typeof raw !== 'string' || !raw.startsWith('/') || raw.startsWith('//')
        || raw.includes('\\') || /[\u0000-\u001f]/.test(raw)) return null;
    try {
      const target = new URL(raw, window.location.origin);
      return target.origin === window.location.origin ? target.href : null;
    } catch (_) { return null; }
  }
  function safeTelegramUrl(raw) {
    if (typeof raw !== 'string') return null;
    try {
      const target = new URL(raw);
      if (target.protocol !== 'https:' || target.hostname.toLowerCase() !== 't.me'
          || !/^\/[A-Za-z0-9_]{5,32}$/.test(target.pathname)) return null;
      return target.href;
    } catch (_) { return null; }
  }
  async function api(path, options) {
    const opts = options || {};
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), opts.timeout || 7000);
    try {
      const response = await fetch(path, {
        method: opts.method || (opts.body === undefined ? 'GET' : 'POST'),
        credentials: 'same-origin',
        cache: 'no-store',
        keepalive: Boolean(opts.keepalive),
        signal: controller.signal,
        headers: {'Content-Type': 'application/json', 'X-Bot-Login': '1'},
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      });
      let data = {};
      try {data = await response.json();} catch (_) { /* friendly status below */ }
      if (!response.ok || data.ok === false) {
        const error = new Error(data.error || data.detail || strings.unavailable);
        error.data = data;
        error.status = response.status;
        throw error;
      }
      return data;
    } finally {clearTimeout(timer);}
  }
  function errorMessage(error) {
    const code = String(
      error?.data?.status || error?.data?.code || error?.data?.error || error?.data?.detail || ''
    ).toLowerCase();
    if (code.includes('mismatch') || code.includes('invalid_code')) return strings.mismatch;
    if (code.includes('expired')) return strings.expired;
    if (code.includes('denied') || code.includes('rejected') || code.includes('blocked')) {
      return strings.denied;
    }
    if (code.includes('account_unavailable') || code.includes('invalid')) {
      return strings.bot_invalid || strings.unavailable;
    }
    return strings.unavailable;
  }
  function formatPrompt(code) {
    return strings.bot_prompt
      .replaceAll('{code}', code)
      .replaceAll('{browser}', strings.browser)
      .replaceAll('{site}', strings.site);
  }
  function closeBlankPopup() {
    try {
      if (telegramWindow && !telegramWindow.closed && telegramWindow.location.href === 'about:blank') {
        telegramWindow.close();
      }
    } catch (_) { /* A navigated Telegram tab is cross-origin and must stay open. */ }
    telegramWindow = null;
  }
  function setTerminal(message, state) {
    active = false;
    started = false;
    stopTimers();
    status(message, state);
    checkButton.hidden = true;
    cancelButton.hidden = true;
    retryButton.hidden = false;
    startButton.hidden = true;
    openLink.hidden = true;
    sessionNode.hidden = !codeNode.textContent;
  }
  function reset() {
    active = false;
    busy = false;
    checking = false;
    completing = false;
    started = false;
    expiresAt = 0;
    stopTimers();
    startButton.hidden = false;
    startButton.disabled = false;
    sessionNode.hidden = true;
    retryButton.hidden = true;
    checkButton.hidden = false;
    cancelButton.hidden = false;
    openLink.hidden = true;
    openLink.removeAttribute('href');
    codeNode.textContent = '';
    promptNode.textContent = '';
    status('', '');
    closeBlankPopup();
  }
  function updateCountdown() {
    if (!active) return;
    const seconds = Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000));
    const minutes = Math.floor(seconds / 60).toString().padStart(2, '0');
    const remainder = (seconds % 60).toString().padStart(2, '0');
    countdownNode.textContent = minutes + ':' + remainder;
    if (!seconds) expireRequest();
  }
  function startCountdown() {
    clearInterval(countdownTimer);
    if (!active || !visible()) return;
    updateCountdown();
    countdownTimer = setInterval(updateCountdown, 1000);
  }
  function schedulePoll(delay) {
    clearTimeout(pollTimer);
    if (!active || !visible()) return;
    pollTimer = setTimeout(checkStatus, delay === undefined ? 2000 : delay);
  }
  async function cancelOnServer(keepalive) {
    if (!started) return;
    started = false;
    try {await api('/auth/bot/cancel', {method: 'POST', body: {}, keepalive: Boolean(keepalive), timeout: 2500});}
    catch (_) { /* the short-lived request expires server-side */ }
  }
  async function expireRequest() {
    if (!active) return;
    active = false;
    stopTimers();
    await cancelOnServer(false);
    setTerminal(strings.expired, 'expired');
  }
  async function completeLogin() {
    completing = true;
    status(strings.approved, 'approved');
    try {
      const result = await api('/auth/bot/complete', {method: 'POST', body: {next: safeNext()}});
      const redirect = safeRedirect(result.redirect);
      if (!result.ok || !redirect) throw new Error(strings.unavailable);
      status(strings.signed_in, 'approved');
      window.location.replace(redirect);
    } catch (error) {
      completing = false;
      setTerminal(errorMessage(error), 'error');
    }
  }
  async function checkStatus() {
    if (!active || !visible() || checking) return;
    if (Date.now() >= expiresAt) {await expireRequest(); return;}
    checking = true;
    try {
      const result = await api('/auth/bot/status');
      if (result.status === 'pending' || result.status === 'claimed') {
        status(strings.waiting, result.status);
        schedulePoll(2000);
      } else if (result.status === 'approved') {
        active = false;
        started = false;
        stopTimers();
        checkButton.hidden = true;
        cancelButton.hidden = true;
        retryButton.hidden = true;
        await completeLogin();
      } else if (result.status === 'denied') {
        started = false;
        setTerminal(strings.denied, 'denied');
      } else if (result.status === 'expired') {
        started = false;
        setTerminal(strings.expired, 'expired');
      } else {
        throw new Error(strings.unavailable);
      }
    } catch (error) {
      status(errorMessage(error), 'error');
      schedulePoll(2000);
    } finally {checking = false;}
  }
  function popupFromClick() {
    try {
      const opened = window.open('about:blank', '_blank');
      if (opened) opened.opener = null;
      return opened;
    } catch (_) {return null;}
  }
  async function startLogin() {
    if (busy) return;
    reset();
    busy = true;
    startButton.disabled = true;
    status(strings.opening, 'opening');
    // Reserve the new tab during the click gesture; the source page stays here.
    telegramWindow = popupFromClick();
    try {
      const result = await api('/auth/bot/start', {
        method: 'POST',
        body: {next: safeNext()},
      });
      started = Boolean(result.ok);
      const botUrl = safeTelegramUrl(result.bot_url);
      const code = String(result.code || '');
      if (!result.ok || !botUrl || !/^\d{6}$/.test(code)) {
        await cancelOnServer(false);
        closeBlankPopup();
        throw new Error(strings.bot_invalid || strings.unavailable);
      }
      const duration = Number(result.expires_in);
      const seconds = Number.isFinite(duration) && duration > 0 ? Math.min(duration, 300) : 300;
      expiresAt = Date.now() + seconds * 1000;
      active = true;
      started = true;
      startButton.hidden = true;
      retryButton.hidden = true;
      sessionNode.hidden = false;
      checkButton.hidden = false;
      cancelButton.hidden = false;
      codeNode.textContent = code;
      promptNode.textContent = formatPrompt(code);
      openLink.href = botUrl;
      openLink.hidden = false;
      status(strings.waiting, 'pending');
      startCountdown();
      try {
        if (telegramWindow && !telegramWindow.closed) telegramWindow.location.replace(botUrl);
      } catch (_) {
        telegramWindow = null;
      }
      checkStatus();
    } catch (error) {
      closeBlankPopup();
      setTerminal(errorMessage(error), 'error');
    } finally {busy = false;}
  }
  async function cancelFromButton() {
    if (!started) {reset(); return;}
    active = false;
    stopTimers();
    await cancelOnServer(false);
    setTerminal(strings.cancel, 'cancelled');
  }

  startButton.addEventListener('click', startLogin);
  retryButton.addEventListener('click', startLogin);
  checkButton.addEventListener('click', () => checkStatus());
  cancelButton.addEventListener('click', cancelFromButton);
  document.addEventListener('visibilitychange', () => {
    if (!visible()) {stopTimers(); return;}
    if (active) {startCountdown(); checkStatus();}
  });
  window.addEventListener('focus', () => {if (active && visible()) checkStatus();});
  window.addEventListener('pagehide', stopTimers);
  window.addEventListener('pageshow', () => {
    if (active && visible()) {startCountdown(); checkStatus();}
  });
})();
