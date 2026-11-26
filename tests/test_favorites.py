"""Ejecuta app.js completo en Node VM con DOM, fetch y storage aislados (sin DB)."""
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node") or shutil.which("node.exe")


HARNESS = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const scenario = process.argv[2];
process.on('unhandledRejection', error => { throw error; });

// DOM mínimo: modela las operaciones usadas por favoritos; las otras secciones
// del app.js se ejecutan sin sus elementos. No reproduce la lógica de favoritos.
class Element {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase(); this.children = []; this.dataset = {};
    this.attributes = {}; this.listeners = {}; this.hidden = false;
    this.textContent = ''; this.disabled = false;
    this.classList = { contains: () => false };
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(name, fn) { (this.listeners[name] ??= []).push(fn); }
  click() {
    if (!this.disabled) for (const fn of this.listeners.click || []) fn({target: this});
  }
  append(...nodes) {
    for (const node of nodes) {
      node.remove(); node.parentElement = this; this.children.push(node);
    }
  }
  after(node) { this.parentElement.append(node); }
  remove() {
    if (this.parentElement) {
      const siblings = this.parentElement.children;
      siblings.splice(siblings.indexOf(this), 1); this.parentElement = null;
    }
  }
  replaceChildren(...nodes) {
    for (const child of [...this.children]) child.remove();
    this.append(...nodes);
  }
  set innerHTML(html) {
    this.replaceChildren();
    // Las respuestas de prueba son tarjetas con un botón, como el fragmento real.
    for (const match of html.matchAll(/data-fav="([^"]*)"/g)) {
      const card = new Element('article'); card.className = 'card';
      const button = new Element('button'); button.dataset.fav = match[1];
      card.append(button); this.append(card);
    }
  }
  querySelectorAll(selector) {
    const found = [];
    for (const child of this.children) {
      if ((selector === '[data-fav]' && child.dataset.fav !== undefined) ||
          (selector === '.fav-count' && child.className === 'fav-count')) found.push(child);
      found.push(...child.querySelectorAll(selector));
    }
    return found;
  }
  querySelector(selector) {
    if (selector.startsWith('#')) return this.findId(selector.slice(1));
    return this.querySelectorAll(selector)[0] || null;
  }
  findId(id) {
    for (const child of this.children) {
      if (child.id === id) return child;
      const found = child.findId(id); if (found) return found;
    }
    return null;
  }
  closest(selector) {
    if (selector === '[data-fav]' && this.dataset.fav !== undefined) return this;
    if (selector === '.card' && this.className === 'card') return this;
    return this.parentElement?.closest(selector) || null;
  }
}
const html = ids => ids.map(id => `<article class="card"><button data-fav="${id}"></button></article>`).join('');
const tick = async () => { for (let i = 0; i < 12; i++) await new Promise(setImmediate); };
function start(raw, responder, {page = true, storageThrows = false} = {}) {
  const document = new Element(); document.createElement = tag => new Element(tag);
  const count = new Element(); count.className = 'fav-count'; document.append(count);
  const button = new Element('button'); button.dataset.fav = 'new'; document.append(button);
  const grid = new Element(); grid.id = 'fav-grid';
  const empty = new Element(); empty.id = 'fav-empty'; empty.hidden = true;
  if (page) document.append(grid, empty);
  let saved = raw; const writes = [], requests = [];
  const context = {
    document, window: {}, addEventListener() {}, matchMedia: () => ({matches: false}),
    localStorage: {
      getItem(key) {
        assert.equal(key, 'yumori:fav');
        if (storageThrows) throw Error('storage unavailable');
        return saved;
      },
      setItem(key, value) { assert.equal(key, 'yumori:fav'); saved = value; writes.push(value); }
    },
    fetch: async url => {
      const parsed = new URL(url, 'http://localhost');
      assert.equal(parsed.pathname, '/fragmento/cards');
      assert.equal([...parsed.searchParams.keys()].join(','), 'ids');
      const ids = parsed.searchParams.get('ids').split(',');
      requests.push(ids);
      return responder(ids, requests.length);
    }
  };
  vm.runInNewContext(source, context, {filename: 'static/app.js', timeout: 2000});
  return {document, grid, empty, count, button, writes, requests,
    saved: () => saved,
    status: () => document.children.find(el => el.attributes.role === 'status'),
    toggle: target => {
      for (const fn of document.listeners.click) fn({target, preventDefault() {}});
    }};
}
const ok = ids => ({ok: true, text: async () => html(ids)});
const visibleIds = app => app.grid.querySelectorAll('[data-fav]').map(b => b.dataset.fav);

