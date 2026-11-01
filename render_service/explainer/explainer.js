/* Explainer kit: a 1080x1920 explainer reel on cream paper. Everything is driven by one plan (absolute times in
   seconds) and drawn as a pure function of t, so the renderer can seek any frame.

   Layers, bottom to top: paper, scenes, presenter, captions, wipes.
   Motion vocabulary: pop (0.55 -> 1, 0.34 s, back.out 2.2), rise (70 px up, 0.4 s, power3.out), exit (50 px up and
   out, 0.22 s), slam (1.22 -> 1, 0.24 s, power4.out), stamp (1.75 -> 1 and -18 -> -6 deg, 0.2 s), and a halftone
   dot wipe (13 x 23 ink dots grow from the centre out, then shrink away, 0.9 s). */
(function () {
  const C = { paper: '#EBE7E1', ink: '#1E1C1A', red: '#D7372C', grey: '#8A857E', light: '#B5AFA7', card: '#FBFAF8' };
  const W = 1080, H = 1920;
  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const span = (t, a, b) => clamp((t - a) / Math.max(1e-6, b - a), 0, 1);
  const E = {
    backOut: (s, k = 2.2) => { s = clamp(s, 0, 1); return 1 + (k + 1) * (s - 1) ** 3 + k * (s - 1) ** 2; },
    p3: s => 1 - (1 - clamp(s, 0, 1)) ** 3, p4: s => 1 - (1 - clamp(s, 0, 1)) ** 4, in2: s => clamp(s, 0, 1) ** 2,
    io: s => { s = clamp(s, 0, 1); return s < 0.5 ? 2 * s * s : 1 - (-2 * s + 2) ** 2 / 2; },
  };
  function rng(seed) { let s = (seed >>> 0) || 1; return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; }

  // ---------------------------------------------------------------- DOM helpers
  const css = `
  @font-face{font-family:Anton;src:url(explainer/fonts/Anton-Regular.ttf)}
  @font-face{font-family:'Instrument Sans';src:url(explainer/fonts/InstrumentSans.ttf);font-weight:400 700}
  @font-face{font-family:'Instrument Serif';src:url(explainer/fonts/InstrumentSerif-Italic.ttf);font-style:italic}
  @font-face{font-family:'JetBrains Mono';src:url(explainer/fonts/JetBrainsMono.ttf);font-weight:100 800}
  #ex{position:absolute;inset:0;overflow:hidden;background:${C.paper};font-family:'Instrument Sans',sans-serif;color:${C.ink}}
  #ex .layer{position:absolute;inset:0}
  #ex .el{position:absolute;opacity:0;will-change:transform,opacity}
  #ex .cardw .sh{position:absolute;inset:0;transform:translate(-13px,12px);border-radius:20px;
    background-image:radial-gradient(circle,${C.ink} 0.85px,transparent 1.15px);background-size:8px 8px}
  #ex .card{position:absolute;inset:0;background:${C.card};border:3px solid ${C.ink};border-radius:20px;overflow:hidden}
  #ex .mono{font-family:'JetBrains Mono',monospace}
  #ex .anton{font-family:Anton,sans-serif;letter-spacing:0.5px;line-height:0.95}
  #ex .serif{font-family:'Instrument Serif',serif;font-style:italic}
  #ex .cap{position:absolute;left:120px;top:196px;width:850px;font-size:62px;font-weight:500;line-height:1.14;letter-spacing:-0.5px}
  #ex .cap span{opacity:0}
  #ex .stamp{font-family:Anton,sans-serif;font-size:52px;color:${C.red};border:5px solid ${C.red};padding:4px 18px 0;line-height:1.1;white-space:nowrap}
  #ex .badge{width:112px;height:112px;border-radius:50%;background:${C.red};color:${C.card};font-family:Anton,sans-serif;font-size:56px;
    display:flex;align-items:center;justify-content:center;border:3px solid ${C.ink}}
  `;
  const div = (parent, cls, style, html) => {
    const d = document.createElement('div'); if (cls) d.className = cls; if (style) Object.assign(d.style, style);
    if (html != null) d.innerHTML = html; parent.appendChild(d); return d;
  };
  const px = v => `${v}px`;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const noDot = s => String(s).replace(/\.(?=\s|$)/g, '');           // no full stops in on-screen text

  // a card with the halftone shadow; returns { el (animated wrapper), body (inside the card) }
  function card(parent, x, y, w, h, style) {
    const el = div(parent, 'el cardw', { left: px(x), top: px(y), width: px(w), height: px(h) });
    div(el, 'sh'); const body = div(el, 'card', style || {});
    return { el, body };
  }
  function svg(parent, w, h, style) {
    const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    s.setAttribute('width', w); s.setAttribute('height', h); s.setAttribute('viewBox', `0 0 ${w} ${h}`);
    Object.assign(s.style, { position: 'absolute', overflow: 'visible', ...(style || {}) }); parent.appendChild(s); return s;
  }
  function path(s, d, attrs) {
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path'); p.setAttribute('d', d);
    for (const k in attrs) p.setAttribute(k, attrs[k]); s.appendChild(p); return p;
  }

  // ---------------------------------------------------------------- animation model
  // every animated element carries a list of moves; its state at t comes from the last move that has started
  const items = [];
  function anim(el, moves, base) {
    const it = { el, moves: moves.filter(m => m && m.at != null).sort((a, b) => a.at - b.at), base: Object.assign({ x: 0, y: 0, r: 0, s: 1 }, base || {}) };
    items.push(it); return it;
  }
  function stateAt(it, t) {
    let st = null;
    for (const m of it.moves) {
      if (t < m.at) break;
      const q = (d) => span(t, m.at, m.at + d);
      switch (m.kind) {
        case 'pop': { const k = E.backOut(q(0.34)); st = { o: clamp(q(0.12) * 1, 0, 1), s: 0.55 + 0.45 * k, y: 0, r: 0 }; break; }
        case 'rise': { const k = E.p3(q(0.4)); st = { o: E.p3(q(0.25)), s: 1, y: 70 * (1 - k), r: 0 }; break; }
        case 'slam': { const k = E.p4(q(0.24)); st = { o: q(0.05), s: 1.22 - 0.22 * k, y: 0, r: 0 }; break; }
        case 'stamp': { const k = E.p4(q(0.2)); st = { o: q(0.04), s: 1.75 - 0.75 * k, y: 0, r: -18 + 12 * k }; break; }
        case 'spin': { const k = E.backOut(q(0.42), 1.6); st = { o: q(0.1), s: 0.4 + 0.6 * k, y: 0, r: -200 * (1 - E.p3(q(0.42))) }; break; }
        case 'fade': { st = { o: E.io(q(m.dur || 0.3)), s: 1, y: 0, r: 0 }; break; }
        case 'show': { st = { o: 1, s: 1, y: 0, r: 0 }; break; }
        case 'exit': { if (!st) break; const k = E.in2(q(0.22)); st = { ...st }; st.o = (st.o ?? 1) * (1 - k); st.y = (st.y || 0) - 50 * k; if (k >= 1) st.o = 0; break; }
        case 'hide': { st = { o: 0, s: 1, y: 0, r: 0 }; break; }
        default: break;
      }
      // a move that ended earlier settles fully (pop/rise/slam end at their final pose)
      if (m.kind !== 'exit' && m.kind !== 'hide' && t >= m.at + 0.5) st = { o: 1, s: 1, y: 0, r: 0 };
    }
    return st;
  }
  function apply(it, t) {
    const st = stateAt(it, t), b = it.base;
    if (!st || st.o <= 0.001) { it.el.style.opacity = 0; it.el.style.visibility = 'hidden'; return; }
    it.el.style.visibility = 'visible'; it.el.style.opacity = st.o.toFixed(3);
    it.el.style.transform = `translate(${(b.x).toFixed(1)}px, ${(b.y + st.y).toFixed(1)}px) rotate(${(b.r + st.r).toFixed(2)}deg) scale(${(b.s * st.s).toFixed(4)})`;
  }
  const hooks = [];   // extra per-frame functions (counters, typing, drawing strokes, demos)

  // ---------------------------------------------------------------- paper with fine noise grain
  function paper(root) {
    const c = document.createElement('canvas'); c.width = 256; c.height = 256;
    const g = c.getContext('2d'), img = g.createImageData(256, 256), r = rng(11);
    for (let i = 0; i < img.data.length; i += 4) { const v = 120 + r() * 135; img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 18; }
    g.putImageData(img, 0, 0);
    div(root, 'layer', { backgroundColor: C.paper, backgroundImage: `url(${c.toDataURL()})`, backgroundSize: '256px 256px' });
  }

  // ---------------------------------------------------------------- captions: each word on its frame, grey -> ink
  function captions(root, plan) {
    const box = div(root, 'cap');
    const chunks = plan.chunks || [];
    const built = chunks.map(ch => {
      const wrap = div(box, '', { position: 'absolute', left: 0, top: 0, width: '850px', opacity: 0 });
      const spans = ch.words.map((w, j) => {
        const isKey = j === ch.key;
        const s = document.createElement('span');
        s.textContent = noDot(w.w) + ' ';
        if (isKey) { s.className = 'serif'; s.style.fontSize = '1.16em'; s.style.color = C.red; s.style.letterSpacing = '0'; }
        wrap.appendChild(s);
        return { s, w, isKey };
      });
      return { ch, wrap, spans };
    });
    hooks.push(t => {
      for (const b of built) {
        const on = t >= b.ch.start && t < b.ch.end;
        b.wrap.style.opacity = on ? 1 : 0;
        if (!on) continue;
        for (const x of b.spans) {
          if (t < x.w.start) { x.s.style.opacity = 0; continue; }
          x.s.style.opacity = 1;
          if (!x.isKey) { const k = span(t, x.w.start, x.w.start + 0.2); x.s.style.color = k >= 1 ? C.ink : mix(C.light, C.ink, k); }
        }
      }
    });
  }
  function mix(a, b, k) {
    const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
    const ch = sh => Math.round(((pa >> sh) & 255) * (1 - k) + ((pb >> sh) & 255) * k);
    return `rgb(${ch(16)},${ch(8)},${ch(0)})`;
  }

  // ---------------------------------------------------------------- header labels at y 132
  function header(root, scenes) {
    const L = div(root, 'mono', { position: 'absolute', left: '120px', top: '132px', fontSize: '25px', color: C.grey, whiteSpace: 'nowrap' });
    const R = div(root, 'mono', { position: 'absolute', right: '120px', top: '132px', fontSize: '25px', color: C.grey, whiteSpace: 'nowrap', textAlign: 'right' });
    hooks.push(t => {
      let cur = null; for (const s of scenes) if (t >= s.from) cur = s;
      if (!cur) return;
      if (L._k !== cur) {
        L._k = cur;
        L.textContent = `// ${String(cur.n).padStart(2, '0')} · ${noDot(cur.name || '')}`;
        R.innerHTML = cur.stat ? `<b style="color:${C.red}">${esc(cur.stat.num)}</b> ${esc(noDot(cur.stat.text || ''))}` : '';
      }
    });
  }

  // ---------------------------------------------------------------- big title with a hand-drawn swash underline
  function title(layer, words, at, y, exitAt) {
    const txt = words.map(noDot), len = txt.join(' ').length;
    const size = Math.round(clamp(840 / Math.max(1, len * 0.47), 96, 176));
    const el = div(layer, 'el anton', { left: '120px', top: px(y), fontSize: px(size), whiteSpace: 'nowrap', transformOrigin: '0% 60%' },
      `<span style="color:${C.ink}">${esc(txt[0] || '')}</span> <span style="color:${C.red}">${esc(txt.slice(1).join(' '))}</span>`);
    anim(el, [{ kind: 'slam', at }, { kind: 'exit', at: exitAt }]);
    // underline: a loose brush stroke that draws in 0.3 s, 0.12 s after the slam
    const w = Math.min(840, len * size * 0.47);
    const ul = svg(layer, w + 40, 60, { left: '112px', top: px(y + size * 0.98) });
    const d = `M 6 34 C ${w * 0.2} 18 ${w * 0.45} 42 ${w * 0.7} 26 S ${w * 0.95} 22 ${w + 20} 30`;
    const p = path(ul, d, { fill: 'none', stroke: C.red, 'stroke-width': 10, 'stroke-linecap': 'round' });
    const L = w * 1.15 + 60; p.setAttribute('stroke-dasharray', L);
    const ulIt = anim(ul, [{ kind: 'show', at: at + 0.12 }, { kind: 'exit', at: exitAt }]);
    hooks.push(t => { p.setAttribute('stroke-dashoffset', (L * (1 - E.p3(span(t, at + 0.12, at + 0.42)))).toFixed(1)); });
    return { el, ul: ulIt, bottom: y + size * 0.98 + 50 };
  }

  // a number that counts up over 1.15 s
  function counter(el, value, at, o) {
    const dec = o.decimals ?? (Math.abs(value) < 10 && value % 1 ? 1 : 0);
    hooks.push(t => {
      const v = value * E.p3(span(t, at, at + 1.15));
      el.textContent = `${o.prefix || ''}${v.toFixed(dec)}${o.suffix || ''}`;
    });
  }
  // a line that types itself in under 0.9 s
  function typer(el, text, at, dur) {
    const n = text.length, d = Math.min(0.9, dur || 0.9);
    hooks.push(t => {
      const k = Math.floor(n * span(t, at, at + d));
      el.innerHTML = esc(text.slice(0, k)) + (t >= at && (k < n || Math.floor(t * 2.5) % 2 === 0) ? `<span style="color:${C.red}">▍</span>` : '');
    });
  }

  // ---------------------------------------------------------------- the hook: problem card struck through, payoff cards
  function hookScene(layer, h, sceneEnd) {
    const P = h.problem || {}, Y = h.payoff || {};
    if (P.title || P.lines) {
      const c = card(layer, 140, 560, 800, 380);
      div(c.body, 'mono', { position: 'absolute', left: '40px', top: '34px', fontSize: '25px', color: C.grey }, esc(noDot(P.label || 'problem')));
      div(c.body, 'anton', { position: 'absolute', left: '40px', top: '86px', fontSize: '88px', width: '720px', lineHeight: '1' }, esc(noDot(P.title || '')));
      (P.lines || []).slice(0, 3).forEach((l, i) => div(c.body, '', { position: 'absolute', left: '40px', top: px(210 + i * 50), fontSize: '36px', color: C.grey, width: '720px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'clip' }, esc(noDot(l))));
      anim(c.el, [{ kind: 'pop', at: P.at ?? 0 }, { kind: 'exit', at: sceneEnd - 0.3 }]);
      if (P.strikeAt != null) {
        const s = svg(layer, 860, 120, { left: '110px', top: '690px' });
        const p = path(s, 'M 10 70 C 220 40 520 80 850 30', { fill: 'none', stroke: C.red, 'stroke-width': 14, 'stroke-linecap': 'round' });
        p.setAttribute('stroke-dasharray', 900);
        anim(s, [{ kind: 'show', at: P.strikeAt }, { kind: 'exit', at: sceneEnd - 0.3 }]);
        hooks.push(t => p.setAttribute('stroke-dashoffset', (900 * (1 - E.p3(span(t, P.strikeAt, P.strikeAt + 0.28)))).toFixed(1)));
      }
    }
    const cards = (Y.cards || []).slice(0, 3);
    cards.forEach((txt, i) => {
      const w = 240, gap = 30, x0 = 540 - (cards.length * w + (cards.length - 1) * gap) / 2 + i * (w + gap);
      const c = card(layer, x0, 1000, w, 130);
      div(c.body, 'anton', { position: 'absolute', inset: '0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '50px', textAlign: 'center', padding: '0 10px' }, esc(noDot(txt)));
      anim(c.el, [{ kind: 'pop', at: (Y.at ?? 1) + i * 0.16 }, { kind: 'exit', at: sceneEnd - 0.3 }]);
      if (Y.ringAt != null && i === (Y.ring ?? cards.length - 1)) {
        const s = svg(layer, w + 80, 210, { left: px(x0 - 40), top: '960px' });
        const p = path(s, `M ${w / 2 + 40} 12 C ${w + 70} 10 ${w + 84} 190 ${w / 2 + 30} 198 C -6 196 -4 20 ${w / 2 + 52} 16`, { fill: 'none', stroke: C.red, 'stroke-width': 8, 'stroke-linecap': 'round' });
        p.setAttribute('stroke-dasharray', 1000);
        anim(s, [{ kind: 'show', at: Y.ringAt }, { kind: 'exit', at: sceneEnd - 0.3 }]);
        hooks.push(t => p.setAttribute('stroke-dashoffset', (1000 * (1 - E.p3(span(t, Y.ringAt, Y.ringAt + 0.4)))).toFixed(1)));
      }
    });
  }

  // ---------------------------------------------------------------- one point
  function pointScene(layer, pt, sceneEnd) {
    const at = pt.at, explain = pt.explainAt ?? (at + 3), out = explain - 0.3;
    const T1 = title(layer, pt.title || ['Point', String(pt.n)], at, 470, out);
    const cy = Math.max(T1.bottom + 30, 720), cardAt = at + 0.3;
    const c = card(layer, 120, cy, 840, 330);
    const num = div(c.body, 'anton', { position: 'absolute', left: '44px', top: '36px', fontSize: '190px', color: C.red, lineHeight: '1' });
    const cd = pt.card || {};
    if (cd.value != null) counter(num, Number(cd.value), cardAt + 0.1, cd); else num.textContent = noDot(cd.big || '');
    div(c.body, '', { position: 'absolute', left: '48px', top: '236px', width: '740px', fontSize: '38px', color: C.grey, lineHeight: '1.15' }, esc(noDot(cd.caption || '')));
    anim(c.el, [{ kind: 'rise', at: cardAt }, { kind: 'exit', at: out }]);
    const badge = div(layer, 'el badge', { left: px(860), top: px(cy - 50) }, `#${pt.n}`);
    anim(badge, [{ kind: 'spin', at: cardAt + 0.6 }, { kind: 'exit', at: out }]);
    if (pt.terminal) {
      const isSearch = pt.terminal.kind === 'search';
      const tb = card(layer, 120, cy + 370, 840, 96, isSearch ? {} : { background: C.ink });
      const tx = div(tb.body, 'mono', { position: 'absolute', left: '34px', top: '24px', fontSize: '34px', color: isSearch ? C.ink : C.paper, whiteSpace: 'nowrap' });
      const pre = div(tb.body, 'mono', { position: 'absolute', left: '34px', top: '24px', fontSize: '34px', color: C.red }, isSearch ? '⌕' : '&gt;');
      tx.style.left = '78px'; void pre;
      typer(tx, noDot(pt.terminal.text || ''), cardAt + 0.75, 0.85);
      anim(tb.el, [{ kind: 'rise', at: cardAt + 0.65 }, { kind: 'exit', at: out }]);
    }
    if (pt.demo) demo(layer, pt.demo, explain, sceneEnd);
    if (pt.stamp && pt.stamp.text) {
      const st = div(layer, 'el stamp', { left: px(pt.stamp.x ?? 600), top: px(pt.stamp.y ?? 470), transformOrigin: '50% 50%' }, esc(noDot(pt.stamp.text)));
      anim(st, [{ kind: 'stamp', at: pt.stamp.at ?? explain + 0.8 }, { kind: 'exit', at: sceneEnd - 0.3 }], { r: 0 });
    }
  }

  // ---------------------------------------------------------------- demo animations: act out the explanation
  function demo(layer, d, at, end) {
    const kind = d.kind || 'bars', top = 560, ex = end - 0.3;
    const spread = (i, n) => at + 0.15 + i * Math.min(0.55, Math.max(0.25, (end - at - 1.2) / Math.max(1, n)));
    if (kind === 'bars') {
      const items = (d.items || []).slice(0, 5), max = Math.max(1, ...items.map(x => +x[1] || 0));
      items.forEach((it, i) => {
        const y = top + i * 150, c = card(layer, 120, y, 840, 120), on = spread(i, items.length), hi = i === (d.highlight ?? items.length - 1);
        div(c.body, '', { position: 'absolute', left: '32px', top: '14px', fontSize: '34px', fontWeight: '600' }, esc(noDot(it[0])));
        const bar = div(c.body, '', { position: 'absolute', left: '32px', top: '66px', height: '30px', width: '0px', background: hi ? C.red : C.ink, borderRadius: '6px' });
        const v = div(c.body, 'anton', { position: 'absolute', right: '30px', top: '14px', fontSize: '64px', color: hi ? C.red : C.ink });
        counter(v, +it[1] || 0, on + 0.1, { suffix: d.suffix || '', prefix: d.prefix || '' });
        hooks.push(t => { bar.style.width = px(Math.round(600 * ((+it[1] || 0) / max) * E.p3(span(t, on + 0.1, on + 1.0)))); });
        anim(c.el, [{ kind: 'rise', at: on }, { kind: 'exit', at: ex }]);
      });
    } else if (kind === 'compare') {
      const [a, b] = d.items || [['Before', ''], ['After', '']];
      [[a, 120, false], [b, 560, true]].forEach(([it, x, good], i) => {
        const c = card(layer, x, top + 40, 400, 520), on = at + 0.15 + i * 0.5;
        div(c.body, 'mono', { position: 'absolute', left: '30px', top: '26px', fontSize: '25px', color: C.grey }, good ? '// with it' : '// without');
        div(c.body, 'anton', { position: 'absolute', left: '30px', top: '80px', fontSize: '72px', width: '340px', color: good ? C.red : C.ink }, esc(noDot(it[0] || '')));
        div(c.body, '', { position: 'absolute', left: '30px', top: '270px', fontSize: '34px', width: '340px', color: C.grey, lineHeight: '1.2' }, esc(noDot(it[1] || '')));
        const mark = div(c.body, 'anton', { position: 'absolute', right: '28px', bottom: '14px', fontSize: '120px', color: good ? C.red : C.ink }, good ? '✓' : '✕');
        anim(mark, [{ kind: 'stamp', at: on + 0.5 }]);
        anim(c.el, [{ kind: 'rise', at: on }, { kind: 'exit', at: ex }]);
      });
    } else if (kind === 'checklist') {
      const items = (d.items || []).slice(0, 5);
      items.forEach((txt, i) => {
        const on = spread(i, items.length), c = card(layer, 120, top + i * 140, 840, 112);
        div(c.body, '', { position: 'absolute', left: '110px', top: '30px', fontSize: '42px', fontWeight: '600', whiteSpace: 'nowrap' }, esc(noDot(txt)));
        const box = div(c.body, '', { position: 'absolute', left: '30px', top: '28px', width: '54px', height: '54px', border: `4px solid ${C.ink}`, borderRadius: '10px' });
        const tick = div(box, 'anton', { position: 'absolute', left: '6px', top: '-14px', fontSize: '64px', color: C.red }, '✓');
        anim(tick, [{ kind: 'pop', at: on + 0.35 }]);
        anim(c.el, [{ kind: 'rise', at: on }, { kind: 'exit', at: ex }]);
      });
    } else if (kind === 'chat') {
      const msgs = (d.items || []).slice(0, 4);
      let y = top;
      msgs.forEach((m, i) => {
        const me = i % 2 === 0, on = spread(i, msgs.length), txt = noDot(m), lines = Math.ceil(txt.length / 26), h = 60 + lines * 48;
        const c = card(layer, me ? 300 : 120, y, 660, h, me ? { background: C.ink } : {});
        const tx = div(c.body, '', { position: 'absolute', left: '32px', top: '26px', width: '596px', fontSize: '40px', lineHeight: '1.2', color: me ? C.paper : C.ink });
        if (me) tx.textContent = txt; else typer(tx, txt, on + 0.25, 0.9);
        anim(c.el, [{ kind: 'pop', at: on }, { kind: 'exit', at: ex }]);
        y += h + 34;
      });
    } else if (kind === 'flow') {
      const items = (d.items || []).slice(0, 4), n = items.length;
      items.forEach((txt, i) => {
        const on = spread(i, n), y = top + i * 175;
        const c = card(layer, 220, y, 640, 120);
        div(c.body, 'anton', { position: 'absolute', inset: '0', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '54px' }, esc(noDot(txt)));
        anim(c.el, [{ kind: 'pop', at: on }, { kind: 'exit', at: ex }]);
        if (i < n - 1) {
          const s = svg(layer, 60, 60, { left: '510px', top: px(y + 122) });
          const p = path(s, 'M 30 4 L 30 44 M 14 30 L 30 48 L 46 30', { fill: 'none', stroke: C.red, 'stroke-width': 8, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' });
          p.setAttribute('stroke-dasharray', 120);
          anim(s, [{ kind: 'show', at: on + 0.3 }, { kind: 'exit', at: ex }]);
          hooks.push(t => p.setAttribute('stroke-dashoffset', (120 * (1 - E.p3(span(t, on + 0.3, on + 0.6)))).toFixed(1)));
        }
      });
    } else if (kind === 'search') {
      const c = card(layer, 120, top, 840, 110);
      const tx = div(c.body, 'mono', { position: 'absolute', left: '80px', top: '30px', fontSize: '38px', whiteSpace: 'nowrap' });
      div(c.body, 'mono', { position: 'absolute', left: '30px', top: '28px', fontSize: '40px', color: C.red }, '⌕');
      typer(tx, noDot(d.query || ''), at + 0.2, 0.85);
      anim(c.el, [{ kind: 'rise', at }, { kind: 'exit', at: ex }]);
      (d.items || []).slice(0, 3).forEach((r, i) => {
        const on = at + 1.15 + i * 0.16, rc = card(layer, 120, top + 150 + i * 150, 840, 120);
        div(rc.body, '', { position: 'absolute', left: '32px', top: '18px', fontSize: '38px', fontWeight: '600', color: i === 0 ? C.red : C.ink, whiteSpace: 'nowrap' }, esc(noDot(r)));
        div(rc.body, '', { position: 'absolute', left: '32px', top: '72px', width: px(300 + 140 * ((i * 37) % 3)), height: '14px', background: C.light, borderRadius: '7px' });
        anim(rc.el, [{ kind: 'pop', at: on }, { kind: 'exit', at: ex }]);
      });
    } else if (kind === 'number') {
      const c = card(layer, 120, top, 840, 520);
      const num = div(c.body, 'anton', { position: 'absolute', left: '0', right: '0', top: '60px', textAlign: 'center', fontSize: '260px', color: C.red });
      counter(num, +d.value || 0, at + 0.2, d);
      div(c.body, '', { position: 'absolute', left: '50px', right: '50px', top: '360px', textAlign: 'center', fontSize: '44px', color: C.ink, fontWeight: '600' }, esc(noDot(d.caption || '')));
      anim(c.el, [{ kind: 'rise', at }, { kind: 'exit', at: ex }]);
    }
  }

  // ---------------------------------------------------------------- closing line card (mirrors the opening for the loop)
  function closeScene(layer, cl, end) {
    if (!cl) return;
    const c = card(layer, 140, 560, 800, 380);
    div(c.body, 'mono', { position: 'absolute', left: '40px', top: '34px', fontSize: '25px', color: C.grey }, esc(noDot(cl.label || 'remember')));
    div(c.body, 'anton', { position: 'absolute', left: '40px', top: '86px', fontSize: '96px', width: '720px', lineHeight: '1' },
      (cl.words || []).map((w, i) => `<span style="color:${i % 2 ? C.red : C.ink}">${esc(noDot(w))}</span>`).join(' '));
    anim(c.el, [{ kind: 'pop', at: cl.at }]);
    if (cl.stamp) {
      const st = div(layer, 'el stamp', { left: '640px', top: '520px' }, esc(noDot(cl.stamp)));
      anim(st, [{ kind: 'stamp', at: cl.stampAt ?? cl.at + 0.6 }, { kind: 'exit', at: end - 0.35 }]);
    }
  }

  // ---------------------------------------------------------------- halftone dot wipe (13 x 23 dots, 0.9 s)
  function wipes(root, times) {
    const s = svg(root, W, H, { left: '0', top: '0' }), dots = [];
    const cx = W / 2, cy = H / 2, maxD = Math.hypot(cx, cy);
    for (let i = 0; i < 13; i++) for (let j = 0; j < 23; j++) {
      const x = (i + 0.5) * W / 13, y = (j + 0.5) * H / 23;
      const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('cx', x.toFixed(1)); c.setAttribute('cy', y.toFixed(1)); c.setAttribute('r', 0); c.setAttribute('fill', C.ink);
      s.appendChild(c); dots.push({ c, d: Math.hypot(x - cx, y - cy) / maxD });
    }
    hooks.push(t => {
      let w = null; for (const p of times) if (t >= p - 0.45 && t <= p + 0.45) w = p;
      s.style.display = w == null ? 'none' : '';
      if (w == null) return;
      const u = (t - (w - 0.45)) / 0.9;                    // 0..1, peak (full cover) at 0.5
      for (const d of dots) {
        const grow = clamp((u - d.d * 0.3) / 0.25, 0, 1), shrink = clamp((u - 0.5 - d.d * 0.3) / 0.2, 0, 1);
        d.c.setAttribute('r', (62 * E.io(grow) * (1 - E.io(shrink))).toFixed(1));
      }
    });
  }

  // ---------------------------------------------------------------- run
  // plan: { duration, chunks, hook, points, close, presenter: { params, mouth, seed }, nods, palms }
  // Scenes switch at each wipe's peak: hook -> point 1 -> ... -> close.
  function run(host, plan) {
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const root = div(host, ''); root.id = 'ex';
    paper(root);
    const scenesL = div(root, 'layer'), presL = div(root, 'layer'), capL = div(root, 'layer');
    const pts = plan.points || [];
    // each wipe starts 0.3 s before its scene's first line and peaks (full cover, the scene swaps) 0.15 s after it
    const wipeAt = pts.map(p => (p.from ?? p.at) + 0.15);
    if (plan.close && pts.length) wipeAt.push((plan.close.from ?? plan.close.at) + 0.15);
    const bounds = [0, ...wipeAt, plan.duration + 1];
    const sceneLayer = i => {
      const l = div(scenesL, 'layer'), a = bounds[i], b = bounds[i + 1];
      hooks.push(t => { l.style.display = t >= a && t < b ? '' : 'none'; }); return l;
    };
    hookScene(sceneLayer(0), plan.hook || {}, bounds[1]);
    pts.forEach((p, i) => pointScene(sceneLayer(i + 1), p, bounds[i + 2]));
    if (plan.close) closeScene(sceneLayer(pts.length + 1), plan.close, plan.duration);
    header(root, [{ from: 0, n: 0, name: plan.hook?.label || 'intro', stat: plan.hook?.stat },
      ...pts.map((p, i) => ({ from: bounds[i + 1], n: p.n || i + 1, name: p.name, stat: p.stat })),
      ...(plan.close ? [{ from: bounds[pts.length + 1], n: pts.length + 1, name: plan.close.name || 'recap', stat: plan.close.stat }] : [])]);
    // presenter bottom right, cropped at the chest
    const ph = div(presL, '', { position: 'absolute', left: '430px', top: '1170px', width: '650px', height: '770px' });
    const pr = plan.presenter || {};
    const rig = window.EXP.rig(ph, pr.params || window.EXP.random(pr.seed || 3), {
      mouth: pr.mouth || '', seed: pr.seed || 7, duration: plan.duration, fps: 30,
      nods: plan.nods || [], points: pts.map(p => p.at - 0.1), palms: plan.palms || pts.filter((_, i) => i % 2 === 1).map(p => p.explainAt),
    });
    hooks.push(t => rig.render(t));
    captions(capL, plan);
    wipes(root, wipeAt);
    return t => { for (const h of hooks) h(t); for (const it of items) apply(it, t); };
  }

  window.EX = { run, C };
})();
