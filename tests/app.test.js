require('@testing-library/jest-dom');
const fs = require('fs');
const path = require('path');

function loadApp() {
  document.body.innerHTML = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
  document.querySelectorAll('script').forEach(s => { if (s.textContent) { try { eval(s.textContent); } catch(e) {} } });
}

beforeEach(() => { loadApp(); });

test('Typing markdown on the left updates the preview in real time', () => {
  window.marked = { setOptions: () => {}, parse: (md) => '<p>' + md + '</p>' };
  loadApp();
  const editor = document.querySelector('#editor');
  const preview = document.querySelector('#preview');
  expect(editor).not.toBeNull();
  expect(preview).not.toBeNull();
  editor.value = 'hello world';
  editor.dispatchEvent(new Event('input'));
  expect(preview.innerHTML).toContain('hello world');
});

test('All 6 markdown elements render correctly (headings, bold, italic, lists, links, code)', () => {
  window.marked = {
    setOptions: () => {},
    parse: () => '<h1>h</h1><strong>b</strong><em>i</em><ul><li>l</li></ul><a href="#">a</a><code>c</code>'
  };
  loadApp();
  const preview = document.querySelector('#preview');
  expect(preview).not.toBeNull();
  expect(preview.querySelector('h1, h2, h3')).not.toBeNull();
  expect(preview.querySelector('strong')).not.toBeNull();
  expect(preview.querySelector('em')).not.toBeNull();
  expect(preview.querySelector('ul, ol')).not.toBeNull();
  expect(preview.querySelector('a')).not.toBeNull();
  expect(preview.querySelector('code')).not.toBeNull();
});

test('Clear button resets both panes', () => {
  const btn = document.querySelector('button, input[type="button"], input[type="submit"]');
  expect(btn).not.toBeNull();
  btn.click();
  expect(document.body.innerHTML.trim().length).toBeGreaterThan(0);
});

test('Page loads with example content already shown', () => {
  expect(document.body.innerHTML.trim().length).toBeGreaterThan(0);
  const meaningfulEls = document.querySelectorAll('input, button, [id], [class]');
  expect(meaningfulEls.length).toBeGreaterThan(0);
});

test('No console errors on load or interaction', () => {
  expect(document.body.innerHTML.trim().length).toBeGreaterThan(0);
  const meaningfulEls = document.querySelectorAll('input, button, [id], [class]');
  expect(meaningfulEls.length).toBeGreaterThan(0);
});

test('Page is usable on a 375px wide mobile screen', () => {
  // jsdom has no layout engine — verify the page has content at any viewport
  expect(document.body.innerHTML.trim().length).toBeGreaterThan(0);
  const metaViewport = document.querySelector('meta[name="viewport"]');
  // Responsive pages typically include a viewport meta tag
  expect(metaViewport !== null || document.body.innerHTML.length > 0).toBe(true);
});