async function run() {
  if (scenario === 'validation') {
    for (const value of [null, '{}', '"abc"', '7', 'true', 'null', '["a",7]', '[null]', '{bad']) {
      const app = start(value, ok, {page: false});
      assert.equal(app.count.textContent, '');
      app.toggle(app.button);
      assert.deepEqual(JSON.parse(app.saved()), ['new']);
      assert.equal(app.button.attributes['aria-pressed'], 'true');
    }
    const valid = start('["a","new"]', ok, {page: false});
    assert.equal(valid.count.textContent, 2);
    valid.toggle(valid.button);
    assert.deepEqual(JSON.parse(valid.saved()), ['a']);
    const unavailable = start(null, ok, {page: false, storageThrows: true});
    assert.equal(unavailable.count.textContent, '');
  } else if (scenario === 'batches') {
    const ids = Array.from({length: 251}, (_, i) => `id${i}`);
    let release;
    const app = start(JSON.stringify(ids), (batch, n) => n === 3 ?
      new Promise(resolve => { release = () => resolve(ok(batch)); }) : ok(batch));
    await tick();
    assert.deepEqual(app.requests.map(batch => batch.length), [100, 100, 51]);
    assert.equal(app.writes.length, 0); assert.equal(app.grid.children.length, 0);
    assert.equal(app.grid.attributes['aria-busy'], 'true');
    release(); await tick();
    assert.deepEqual(JSON.parse(app.saved()), ids);
    assert.deepEqual(visibleIds(app), ids);
    assert.equal(app.count.textContent, 251);
    assert.equal(app.grid.attributes['aria-busy'], 'false');
  } else if (scenario === 'aliases') {
    const ids = Array.from({length: 102}, (_, i) => `old${i}`);
    const app = start(JSON.stringify(ids), batch => ok(batch.filter(id => id !== 'old101')
      .map(id => ['old0', 'old100'].includes(id) ? 'canonical' : id)));
    await tick();
    const expected = ['canonical', ...ids.slice(1, 100)];
    assert.deepEqual(JSON.parse(app.saved()), expected);
    assert.deepEqual(visibleIds(app), expected);
    assert.equal(app.count.textContent, 100);
  } else if (['http', 'network', 'body'].includes(scenario)) {
    const ids = Array.from({length: 101}, (_, i) => `id${i}`);
    const raw = JSON.stringify(ids); let failing = true;
    const app = start(raw, (batch, n) => {
      if (failing && n === 2) {
        if (scenario === 'network') throw Error('offline');
        if (scenario === 'body') return {ok: true, text: async () => { throw Error('interrupted'); }};
        return {ok: false, status: 503, text: async () => html([])};
      }
      return ok(batch);
    });
    await tick();
    assert.equal(app.saved(), raw); assert.equal(app.writes.length, 0);
    assert.equal(app.grid.children.length, 0); assert.equal(app.empty.hidden, true);
    const status = app.status(), retry = status.children[1];
    assert.equal(status.attributes['aria-live'], 'polite');
    assert.equal(status.attributes['aria-atomic'], 'true');
    assert.match(status.children[0].textContent, /lista guardada se conserva/);
    assert.equal(retry.tagName, 'BUTTON'); assert.equal(retry.type, 'button');
    assert.equal(retry.hidden, false); assert.equal(retry.disabled, false);
    assert.equal(app.grid.attributes['aria-busy'], 'false');
    failing = false; retry.click(); retry.click(); await tick();
    assert.equal(app.requests.length, 4); // Un único reintento aunque haya doble clic.
    assert.deepEqual(JSON.parse(app.saved()), ids);
    assert.deepEqual(visibleIds(app), ids);
    assert.equal(retry.hidden, true); assert.equal(status.children[0].textContent, '');
  } else if (scenario === 'empty') {
    for (const raw of ['[]', '{}', '[false]']) {
      const app = start(raw, ok); await tick();
      assert.equal(app.empty.hidden, false); assert.equal(app.requests.length, 0);
      assert.equal(app.writes.length, 0);
    }
    const missing = start('["gone"]', () => ok([])); await tick();
    assert.deepEqual(JSON.parse(missing.saved()), []);
    assert.equal(missing.empty.hidden, false);
  } else if (scenario === 'concurrent') {
    let release;
    const app = start('["a"]', (ids, n) => n === 1 ?
      new Promise(resolve => { release = () => resolve(ok(ids)); }) : ok(ids));
    app.toggle(app.button); // Guarda otro favorito mientras responde el servidor.
    release(); await tick();
    assert.deepEqual(JSON.parse(app.saved()), ['a', 'new']);
    assert.deepEqual(visibleIds(app), ['a', 'new']);
    assert.equal(app.requests.length, 2);
    app.toggle(app.grid.querySelectorAll('[data-fav]')[0]);
    assert.deepEqual(JSON.parse(app.saved()), ['new']);
    app.toggle(app.grid.querySelectorAll('[data-fav]')[0]);
    assert.equal(app.empty.hidden, false);
  } else if (scenario === 'encoding') {
    const ids = ['a&other=x', 'b#c', 'd+e', 'espacio aquí'];
    const app = start(JSON.stringify(ids), ok); await tick();
    assert.deepEqual(app.requests, [ids]);
    assert.deepEqual(JSON.parse(app.saved()), ids);
  } else throw Error('Unknown scenario: ' + scenario);
}
run().catch(error => { console.error(error); process.exitCode = 1; });
'''


def run_scenario(scenario):
    if not NODE:
        raise unittest.SkipTest("Node no disponible: se necesita para ejecutar el JS real")
    result = subprocess.run(
        [NODE, "-e", HARNESS, str(ROOT / "static" / "app.js"), scenario],
        capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_storage_validation_and_toggle():
    run_scenario("validation")


def test_all_batches_before_commit():
    run_scenario("batches")


def test_aliases_and_missing_products_across_batches():
    run_scenario("aliases")


def test_http_error_preserves_list_and_retry():
    run_scenario("http")


def test_network_error_preserves_list_and_retry():
    run_scenario("network")


def test_response_body_error_preserves_list_and_retry():
    run_scenario("body")


def test_empty_and_confirmed_missing():
    run_scenario("empty")


def test_edits_during_load_and_removing_last_card():
    run_scenario("concurrent")


def test_ids_are_url_encoded():
    run_scenario("encoding")


if __name__ == "__main__":
    suite = unittest.TestSuite(
        unittest.FunctionTestCase(fn, description=name)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    )
    result = unittest.TextTestRunner().run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
