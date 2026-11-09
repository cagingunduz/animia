// Letter-level QA the HyperFrames check can't do (it compares element boxes): letters whose ink touches
// (heavy display type with negative tracking glues Turkish "rı" into an "n") and letters drawn from a fallback
// font because the chosen family has no such glyph. The page is loaded once in Chrome and the anime.js
// timelines are seeked to sample times; a problem must hold for >= 0.5 s at full opacity to count.

import path from 'node:path';
import { pathToFileURL } from 'node:url';

// Runs inside the page: one sample at the current time.
function measure() {
  const canvas = document.createElement('canvas'), g = canvas.getContext('2d');
  const W = innerWidth, H = innerHeight, out = [];
  const visible = el => {
    let a = 1;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden') return false;
      a *= parseFloat(cs.opacity || '1');
      if (a < 0.9) return false;
    }
    return true;
  };
  const inkCache = new Map();
  const ink = (font, ch) => {
    const k = font + '|' + ch;
    if (!inkCache.has(k)) { g.font = font; const m = g.measureText(ch); inkCache.set(k, { l: m.actualBoundingBoxLeft, r: m.actualBoundingBoxRight, w: m.width }); }
    return inkCache.get(k);
  };
  const fallbackCache = new Map();
  const missing = (cs, ch) => {
    const fam = cs.fontFamily.split(',')[0].trim();
    const k = fam + '|' + cs.fontWeight + '|' + ch;
    if (!fallbackCache.has(k)) {
      const base = `${cs.fontStyle} ${cs.fontWeight} 100px ${fam}`;
      g.font = `${base}, monospace`; const a = g.measureText(ch).width;
      g.font = `${base}, serif`; const b = g.measureText(ch).width;
      g.font = `${base}, monospace`; const ref = g.measureText('A').width;
      g.font = `${base}, serif`; const refB = g.measureText('A').width;
      // the family itself draws 'A' (same width either way) but not this letter (the generic fallback shows through)
      fallbackCache.set(k, Math.abs(ref - refB) < 0.01 && Math.abs(a - b) > 0.01);
    }
    return fallbackCache.get(k);
  };
  // every character of every visible text node, in document order, grouped by its nearest block
  const blocks = new Map();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode, el = node.parentElement;
    if (!el || !node.nodeValue.trim() || ['SCRIPT', 'STYLE'].includes(el.tagName) || !visible(el)) continue;
    let block = el;
    while (block.parentElement && getComputedStyle(block).display.startsWith('inline')) block = block.parentElement;
    const cs = getComputedStyle(el), size = parseFloat(cs.fontSize) || 16;
    const font = `${cs.fontStyle} ${cs.fontWeight} ${size}px ${cs.fontFamily}`;
    const ls = parseFloat(cs.letterSpacing) || 0;
    const chars = blocks.get(block) || [];
    const text = node.nodeValue;
    let i = 0;
    for (const ch of text) {
      const n = ch.length, r = document.createRange();
      r.setStart(node, i); r.setEnd(node, i + n); i += n;
      if (!ch.trim()) { chars.push(null); continue; }
      const rect = r.getBoundingClientRect();
      if (!rect.width || rect.right < 0 || rect.left > W || rect.bottom < 0 || rect.top > H) { chars.push(null); continue; }
      // a letter cut by the edge of the frame (the viewer sees half of it); parked fully off-frame is fine
      const cut = rect.left < -1 || rect.right > W + 1 || rect.top < -1 || rect.bottom > H + 1;
      const m = ink(font, ch), scale = m.w + ls > 0 ? rect.width / (m.w + ls) : 1;
      chars.push({ ch, el, cut, size: size * scale, top: rect.top, h: rect.height,
        inkL: rect.left - m.l * scale, inkR: rect.left + m.r * scale, miss: ch.charCodeAt(0) > 127 && missing(cs, ch) });
    }
    chars.push(null);                                     // never pair across text nodes in different elements' ends
    blocks.set(block, chars);
  }
  const word = (list, k) => { let a = k, b = k; while (a > 0 && list[a - 1]) a--; while (b < list.length - 1 && list[b + 1]) b++; return list.slice(a, b + 1).map(c => c.ch).join(''); };
  for (const list of blocks.values()) {
    list.forEach((c, k) => {
      if (!c) return;
      if (c.miss) out.push({ code: 'missing_glyph', ch: c.ch, word: word(list, k) });
      if (c.cut) out.push({ code: 'text_off_frame', ch: c.ch, word: word(list, k) });
      const d = list[k + 1];
      if (!d || Math.abs(d.top - c.top) > c.h * 0.3) return;
      const overlap = c.inkR - d.inkL;                   // > 0: the ink of the two letters overlaps
      // pairs that misread as one letter when nearly touching: r+ı / r+n read as "n" / "m" (DM Sans at
      // letter-spacing 0 leaves ~0.09em here, at -0.06em ~0.03em)
      const misread = c.ch === 'r' && 'ınlI'.includes(d.ch) && -overlap < 0.05 * c.size;
      if (overlap > 0.015 * c.size || misread)
        out.push({ code: 'glyph_collision', pair: c.ch + d.ch, word: word(list, k), px: Math.round(overlap) });
    });
  }
  return out;
}

