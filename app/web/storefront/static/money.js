/* Whole-UZS display without converting money through floating-point numbers. */
window.qurbotFormatUzs = value => {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(String(value));
  if (!match) return String(value);
  const rounded = BigInt(match[1]) + BigInt(match[2]?.[0] >= '5' ? 1 : 0);
  return rounded.toString().replace(/\B(?=(\d{3})+(?!\d))/g, '.');
};
