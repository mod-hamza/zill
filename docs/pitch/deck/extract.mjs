// Extract an editable layout (text runs, panels, rules) and photo-only backgrounds from index.html.
// Run from frontend/: node ../docs/pitch/deck/extract.mjs   -> deck/pptx/layout.json + deck/pptx/bg-NN.png
import { createRequire } from 'node:module';
const { chromium } = createRequire(process.cwd() + '/package.json')('playwright');
import path from 'node:path'; import fs from 'node:fs';
import { pathToFileURL, fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(here, 'pptx'); fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.goto(pathToFileURL(path.join(here, 'index.html')).href, { waitUntil: 'networkidle' });
await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(400);
const layout = await page.evaluate(() => {
  const slides = [...document.querySelectorAll('section.slide')];
  const isBake = (el) => el.matches('.bg,[class*=scrim],img') ||
    (/position:\s*absolute/.test(el.getAttribute('style') || '') && /gradient/.test(el.getAttribute('style') || '') && !el.textContent.trim());
  const rgba = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(',').map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  return slides.map((sl) => {
    const o = sl.getBoundingClientRect(); const shapes = []; const texts = [];
    let bake = 0;
    const rel = (r) => ({ x: r.left - o.left, y: r.top - o.top, w: r.width, h: r.height });
    const walk = (el) => {
      const cs = getComputedStyle(el);
      if (isBake(el)) { bake++; return; }
      const r = el.getBoundingClientRect();
      if (el !== sl && r.width > 0) {
        const bg = rgba(cs.backgroundColor);
        const grad = cs.backgroundImage.includes('gradient');
        if ((bg && bg.a > 0.02) || grad) shapes.push({ kind: 'fill', ...rel(r), color: bg && bg.a > 0.02 ? bg : { r: 26, g: 21, b: 17, a: 1 } });
        for (const side of ['Top', 'Bottom', 'Left', 'Right']) {
          const w = parseFloat(cs['border' + side + 'Width']); const c = rgba(cs['border' + side + 'Color']);
          if (w > 0 && cs['border' + side + 'Style'] !== 'none' && c && c.a > 0) shapes.push({ kind: 'line', side, ...rel(r), bw: w, color: c });
        }
        if (cs.borderRadius === '50%' || el.classList.contains('step')) {}
      }
      if (el.classList.contains('step')) {
        const s = rel(r); shapes.push({ kind: 'dot', x: s.x, y: s.y - 5, w: 9, h: 9, color: { r: 200, g: 161, b: 90, a: 1 } });
        if (el.nextElementSibling) texts.push({ ...{ x: s.x + s.w - 24 - 14, y: s.y + 30, w: 30, h: 26 }, align: 'left', lh: 26, single: true, paras: [[{ t: '→', font: 'Inter Tight', size: 22, color: { r: 200, g: 161, b: 90, a: 1 }, weight: 300, ls: 0 }]] });
      }
      // leaf block?
      const kids = [...el.children];
      const blockKid = kids.some((k) => { const d = getComputedStyle(k).display; return d !== 'inline' && d !== 'none' && k.tagName !== 'BR'; });
      const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.data.trim());
      if (!blockKid && (hasText || kids.length) && el.textContent.trim()) {
        const runs = [];
        const collect = (n, parentCs) => {
          if (n.nodeType === 3) {
            let t = n.data.replace(/\s+/g, ' ');
            const c2 = parentCs; if (c2.textTransform === 'uppercase') t = t.toUpperCase();
            if (t) runs.push({ t, font: c2.fontFamily.split(',')[0].replace(/["']/g, '').trim(), size: parseFloat(c2.fontSize), color: rgba(c2.color), weight: parseInt(c2.fontWeight), italic: c2.fontStyle === 'italic', ls: parseFloat(c2.letterSpacing) || 0 });
          } else if (n.nodeType === 1) {
            if (n.tagName === 'BR') { runs.push({ br: true }); return; }
            const c2 = getComputedStyle(n); for (const ch of n.childNodes) collect(ch, c2);
          }
        };
        for (const ch of el.childNodes) collect(ch, cs);
        // trim
        while (runs.length && runs[0].t !== undefined && !runs[0].t.trim()) runs.shift();
        if (runs.length && runs[0].t) runs[0].t = runs[0].t.replace(/^\s+/, '');
        const last = runs[runs.length - 1]; if (last && last.t) last.t = last.t.replace(/\s+$/, '');
        if (runs.length) {
          const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.3;
          // content rect (exclude padding)
          const pl = parseFloat(cs.paddingLeft), pr = parseFloat(cs.paddingRight), pt = parseFloat(cs.paddingTop), pb = parseFloat(cs.paddingBottom);
          const rr = rel(r);
          texts.push({ x: rr.x + pl, y: rr.y + pt, w: rr.w - pl - pr, h: rr.h - pt - pb, align: cs.textAlign === 'center' ? 'center' : cs.textAlign === 'right' || cs.textAlign === 'end' ? 'right' : 'left', lh, single: (rr.h - pt - pb) < lh * 1.5, paras: [runs] });
        }
        return;
      }
      if (blockKid && hasText) {
        for (const n of el.childNodes) if (n.nodeType === 3 && n.data.trim()) {
          const rg = document.createRange(); rg.selectNodeContents(n); const rr = rel(rg.getBoundingClientRect());
          const t = cs.textTransform === 'uppercase' ? n.data.trim().toUpperCase() : n.data.trim();
          const lh = parseFloat(cs.lineHeight) || parseFloat(cs.fontSize) * 1.3;
          texts.push({ x: rr.x, y: rr.y, w: Math.max(rr.w, r.width - 40), h: rr.h, align: 'left', lh, single: rr.h < lh * 1.5, paras: [[{ t, font: cs.fontFamily.split(',')[0].replace(/["']/g, '').trim(), size: parseFloat(cs.fontSize), color: rgba(cs.color), weight: parseInt(cs.fontWeight), italic: cs.fontStyle === 'italic', ls: parseFloat(cs.letterSpacing) || 0 }]] });
        }
      }
      for (const k of kids) walk(k);
    };
    walk(sl);
    return { shapes, texts, bake };
  });
});
fs.writeFileSync(path.join(out, 'layout.json'), JSON.stringify(layout));
// background (photo-only) renders
const n = layout.length;
for (let i = 0; i < n; i++) {
  if (!layout[i].bake) continue;
  await page.evaluate((idx) => {
    const sl = document.querySelectorAll('section.slide')[idx];
    const isBake = (el) => el.matches('.bg,[class*=scrim],img') || (/position:\s*absolute/.test(el.getAttribute('style') || '') && /gradient/.test(el.getAttribute('style') || '') && !el.textContent.trim());
    document.querySelectorAll('section.slide').forEach((s, j) => { s.style.display = j === idx ? '' : 'none'; });
    sl.querySelectorAll('*').forEach((e) => { e.style.visibility = isBake(e) ? 'visible' : 'hidden'; });
    window.__idx = idx;
  }, i);
  await page.locator('section.slide').nth(i).screenshot({ path: path.join(out, `bg-${String(i + 1).padStart(2, '0')}.png`) });
  await page.reload({ waitUntil: 'networkidle' }); await page.evaluate(() => document.fonts.ready);
}
await browser.close(); console.log('slides', n, 'bake', layout.map((l) => l.bake).join(','));
