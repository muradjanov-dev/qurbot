/* Decimal-string money display. Conversion and price arithmetic stay server-side. */
(function () {
  'use strict';

  function parts(value) {
    const match = /^([+-]?)(\d+)(?:\.(\d+))?$/.exec(String(value));
    if (!match) return null;
    return {sign: match[1], whole: match[2], fraction: match[3] || ''};
  }

  function group(whole) {return whole.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');}

  function formatUzs(value) {
    const number = parts(value);
    if (!number) return String(value);
    let fraction = number.fraction.replace(/0+$/, '');
    if (fraction && number.fraction.length >= 2) fraction = fraction.padEnd(2, '0');
    return number.sign + group(number.whole) + (fraction ? ',' + fraction : '');
  }

  function formatUsd(value) {
    const number = parts(value);
    if (!number) return String(value);
    let cents = BigInt(number.whole) * 100n + BigInt((number.fraction + '00').slice(0, 2));
    if ((number.fraction[2] || '0') >= '5') cents += 1n;
    const whole = (cents / 100n).toString();
    const tail = (cents % 100n).toString().padStart(2, '0');
    return number.sign + group(whole) + ',' + tail;
  }

  function currencyLabel(currency, lang) {
    if (currency !== 'UZS') return currency;
    if (lang === 'ru') return 'сум';
    if (lang === 'uz_latn') return "so'm";
    return 'сўм';
  }

  window.qurbotFormatUzs = formatUzs;
  window.qurbotFormatMoney = function (value, currency, lang) {
    const code = String(currency || 'UZS').toUpperCase();
    const amount = code === 'USD' ? formatUsd(value) : formatUzs(value);
    return amount + ' ' + currencyLabel(code, lang || window.QB?.lang);
  };
})();