export async function glyphCheck(browser, dir, { step = 250, held = 500 } = {}) {
  const page = await browser.newPage();
  try {
    await page.setViewport({ width: 1080, height: 1920 });
    await page.goto(pathToFileURL(path.join(dir, 'index.html')).href, { waitUntil: 'load', timeout: 30000 });
    await page.evaluate(async () => { await document.fonts.ready; });
    const box = await page.evaluate(() => {
      const r = document.querySelector('[data-composition-id]');
      return { dur: parseFloat(r?.dataset.duration || '0') * 1000, w: parseInt(r?.dataset.width || innerWidth), h: parseInt(r?.dataset.height || innerHeight) };
    });
    if (box.w && box.h) await page.setViewport({ width: box.w, height: box.h });
    const dur = box.dur || 0;
    const seen = new Map();                                // problem key -> { start, last, first, best, f }
    for (let t = 0; t <= dur; t += step) {
      await page.evaluate(ms => { for (const tl of window.__hfAnime || []) { try { tl.seek(ms); } catch { /* not a timeline */ } } }, t);
      const found = await page.evaluate(measure);
      for (const f of found) {
        const k = f.code === 'text_off_frame' ? `${f.code}|${f.word}` : `${f.code}|${f.pair || f.ch}|${f.word}`;
        const s = seen.get(k);
        if (!s) { seen.set(k, { start: t, last: t, first: t, best: step, f }); continue; }
        if (t - s.last > step) s.start = t;                 // a new run after a gap
        s.last = t;
        const run = t - s.start + step;
        if (run > s.best) { s.best = run; s.first = s.start; }
      }
    }
    const findings = [];
    for (const { first, best, f } of seen.values()) {
      if (best < held) continue;
      const last = first + best - step;
      if (f.code === 'text_off_frame') {
        findings.push({ code: 'text_off_frame', severity: 'error', section: 'layout', time: first / 1000, heldMs: last - first + step, text: f.word,
          message: `"${f.word}" runs off the edge of the frame: part of it is cut off.`,
          fixHint: 'Keep every line inside the frame with a margin of at least 64px: lower the font-size, allow the line to wrap, or measure the longest word against the frame width.' });
        continue;
      }
      findings.push(f.code === 'glyph_collision'
        ? { code: 'glyph_collision', severity: 'error', section: 'layout', time: first / 1000, heldMs: last - first + step, text: f.word,
            message: f.px > 0
              ? `Letters "${f.pair}" in "${f.word}" touch (${f.px}px of overlapping ink): the word misreads.`
              : `Letters "${f.pair}" in "${f.word}" are only ${-f.px}px apart and read as one letter ("rı" looks like "n").`,
            fixHint: 'Set letter-spacing to 0 or more on this text (never negative with a dotless ı), or use a lighter weight.' }
        : { code: 'missing_glyph', severity: 'error', section: 'layout', time: first / 1000, heldMs: last - first + step, text: f.word,
            message: `"${f.ch}" in "${f.word}" is drawn from a fallback font: the chosen font has no such letter.`,
            fixHint: 'Use a family with Latin Extended (Turkish) glyphs, e.g. Inter, DM Sans, Manrope, Poppins, Montserrat, Rubik.' });
    }
    return findings.slice(0, 12);
  } finally {
    await page.close().catch(() => {});
  }
}
