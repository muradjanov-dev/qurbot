"""The storefront formatter keeps cents using decimal strings, not floats."""

import shutil
import subprocess
from pathlib import Path

import pytest


def test_browser_money_format_matches_python_cents_and_grouping() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to execute storefront JavaScript")
    root = Path(__file__).resolve().parents[2]
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const window = {QB: {lang: 'uz_cyrl'}};
vm.runInNewContext(fs.readFileSync('app/web/storefront/static/money.js', 'utf8'), {window, BigInt});
assert.equal(window.qurbotFormatUzs('100000.00'), '100 000');
assert.equal(window.qurbotFormatUzs('1234.50'), '1 234,50');
assert.equal(window.qurbotFormatUzs('1234.5'), '1 234,5');
assert.equal(window.qurbotFormatMoney('2.00', 'USD', 'uz_cyrl'), '2,00 USD');
assert.equal(window.qurbotFormatMoney('1234.5', 'USD', 'ru'), '1 234,50 USD');
"""
    result = subprocess.run(
        [node, "-e", script], cwd=root, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
