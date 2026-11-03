/* Recipe kit: a 1080x1920 recipe reel, from an empty glass (or pan) to the finished drink (or dish). Each ingredient
   goes in with its measurement on screen. Everything is drawn in SVG as a pure function of t (seconds) from one plan:

   plan = { duration, name, tagline, glass: 'highball' | 'rocks' | 'coupe' | 'martini', bg: ['#hex', '#hex'],
            final: '#hex' (the colour once mixed), captions: [[t, 'word', tEnd], ...],
            steps: [{ at, end, kind, title, amount, unit, ml, name, color, fill, ... }] }
   kinds: add (solids: items 'mint' | 'lime' | 'berries' | 'sugar'), muddle, pour (a bottle pours `fill` of the
   glass in `color`), ice (cubes: 'cubes' | 'crushed'), top (soda: bubbles), stir, shake (shaker, then strain),
   garnish (items: 'mint' | 'lime_wheel' | 'orange_peel' | 'cherry' | 'olive' | 'umbrella').

   Dishes set plan.vessel: 'pan' | 'pot' | 'bowl' (instead of glass) and use these kinds:
   add (items: [{ shape, color, count? }], shape 'dice' | 'slice' | 'ring' | 'round' | 'strip' | 'leaf' | 'mince' |
   'crumble' | 'grain' | 'chunk'; fill raises the contents; heat: true lights the burner; spoon: true stirs it in),
   pour (fill, color, opacity, container 'bottle' | 'bowl'), sprinkle (color: a spoonful of spice dust), crack
   (count eggs), stir / whisk (blend: true mixes everything to plan.final), cook (a time skip: amount + unit 'min';
   color deepens the sauce, brown 0..1 browns what is in, bubbles: false for a dry pan), garnish (items, on top). */
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const W = 1080, H = 1920;
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const span = (t, a, b) => clamp((t - a) / Math.max(1e-6, b - a));
  const lerp = (a, b, s) => a + (b - a) * s;
  const E = {
    out: s => 1 - (1 - clamp(s)) ** 3, io: s => { s = clamp(s); return s < 0.5 ? 4 * s ** 3 : 1 - (-2 * s + 2) ** 3 / 2; },
    back: (s, k = 1.8) => { s = clamp(s); return 1 + (k + 1) * (s - 1) ** 3 + k * (s - 1) ** 2; }, in: s => clamp(s) ** 2,
  };
  function rng(seed) { let s = (seed >>> 0) || 1; return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; }
  const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs || {}) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
  const set = (e, attrs) => { for (const k in attrs) e.setAttribute(k, attrs[k]); };
  const hooks = [];
  const mixHex = (a, b, k) => {
    const pa = parseInt(a.slice(1), 16), pb = parseInt(b.slice(1), 16);
    const c = sh => Math.round(((pa >> sh) & 255) * (1 - k) + ((pb >> sh) & 255) * k);
    return '#' + [c(16), c(8), c(0)].map(v => v.toString(16).padStart(2, '0')).join('');
  };

  // ---------------------------------------------------------------- glasses: interior polygon (top-left, top-right,
  // bottom-right, bottom-left), the rim y and the bottom y; the liquid fills between bottom and rim
  const GLASSES = {
    highball: { inner: [[352, 820], [728, 820], [708, 1500], [372, 1500]], base: 48, rim: 820, bottom: 1500 },
    rocks: { inner: [[320, 1080], [760, 1080], [734, 1500], [346, 1500]], base: 62, rim: 1080, bottom: 1500 },
    coupe: { bowl: true, cx: 540, rim: 1010, bottom: 1250, rx: 290, stem: [1250, 1550], foot: 160 },
    martini: { cone: true, cx: 540, rim: 950, bottom: 1310, rx: 310, stem: [1310, 1550], foot: 160 },
  };
  function glassGeom(g) {
    if (g.inner) {
      const [[x0, y0], [x1], [x2, y2], [x3]] = g.inner;
      return { top: y0, bottom: y2, widthAt: y => { const s = (y - y0) / (y2 - y0); return [lerp(x0, x3, s), lerp(x1, x2, s)]; } };
    }
    if (g.cone) return { top: g.rim, bottom: g.bottom, widthAt: y => { const s = (y - g.rim) / (g.bottom - g.rim); const hw = g.rx * (1 - s); return [g.cx - hw, g.cx + hw]; } };
    return { top: g.rim, bottom: g.bottom, widthAt: y => { const s = clamp((y - g.rim) / (g.bottom - g.rim)); const hw = g.rx * Math.sqrt(Math.max(0, 1 - s * s)); return [g.cx - hw, g.cx + hw]; } };
  }
  function glassPath(G, kind) {
    const g = GLASSES[kind];
    if (g.inner) { const p = g.inner; return `M ${p[0][0]} ${p[0][1]} L ${p[3][0]} ${p[3][1]} L ${p[2][0]} ${p[2][1]} L ${p[1][0]} ${p[1][1]}`; }
    const pts = []; for (let y = G.top; y <= G.bottom + 0.01; y += 6) pts.push([y, G.widthAt(y)]);
    return 'M ' + pts.map(([y, w]) => `${w[0].toFixed(1)} ${y.toFixed(1)}`).join(' L ') + ' L ' + pts.slice().reverse().map(([y, w]) => `${w[1].toFixed(1)} ${y.toFixed(1)}`).join(' L ');
  }

  // ---------------------------------------------------------------- drinks: a glass seen from the side
  function drinkScene(svg, defs, plan, steps) {
    // soft spotlight + floor
    const kind = plan.glass || 'highball', g = GLASSES[kind], G = glassGeom(g);
    el('ellipse', { cx: 540, cy: g.stem ? g.stem[1] + 6 : g.bottom + g.base, rx: 380, ry: 46, fill: 'rgba(0,0,0,0.35)' }, svg);
    const clip = el('clipPath', { id: 'gclip' }, defs);
    el('path', { d: glassPath(G, kind) + ' Z' }, clip);
    // ---- layers: back of glass, liquid, solids, ice, front of glass
    const back = el('g', {}, svg);
    el('path', { d: glassPath(G, kind) + ' Z', fill: 'rgba(255,255,255,0.05)' }, back);
    const liquidG = el('g', { 'clip-path': 'url(#gclip)' }, svg);
    const solidsG = el('g', { 'clip-path': 'url(#gclip)' }, svg);
    const iceG = el('g', { 'clip-path': 'url(#gclip)' }, svg);
    const fxG = el('g', {}, svg);
    const front = el('g', {}, svg);
    el('path', { d: glassPath(G, kind), fill: 'none', stroke: 'rgba(255,255,255,0.75)', 'stroke-width': 6, 'stroke-linejoin': 'round' }, front);
    { const [xl, xr] = G.widthAt(G.top); el('ellipse', { cx: (xl + xr) / 2, cy: G.top, rx: (xr - xl) / 2, ry: 16, fill: 'none', stroke: 'rgba(255,255,255,0.6)', 'stroke-width': 4 }, front); }
    // highlights on the glass
    const hl = G.widthAt(G.top + 40)[0] + 26;
    el('path', { d: `M ${hl} ${G.top + 60} L ${G.widthAt(G.bottom - 60)[0] + 26} ${G.bottom - 80}`, stroke: 'rgba(255,255,255,0.35)', 'stroke-width': 12, 'stroke-linecap': 'round' }, front);
    if (g.inner) el('rect', { x: g.inner[3][0] - 6, y: g.bottom, width: g.inner[2][0] - g.inner[3][0] + 12, height: g.base, rx: 10, fill: 'rgba(255,255,255,0.22)', stroke: 'rgba(255,255,255,0.6)', 'stroke-width': 4 }, front);
    if (g.stem) { el('rect', { x: 530, y: g.stem[0], width: 20, height: g.stem[1] - g.stem[0], fill: 'rgba(255,255,255,0.5)' }, front); el('ellipse', { cx: 540, cy: g.stem[1], rx: g.foot, ry: 18, fill: 'rgba(255,255,255,0.35)', stroke: 'rgba(255,255,255,0.6)', 'stroke-width': 4 }, front); }

    // ---- liquid model: layers added by pours, blended by stir/shake
    const cap = G.bottom - G.top - 24;                            // usable height
    const levelAt = t => {
      let lv = 0;
      for (const s of steps) if ((s.kind === 'pour' || s.kind === 'top' || s.kind === 'shake') && s.fill) lv += s.fill * E.io(span(t, s.at + 0.6, s.at + 0.6 + (s.pourDur || 1.6)));
      return clamp(lv, 0, 0.96);
    };
    const layerRects = steps.filter(s => (s.kind === 'pour' || s.kind === 'top' || s.kind === 'shake') && s.fill).map(s => ({ s, r: el('rect', { x: 0, width: W, fill: s.color || '#ffffff', opacity: s.opacity || 0.9 }, liquidG) }));
    const mixRect = el('rect', { x: 0, width: W, fill: plan.final || '#C9E7A1' }, liquidG);
    const surf = el('ellipse', { rx: 10, ry: 10, fill: 'rgba(255,255,255,0.28)' }, liquidG);
    const blendT = steps.find(s => s.kind === 'stir' || s.kind === 'shake');
    hooks.push(t => {
      let acc = 0;
      for (const { s, r } of layerRects) {
        const k = s.fill * E.io(span(t, s.at + 0.6, s.at + 0.6 + (s.pourDur || 1.6)));
        const y1 = G.bottom - acc * cap, y0 = G.bottom - (acc + k) * cap;
        set(r, { y: y0.toFixed(1), height: Math.max(0, y1 - y0).toFixed(1) });
        acc += k;
      }
      const lv = clamp(acc, 0, 0.96), top = G.bottom - lv * cap;
      const blend = blendT ? E.io(span(t, blendT.at + 0.4, blendT.at + 1.6)) : 0;
      set(mixRect, { y: top.toFixed(1), height: (G.bottom - top + 2).toFixed(1), opacity: blend.toFixed(3) });
      const [xl, xr] = G.widthAt(top);
      const wob = 6 * Math.sin(t * 5);
      set(surf, { cx: ((xl + xr) / 2).toFixed(1), cy: top.toFixed(1), rx: ((xr - xl) / 2).toFixed(1), ry: (lv > 0.01 ? 14 + wob * 0.4 : 0).toFixed(1) });
    });

    // ---- solids: mint leaves, lime wedges, berries, sugar
    const r = rng(7);
    const leaf = (parent, x, y, s, rot, col = '#3FAE5A') => {
      const gg = el('g', { transform: `translate(${x} ${y}) rotate(${rot}) scale(${s})` }, parent);
      el('path', { d: 'M 0 -38 C 26 -22 26 22 0 38 C -26 22 -26 -22 0 -38 Z', fill: col }, gg);
      el('path', { d: 'M 0 -34 L 0 34', stroke: 'rgba(0,0,0,0.25)', 'stroke-width': 3 }, gg);
      return gg;
    };
    const wedge = (parent, x, y, s, rot) => {
      const gg = el('g', { transform: `translate(${x} ${y}) rotate(${rot}) scale(${s})` }, parent);
      el('path', { d: 'M -44 0 A 44 44 0 0 1 44 0 Z', fill: '#7CC242' }, gg);
      el('path', { d: 'M -36 -2 A 36 36 0 0 1 36 -2 Z', fill: '#D7EC8A' }, gg);
      for (let i = 1; i < 5; i++) { const a = Math.PI * i / 5; el('path', { d: `M 0 -2 L ${-36 * Math.cos(a)} ${-36 * Math.sin(a) - 2}`, stroke: '#9CCF55', 'stroke-width': 3 }, gg); }
      return gg;
    };
    const solids = [];
    for (const s of steps.filter(s => s.kind === 'add')) {
      for (const it of s.items || []) {
        const n = it === 'mint' ? 9 : it === 'lime' ? 4 : it === 'berries' ? 7 : 12;
        for (let i = 0; i < n; i++) {
          const yb = G.bottom - 30 - r() * 90, [xl, xr] = G.widthAt(yb), x = lerp(xl + 40, xr - 40, r());
          const node = it === 'mint' ? leaf(solidsG, 0, 0, 0.9 + r() * 0.4, r() * 360)
            : it === 'lime' ? wedge(solidsG, 0, 0, 0.9 + r() * 0.2, r() * 60 - 30)
              : it === 'berries' ? (() => { const c = el('circle', { r: 18 + r() * 6, fill: ['#B3122E', '#5B2A86', '#D2384D'][i % 3] }, solidsG); return c; })()
                : el('rect', { width: 16, height: 16, rx: 3, fill: '#F7F2E6' }, solidsG);
          const delay = s.at + 0.3 + i * 0.07, rot = r() * 360;
          solids.push({ node, x, yb, delay, rot, kind: it });
        }
      }
    }
    const muddle = steps.find(s => s.kind === 'muddle');
    hooks.push(t => {
      const crush = muddle ? E.io(span(t, muddle.at + 0.4, muddle.at + (muddle.end - muddle.at) - 0.2)) : 0;
      for (const so of solids) {
        if (t < so.delay) { so.node.setAttribute('visibility', 'hidden'); continue; }
        so.node.setAttribute('visibility', 'visible');
        const q = span(t, so.delay, so.delay + 0.55), y = lerp(G.top - 300, so.yb, E.in(q)) + (q >= 1 ? 6 * Math.sin((t - so.delay) * 3) * Math.exp(-(t - so.delay - 0.55) * 2) : 0);
        const sc = 1 - 0.25 * crush;
        so.node.setAttribute('transform', `translate(${so.x.toFixed(1)} ${(y + 18 * crush).toFixed(1)}) rotate(${(so.rot + 40 * q).toFixed(1)}) scale(${(so.kind === 'mint' ? sc : 1).toFixed(3)} ${(sc * (so.kind === 'mint' ? 0.8 : 1)).toFixed(3)})`);
      }
    });
    // muddler
    if (muddle) {
      const m = el('g', {}, fxG);
      el('rect', { x: -22, y: -620, width: 44, height: 620, rx: 18, fill: '#C68A4E' }, m);
      el('rect', { x: -26, y: -40, width: 52, height: 40, rx: 12, fill: '#A86E38' }, m);
      hooks.push(t => {
        const on = t >= muddle.at && t <= muddle.end;
        m.setAttribute('visibility', on ? 'visible' : 'hidden'); if (!on) return;
        const inQ = E.out(span(t, muddle.at, muddle.at + 0.4)), outQ = E.in(span(t, muddle.end - 0.4, muddle.end));
        const press = Math.max(0, Math.sin((t - muddle.at) * Math.PI * 2.6)) * 70;
        const y = G.bottom - 40 - press - (1 - inQ) * 700 - outQ * 700;
        m.setAttribute('transform', `translate(540 ${y.toFixed(1)}) rotate(${(4 * Math.sin(t * 6)).toFixed(2)})`);
      });
    }
    // ---- ice: cubes or crushed, dropping in with a bounce and floating with the level
    for (const s of steps.filter(s => s.kind === 'ice')) {
      const crushed = s.style === 'crushed', n = crushed ? 46 : 6, rr = rng(31), cubes = [];
      for (let i = 0; i < n; i++) {
        const size = crushed ? 30 + rr() * 26 : 104;
        const node = el('g', {}, iceG);
        el('rect', { x: -size / 2, y: -size / 2, width: size, height: size, rx: size * 0.22, fill: 'rgba(235,248,255,0.55)', stroke: 'rgba(255,255,255,0.85)', 'stroke-width': 3 }, node);
        el('path', { d: `M ${-size * 0.28} ${-size * 0.3} L ${size * 0.1} ${-size * 0.3}`, stroke: 'rgba(255,255,255,0.9)', 'stroke-width': 5, 'stroke-linecap': 'round' }, node);
        const row = crushed ? Math.floor(i / 7) : i % 3, col = crushed ? i % 7 : Math.floor(i / 3);
        const yy = G.bottom - (crushed ? 40 + row * 70 : 80 + row * 160) - rr() * 20;
        const [xl, xr] = G.widthAt(yy);
        const x = crushed ? lerp(xl + 30, xr - 30, (col + 0.5 * (row % 2)) / 7) : lerp(xl + 80, xr - 80, col);
        cubes.push({ node, x, y: yy, d: s.at + 0.2 + i * (crushed ? 0.025 : 0.16), rot: rr() * 40 - 20 });
      }
      hooks.push(t => {
        for (const c of cubes) {
          if (t < c.d) { c.node.setAttribute('visibility', 'hidden'); continue; }
          c.node.setAttribute('visibility', 'visible');
          const q = span(t, c.d, c.d + 0.45);
          const y = lerp(G.top - 260, c.y, E.in(q)) - (q >= 1 ? 26 * Math.exp(-(t - c.d - 0.45) * 7) * Math.abs(Math.sin((t - c.d - 0.45) * 12)) : 0);
          c.node.setAttribute('transform', `translate(${c.x.toFixed(1)} ${y.toFixed(1)}) rotate(${(c.rot + (1 - q) * 90).toFixed(1)})`);
        }
      });
    }
    // ---- soda: bubbles rising inside the liquid from the top-up on
    const top = steps.find(s => s.kind === 'top');
    if (top) {
      const rb = rng(55), bubbles = [];
      for (let i = 0; i < 40; i++) bubbles.push({ n: el('circle', { r: 3 + rb() * 5, fill: 'rgba(255,255,255,0.7)' }, liquidG), x: rb(), ph: rb(), sp: 0.4 + rb() * 0.6 });
      hooks.push(t => {
        const lv = levelAt(t), topY = G.bottom - lv * cap;
        for (const b of bubbles) {
          const on = t >= top.at + 0.8; b.n.setAttribute('visibility', on ? 'visible' : 'hidden'); if (!on) continue;
          const u = ((t - top.at) * b.sp + b.ph) % 1, y = lerp(G.bottom - 10, topY + 10, u), [xl, xr] = G.widthAt(y);
          set(b.n, { cx: lerp(xl + 20, xr - 20, b.x).toFixed(1), cy: y.toFixed(1) });
        }
      });
    }
    // ---- pours: a bottle tilts in from the upper right and a stream falls to the surface
    for (const s of steps.filter(s => s.kind === 'pour' || s.kind === 'top')) {
      const b = el('g', {}, fxG);
      const col = s.bottle || (s.kind === 'top' ? '#9ED7E8' : '#E9E3D6');
      el('rect', { x: -70, y: -260, width: 140, height: 300, rx: 34, fill: col, opacity: 0.92 }, b);
      el('rect', { x: -26, y: -360, width: 52, height: 110, rx: 14, fill: col, opacity: 0.92 }, b);
      el('rect', { x: -70, y: -170, width: 140, height: 120, fill: s.color || '#ffffff', opacity: 0.85 }, b);
      el('rect', { x: -30, y: -376, width: 60, height: 22, rx: 6, fill: '#2B2B2B' }, b);
      const stream = el('path', { fill: 'none', stroke: s.color || '#ffffff', 'stroke-linecap': 'round', opacity: 0.95 }, fxG);
      const pour = s.pourDur || 1.6;
      hooks.push(t => {
        const on = t >= s.at && t <= s.at + pour + 1.2;
        b.setAttribute('visibility', on ? 'visible' : 'hidden'); stream.setAttribute('visibility', 'hidden');
        if (!on) return;
        const inQ = E.out(span(t, s.at, s.at + 0.5)), outQ = E.in(span(t, s.at + pour + 0.6, s.at + pour + 1.1));
        const tilt = -128 * E.io(span(t, s.at + 0.2, s.at + 0.6)) * (1 - E.io(span(t, s.at + pour + 0.5, s.at + pour + 0.8)));
        const bx = lerp(1120, 780, inQ) + outQ * 700, by = lerp(420, G.top - 230, inQ) - outQ * 360;
        b.setAttribute('transform', `translate(${bx.toFixed(1)} ${by.toFixed(1)}) rotate(${tilt.toFixed(1)})`);
        const flowing = t >= s.at + 0.55 && t <= s.at + 0.6 + pour;
        if (flowing) {
          const a = tilt * Math.PI / 180, mx = bx + Math.sin(-a) * 360 * -1, my = by - Math.cos(a) * 360;
          const lv = levelAt(t), sy = G.bottom - lv * cap;
          const w = 16 * Math.min(1, span(t, s.at + 0.55, s.at + 0.75)) * (1 - span(t, s.at + 0.4 + pour, s.at + 0.6 + pour));
          set(stream, { d: `M ${mx.toFixed(1)} ${my.toFixed(1)} C ${(mx - 40).toFixed(1)} ${(my + 60).toFixed(1)}, 560 ${(sy - 200).toFixed(1)}, 548 ${sy.toFixed(1)}`, 'stroke-width': w.toFixed(1), visibility: 'visible' });
        }
      });
    }
    // ---- stir: a bar spoon circling in the glass
    const stir = steps.find(s => s.kind === 'stir');
    if (stir) {
      const sp = el('g', {}, fxG);
      el('rect', { x: -8, y: -820, width: 16, height: 820, rx: 8, fill: '#D9DDE2' }, sp);
      for (let k = 0; k < 14; k++) el('rect', { x: -8, y: -760 + k * 30, width: 16, height: 6, fill: '#AEB4BC' }, sp);
      el('circle', { cx: 0, cy: -830, r: 18, fill: '#D9DDE2' }, sp);
      el('ellipse', { cx: 0, cy: 0, rx: 26, ry: 14, fill: '#D9DDE2' }, sp);
      hooks.push(t => {
        const on = t >= stir.at && t <= stir.end; sp.setAttribute('visibility', on ? 'visible' : 'hidden'); if (!on) return;
        const inQ = E.out(span(t, stir.at, stir.at + 0.35)), outQ = E.in(span(t, stir.end - 0.35, stir.end));
        const ph = (t - stir.at) * Math.PI * 3;
        sp.setAttribute('transform', `translate(${(540 + 70 * Math.sin(ph)).toFixed(1)} ${(G.bottom - 60 - (1 - inQ) * 800 - outQ * 800).toFixed(1)}) rotate(${(10 * Math.cos(ph)).toFixed(1)})`);
      });
    }
    // ---- garnish: pops onto the rim at its time
    const gar = steps.find(s => s.kind === 'garnish');
    if (gar) {
      const items = gar.items || ['mint'];
      const [rl, rrx] = G.widthAt(G.top + 4);
      items.forEach((it, i) => {
        const node = el('g', {}, front);
        if (it === 'mint') { for (let k = 0; k < 5; k++) leaf(node, (k - 2) * 26, -40 - Math.abs(k - 2) * -12, 1.25, (k - 2) * 22, '#47B862'); el('rect', { x: -4, y: -20, width: 8, height: 60, fill: '#2F7A3E' }, node); }
        else if (it === 'lime_wheel' || it === 'orange_peel') {
          const c = it === 'lime_wheel' ? ['#7CC242', '#D7EC8A', '#9CCF55'] : ['#F08A24', '#FFD08A', '#F5A54A'];
          el('circle', { r: 70, fill: c[0] }, node); el('circle', { r: 58, fill: c[1] }, node);
          for (let k = 0; k < 8; k++) { const a = k * Math.PI / 4; el('path', { d: `M 0 0 L ${58 * Math.cos(a)} ${58 * Math.sin(a)}`, stroke: c[2], 'stroke-width': 4 }, node); }
          el('rect', { x: -6, y: 0, width: 12, height: 72, fill: '#00000000' }, node);
        } else if (it === 'cherry') { el('circle', { r: 30, fill: '#B3122E' }, node); el('path', { d: 'M 0 -28 C 10 -70 30 -90 40 -100', stroke: '#4A6B2A', 'stroke-width': 5, fill: 'none' }, node); }
        else if (it === 'olive') { el('ellipse', { rx: 30, ry: 22, fill: '#7E9A3A' }, node); el('circle', { cx: 12, r: 8, fill: '#C0392B' }, node); el('rect', { x: -3, y: -90, width: 6, height: 120, fill: '#C68A4E' }, node); }
        else if (it === 'umbrella') { el('path', { d: 'M -80 0 Q 0 -90 80 0 Z', fill: '#E8508A' }, node); el('rect', { x: -3, y: -10, width: 6, height: 150, fill: '#E8D9B0' }, node); }
        const x = it === 'lime_wheel' || it === 'orange_peel' ? rrx - 10 : it === 'mint' ? (rl + rrx) / 2 - 40 : (rl + rrx) / 2 + 40;
        const y = it === 'lime_wheel' || it === 'orange_peel' ? G.top + 10 : G.top + 24;
        const d = gar.at + 0.35 + i * 0.4;
        hooks.push(t => { const q = span(t, d, d + 0.45); node.setAttribute('visibility', t >= d ? 'visible' : 'hidden'); node.setAttribute('transform', `translate(${x.toFixed(1)} ${(y - (1 - E.out(q)) * 200).toFixed(1)}) scale(${Math.max(0.01, E.back(q)).toFixed(3)})`); });
      });
    }
    // ---- shake: a shaker shakes over the glass, then tips and strains the drink in
    const shake = steps.find(s => s.kind === 'shake');
    if (shake) {
      const sh = el('g', {}, fxG);
      el('path', { d: 'M -110 -300 L 110 -300 L 90 160 L -90 160 Z', fill: '#C9CED6' }, sh);
      el('rect', { x: -70, y: -380, width: 140, height: 90, rx: 20, fill: '#B5BBC4' }, sh);
      el('rect', { x: -110, y: -60, width: 220, height: 14, fill: '#9AA1AB' }, sh);
      const strain = el('path', { fill: 'none', stroke: plan.final || '#E8C27A', 'stroke-linecap': 'round' }, fxG);
      hooks.push(t => {
        const on = t >= shake.at && t <= shake.end; sh.setAttribute('visibility', on ? 'visible' : 'hidden'); strain.setAttribute('visibility', 'hidden'); if (!on) return;
        const tipAt = shake.end - 1.5, inQ = E.out(span(t, shake.at, shake.at + 0.4)), outQ = E.in(span(t, shake.end - 0.35, shake.end));
        const tip = E.io(span(t, tipAt, tipAt + 0.35)), shaking = 1 - tip, k = (t - shake.at) * 26;
        const sx = lerp(540 + 30 * Math.sin(k) * shaking, 900, tip) + (1 - inQ) * 700 + outQ * 500, sy = lerp(G.top - 300 + 40 * Math.cos(k) * shaking, G.top - 220, tip) - outQ * 300;
        const a = lerp(12 * Math.sin(k) * shaking, -110, tip) * (1 - E.io(span(t, shake.end - 0.55, shake.end - 0.3)));
        sh.setAttribute('transform', `translate(${sx.toFixed(1)} ${sy.toFixed(1)}) rotate(${a.toFixed(1)})`);
        if (t > tipAt + 0.3 && t < shake.end - 0.45) {
          const r = a * Math.PI / 180, mx = sx + 380 * Math.sin(r), my = sy - 380 * Math.cos(r), sy2 = G.bottom - levelAt(t) * cap;
          set(strain, { d: `M ${mx.toFixed(1)} ${my.toFixed(1)} C ${(mx - 10).toFixed(1)} ${(my + 60).toFixed(1)}, 548 ${(sy2 - 160).toFixed(1)}, 544 ${sy2.toFixed(1)}`, 'stroke-width': 12, visibility: 'visible' });
        }
      });
    }
  }

  // ---------------------------------------------------------------- dishes: a pan, pot or bowl seen from above at an angle.
  // Contents sit on a surface ellipse that rises from the floor to the rim as the vessel fills.
  const VESSELS = {
    pan: { cy: 1120, RX: 410, RY: 220, D: 70, fk: 0.9, wall: '#2A2B2F', inner: '#3A3C41', floor: '#45474D', rim: '#767981', handle: 'long' },
    pot: { cy: 1030, RX: 360, RY: 190, D: 170, fk: 0.95, wall: '#8C9097', inner: '#3E4045', floor: '#4A4C52', rim: '#B9BDC4', handle: 'ears' },
    bowl: { cy: 1060, RX: 390, RY: 205, D: 210, fk: 0.55, wall: '#3C566E', inner: '#5A6F84', floor: '#647A90', rim: '#9FB3C6', handle: 'none' },
  };
  // a piece of food centred on 0,0 (about 40 px)
  function piece(parent, shape, color, r) {
    const g = el('g', {}, parent), dark = mixHex(color, '#000000', 0.28), st = { stroke: dark, 'stroke-width': 3 };
    const blob = (rad, n, j) => { let d = ''; for (let i = 0; i < n; i++) { const a = i / n * Math.PI * 2, q = rad * (1 - j + 2 * j * r()); d += (i ? ' L ' : 'M ') + (q * Math.cos(a)).toFixed(1) + ' ' + (q * Math.sin(a)).toFixed(1); } return d + ' Z'; };
    if (shape === 'dice') el('rect', { x: -16, y: -16, width: 32, height: 32, rx: 7, fill: color, ...st }, g);
    else if (shape === 'slice') el('path', { d: 'M -28 4 A 28 28 0 0 1 28 4 Z', fill: color, ...st }, g);
    else if (shape === 'ring') el('circle', { r: 22, fill: 'none', stroke: color, 'stroke-width': 9 }, g);
    else if (shape === 'round') { el('circle', { r: 19, fill: color, ...st }, g); el('circle', { cx: -6, cy: -7, r: 5, fill: 'rgba(255,255,255,0.45)' }, g); }
    else if (shape === 'strip') el('rect', { x: -36, y: -9, width: 72, height: 18, rx: 9, fill: color, ...st }, g);
    else if (shape === 'leaf') { el('path', { d: 'M 0 -22 C 15 -13 15 13 0 22 C -15 13 -15 -13 0 -22 Z', fill: color }, g); el('path', { d: 'M 0 -19 L 0 19', stroke: dark, 'stroke-width': 2 }, g); }
    else if (shape === 'mince') el('path', { d: blob(9, 6, 0.35), fill: color, ...st, 'stroke-width': 2 }, g);
    else if (shape === 'crumble') el('path', { d: blob(18, 7, 0.3), fill: color, ...st, 'stroke-width': 2 }, g);
    else if (shape === 'grain') el('ellipse', { rx: 9, ry: 4, fill: color }, g);
    else el('path', { d: blob(26, 8, 0.25), fill: color, ...st }, g);            // chunk
    return g;
  }
  const COUNT = { dice: 16, slice: 12, ring: 10, round: 12, strip: 12, leaf: 14, mince: 22, crumble: 10, grain: 60, chunk: 9 };

  function dishScene(svg, defs, plan, steps) {
    const V = VESSELS[plan.vessel] || VESSELS.pan, cx = 540, cy = V.cy, RX = V.RX, RY = V.RY, D = V.D, k = RY / RX;
    const rnd = rng(11);
    // ---- contents level: liquids and solids raise the surface
    const LIQ = s => s.kind === 'pour' && s.fill;
    const amountIn = (s, t) => (s.fill || 0) * E.io(span(t, s.at + 0.6, s.at + 0.6 + (s.pourDur || 1.4)));
    const level = t => clamp(steps.reduce((a, s) => a + (LIQ(s) || s.kind === 'add' ? amountIn(s, t) : 0), 0), 0, 0.9);
    const surf = t => { const L = level(t), rx = lerp(RX * V.fk, RX * 0.97, L); return { y: lerp(cy + D, cy + 6, L), rx, ry: rx * k }; };
    const inside = (u, v, S) => { const x = u * S.rx, y = S.y - cy + v * S.ry; return (x / (RX - 34)) ** 2 + (y / (RY - 22)) ** 2 < 1; };
    const spot = (S, rmax = 0.82) => { for (let i = 0; i < 40; i++) { const a = rnd() * Math.PI * 2, rr = Math.sqrt(rnd()) * rmax, u = rr * Math.cos(a), v = rr * Math.sin(a); if (inside(u, v, S)) return [u, v]; } return [0, 0]; };
    const swirlSteps = steps.filter(s => s.kind === 'stir' || s.kind === 'whisk' || s.spoon);
    const swirl = t => swirlSteps.reduce((a, s) => a + Math.PI * 1.4 * E.io(span(t, s.at + 0.4, s.end - 0.3)), 0);
    const place = (u, v, t, S) => { const a = swirl(t) * (1 - 0.4 * Math.hypot(u, v)), c = Math.cos(a), sn = Math.sin(a), uu = u * c - v * sn, vv = u * sn + v * c; return [cx + uu * S.rx, S.y + vv * S.ry]; };
    const firstHeat = steps.find(s => s.heat || s.kind === 'cook');
    const cooks = steps.filter(s => s.kind === 'cook');
    const brownAt = (t, from) => cooks.filter(s => s.at >= from).reduce((a, s) => a + (s.brown || 0) * E.io(span(t, s.at + 0.3, s.end - 0.3)), 0);

    // ---- the vessel
    el('ellipse', { cx, cy: cy + D + RY * V.fk + 30, rx: RX * 1.05, ry: 60, fill: 'rgba(0,0,0,0.38)' }, svg);
    const glowGrad = el('radialGradient', { id: 'heat' }, defs);
    el('stop', { offset: '0%', 'stop-color': '#FF8A2A', 'stop-opacity': 0.9 }, glowGrad); el('stop', { offset: '100%', 'stop-color': '#FF5A1A', 'stop-opacity': 0 }, glowGrad);
    const glow = el('ellipse', { cx, cy: cy + D + 60, rx: RX * 1.15, ry: RY * 0.8, fill: 'url(#heat)', opacity: 0 }, svg);
    if (V.handle === 'long') { const h = el('g', { transform: `translate(${cx + RX - 30} ${cy + 40}) rotate(24)` }, svg); el('rect', { x: 0, y: -24, width: 420, height: 48, rx: 24, fill: '#1C1D20' }, h); el('rect', { x: 20, y: -16, width: 380, height: 10, rx: 5, fill: 'rgba(255,255,255,0.08)' }, h); }
    if (V.handle === 'ears') for (const sx of [-1, 1]) el('rect', { x: cx + sx * (RX + 30) - 40, y: cy + 50, width: 80, height: 30, rx: 15, fill: V.rim }, svg);
    const fr = RX * V.fk, fry = fr * k;
    const bodyD = V.handle === 'none'
      ? `M ${cx - RX} ${cy} C ${cx - RX} ${cy + D * 1.5}, ${cx + RX} ${cy + D * 1.5}, ${cx + RX} ${cy} A ${RX} ${RY} 0 0 1 ${cx - RX} ${cy} Z`
      : `M ${cx - RX} ${cy} L ${cx - fr} ${cy + D} A ${fr} ${fry} 0 0 0 ${cx + fr} ${cy + D} L ${cx + RX} ${cy} A ${RX} ${RY} 0 0 1 ${cx - RX} ${cy} Z`;
    const bg = el('linearGradient', { id: 'vbody', x1: 0, x2: 1 }, defs);
    [[0, mixHex(V.wall, '#000000', 0.25)], [0.45, mixHex(V.wall, '#FFFFFF', 0.12)], [1, mixHex(V.wall, '#000000', 0.35)]].forEach(([o, c]) => el('stop', { offset: o, 'stop-color': c }, bg));
    el('path', { d: bodyD, fill: 'url(#vbody)' }, svg);
    if (V.handle === 'none') el('ellipse', { cx, cy: cy + D * 1.12, rx: RX * 0.38, ry: 22, fill: mixHex(V.wall, '#000000', 0.2) }, svg);
    const clip = el('clipPath', { id: 'vclip' }, defs); el('ellipse', { cx, cy, rx: RX - 6, ry: RY - 6 }, clip);
    el('ellipse', { cx, cy, rx: RX, ry: RY, fill: V.inner }, svg);
    const inner = el('g', { 'clip-path': 'url(#vclip)' }, svg);
    el('ellipse', { cx, cy: cy + D, rx: fr, ry: fry, fill: V.floor }, inner);
    const liquids = el('g', {}, inner), bubbles = el('g', {}, inner);
    el('ellipse', { cx, cy, rx: RX, ry: RY, fill: 'none', stroke: V.rim, 'stroke-width': 12 }, svg);
    el('path', { d: `M ${cx - RX * 0.8} ${cy - RY * 0.6} A ${RX} ${RY} 0 0 1 ${cx + RX * 0.2} ${cy - RY * 0.99}`, fill: 'none', stroke: 'rgba(255,255,255,0.35)', 'stroke-width': 4, 'stroke-linecap': 'round' }, svg);
    const items = el('g', { 'clip-path': 'url(#vclip)' }, svg), falling = el('g', {}, svg), fx = el('g', {}, svg);
    const settle = (node, landed) => { const want = landed ? items : falling; if (node.parentNode !== want) want.appendChild(node); };
    hooks.push(t => { const on = firstHeat ? span(t, firstHeat.at, firstHeat.at + 0.8) : 0; glow.setAttribute('opacity', (on * (0.55 + 0.08 * Math.sin(t * 9) + 0.05 * Math.sin(t * 23))).toFixed(3)); });

    // ---- liquids: a puddle that spreads from where the stream lands; cook steps can deepen the colour
    const liqs = steps.filter(LIQ).map(s => ({ s, e: el('ellipse', { fill: s.color || '#C0392B', opacity: s.opacity || 0.95 }, liquids) }));
    const tints = cooks.filter(s => s.color).map(s => ({ s, e: el('ellipse', { fill: s.color, opacity: 0 }, liquids) }));
    const blendS = steps.find(s => (s.kind === 'whisk' || s.kind === 'stir') && s.blend);
    const blendE = blendS ? el('ellipse', { fill: plan.final || '#E8C27A', opacity: 0 }, liquids) : null;
    const sheen = el('ellipse', { fill: 'rgba(255,255,255,0.10)', opacity: 0 }, liquids);
    hooks.push(t => {
      const S = surf(t);
      for (const { s, e } of liqs) {
        const g = E.out(span(t, s.at + 0.65, s.at + 0.6 + (s.pourDur || 1.4) + 0.4));
        const sp = Math.sqrt(g) * (s.spread || 1);
        set(e, { cx, cy: S.y.toFixed(1), rx: (S.rx * sp).toFixed(1), ry: (S.ry * sp).toFixed(1), visibility: g > 0 ? 'visible' : 'hidden' });
      }
      let any = liqs.some(({ s }) => t > s.at + 0.65);
      for (const { s, e } of tints) set(e, { cx, cy: S.y.toFixed(1), rx: S.rx.toFixed(1), ry: S.ry.toFixed(1), opacity: (any ? E.io(span(t, s.at + 0.3, s.end - 0.3)) : 0).toFixed(3) });
      if (blendE) set(blendE, { cx, cy: S.y.toFixed(1), rx: S.rx.toFixed(1), ry: S.ry.toFixed(1), opacity: E.io(span(t, blendS.at + 0.4, blendS.end - 0.3)).toFixed(3) });
      set(sheen, { cx: cx - S.rx * 0.2, cy: (S.y - S.ry * 0.3).toFixed(1), rx: (S.rx * 0.5).toFixed(1), ry: (S.ry * 0.25).toFixed(1), opacity: any ? 1 : 0 });
    });

    // ---- solids, garnish and sprinkles: pieces fall in and settle on the surface, turn with the spoon and brown with cooking
    for (const s of steps) {
      if (!['add', 'garnish', 'sprinkle'].includes(s.kind)) continue;
      const list = s.items && s.items.length ? s.items : [{ shape: s.shape || (s.kind === 'sprinkle' ? 'dust' : 'chunk'), color: s.color }];
      list.forEach((it, j) => {
        const shape = it.shape || 'chunk', dust = shape === 'dust', n = it.count || (dust ? 70 : COUNT[shape] || 12);
        for (let i = 0; i < n; i++) {
          const S0 = surf(s.end), [u, v] = spot(S0, s.kind === 'garnish' ? 0.75 : 0.82);
          const node = dust ? el('circle', { r: 2.5 + rnd() * 3, fill: it.color || s.color || '#B5442A' }, items) : piece(items, shape, it.color || s.color || '#D9A441', rnd);
          const d = s.at + 0.45 + j * 0.35 + (dust ? rnd() * 1.1 : i * Math.min(0.06, 1.0 / n)), rot = rnd() * 360, sc = 0.85 + rnd() * 0.3;
          const sx = dust ? cx + (rnd() - 0.5) * 60 : cx + (rnd() - 0.5) * 260, sy = dust ? 760 : cy - RY - 200;
          const base = it.color || s.color || '#D9A441';
          hooks.push(t => {
            if (t < d) { node.setAttribute('visibility', 'hidden'); return; }
            node.setAttribute('visibility', 'visible');
            const S = surf(t), [px, py] = place(u, v, t, S), q = span(t, d, d + (dust ? 0.4 : 0.5)), e = E.in(q);
            settle(node, q >= 1);
            const bounce = q >= 1 && !dust ? 10 * Math.exp(-(t - d - 0.5) * 9) * Math.abs(Math.sin((t - d - 0.5) * 14)) : 0;
            const x = lerp(sx, px, e), y = lerp(sy, py, e) - bounce;
            node.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${(rot + 120 * (1 - q) + swirl(t) * 57).toFixed(1)}) scale(${sc.toFixed(2)} ${(sc * (q >= 1 ? 0.8 : 1)).toFixed(2)})`);
            if (!dust && s.kind === 'add') { const b = clamp(brownAt(t, s.at)); if (b > 0) node.style.filter = `brightness(${(1 - 0.35 * b).toFixed(3)}) saturate(${(1 + 0.2 * b).toFixed(3)})`; }
            // later sauces cover what went in before them, partly
            const cover = steps.filter(x => LIQ(x) && x.at > s.at && (x.opacity || 0.95) > 0.8).reduce((a, x) => a + E.out(span(t, x.at + 0.8, x.at + 0.6 + (x.pourDur || 1.4) + 0.4)), 0);
            node.setAttribute('opacity', ((1 - 0.5 * clamp(cover)) * span(t, d, d + 0.12)).toFixed(3));
            void base;
          });
        }
      });
      // a measuring spoon tips a sprinkle in
      if (s.kind === 'sprinkle') {
        const sp = el('g', {}, fx);
        el('ellipse', { cx: 0, cy: 0, rx: 46, ry: 30, fill: '#C9CED6' }, sp); el('ellipse', { cx: 0, cy: -4, rx: 36, ry: 20, fill: s.color || '#B5442A' }, sp);
        el('rect', { x: 40, y: -10, width: 200, height: 20, rx: 10, fill: '#C9CED6' }, sp);
        hooks.push(t => {
          const on = t >= s.at && t <= s.at + 2.2; sp.setAttribute('visibility', on ? 'visible' : 'hidden'); if (!on) return;
          const iq = E.out(span(t, s.at, s.at + 0.4)), oq = E.in(span(t, s.at + 1.7, s.at + 2.2));
          sp.setAttribute('transform', `translate(${(lerp(1000, 560, iq) + oq * 500).toFixed(1)} ${(730 - oq * 200).toFixed(1)}) rotate(${(-40 * E.io(span(t, s.at + 0.3, s.at + 0.6)) * (1 - oq)).toFixed(1)})`);
        });
      }
    }

    // ---- eggs: a shell drops, cracks open, the white spreads and the yolk sits on top
    for (const s of steps.filter(s => s.kind === 'crack')) {
      const n = s.count || 2;
      for (let i = 0; i < n; i++) {
        const a = (i / n) * Math.PI * 2 + 0.6, u = 0.45 * Math.cos(a), v = 0.45 * Math.sin(a), d = s.at + 0.5 + i * Math.min(0.5, 1.8 / n);
        const g = el('g', {}, items), white = el('path', { d: (() => { let p = ''; for (let j = 0; j < 9; j++) { const b = j / 9 * Math.PI * 2, q = 64 * (0.85 + 0.3 * rnd()); p += (j ? ' L ' : 'M ') + (q * Math.cos(b)).toFixed(1) + ' ' + (q * Math.sin(b) * 0.62).toFixed(1); } return p + ' Z'; })(), fill: '#FAF7EF', 'stroke-linejoin': 'round', stroke: '#FAF7EF', 'stroke-width': 18 }, g);
        const yolk = el('g', {}, g); el('ellipse', { rx: 30, ry: 25, fill: '#F2A81D' }, yolk); el('ellipse', { cx: -9, cy: -8, rx: 9, ry: 6, fill: 'rgba(255,255,255,0.55)' }, yolk);
        const shell = el('g', {}, fx); el('ellipse', { rx: 40, ry: 52, fill: '#F1DFC2', stroke: '#D9C3A0', 'stroke-width': 3 }, shell);
        hooks.push(t => {
          const S = surf(t), [px, py] = place(u, v, t, S);
          const sq = span(t, d - 0.45, d); shell.setAttribute('visibility', t >= d - 0.45 && t < d + 0.05 ? 'visible' : 'hidden');
          shell.setAttribute('transform', `translate(${lerp(px, px, sq).toFixed(1)} ${lerp(560, py - 70, E.in(sq)).toFixed(1)}) rotate(${(30 * sq).toFixed(1)})`);
          if (t < d) { g.setAttribute('visibility', 'hidden'); return; }
          g.setAttribute('visibility', 'visible'); settle(g, true);
          const sp = E.out(span(t, d, d + 0.6)), cook = clamp(brownAt(t, s.at) * 2);
          g.setAttribute('transform', `translate(${px.toFixed(1)} ${py.toFixed(1)})`);
          white.setAttribute('transform', `scale(${(0.4 + 0.6 * sp).toFixed(3)})`); white.setAttribute('opacity', (0.72 + 0.28 * cook).toFixed(3));
          yolk.setAttribute('transform', `translate(0 ${(-30 * (1 - E.out(span(t, d, d + 0.35)))).toFixed(1)})`);
        });
      }
    }

    // ---- pours: a bottle (oil, stock) or a small bowl (sauce, batter) tips in from the upper right
    for (const s of steps.filter(LIQ)) {
      const b = el('g', {}, fx), bowl = s.container === 'bowl', pour = s.pourDur || 1.4;
      if (bowl) { el('path', { d: 'M -130 -40 Q -120 80 0 80 Q 120 80 130 -40 Z', fill: '#C27A52' }, b); el('ellipse', { cx: 0, cy: -40, rx: 130, ry: 34, fill: s.color || '#C0392B' }, b); }
      else {
        const col = s.bottle || '#E6E0C8';
        el('rect', { x: -60, y: -240, width: 120, height: 280, rx: 30, fill: col, opacity: 0.94 }, b); el('rect', { x: -22, y: -330, width: 44, height: 100, rx: 12, fill: col, opacity: 0.94 }, b);
        el('rect', { x: -60, y: -160, width: 120, height: 110, fill: s.color || '#D4B33A', opacity: 0.85 }, b); el('rect', { x: -26, y: -346, width: 52, height: 20, rx: 6, fill: '#2B2B2B' }, b);
      }
      const M = bowl ? [-130, -40] : [0, -330], tiltTo = bowl ? -78 : -125;
      const stream = el('path', { fill: 'none', stroke: s.color || '#D4B33A', 'stroke-linecap': 'round' }, fx);
      hooks.push(t => {
        const on = t >= s.at && t <= s.at + pour + 1.1; b.setAttribute('visibility', on ? 'visible' : 'hidden'); stream.setAttribute('visibility', 'hidden'); if (!on) return;
        const iq = E.out(span(t, s.at, s.at + 0.5)), oq = E.in(span(t, s.at + pour + 0.55, s.at + pour + 0.95));
        const tilt = tiltTo * E.io(span(t, s.at + 0.2, s.at + 0.6)) * (1 - E.io(span(t, s.at + pour + 0.5, s.at + pour + 0.8)));
        const bx = lerp(1150, bowl ? 700 : 790, iq) + oq * 700, by = lerp(420, bowl ? 760 : 650, iq) - oq * 360;
        b.setAttribute('transform', `translate(${bx.toFixed(1)} ${by.toFixed(1)}) rotate(${tilt.toFixed(1)})`);
        if (t >= s.at + 0.55 && t <= s.at + 0.6 + pour) {
          const a = tilt * Math.PI / 180, mx = bx + M[0] * Math.cos(a) - M[1] * Math.sin(a), my = by + M[0] * Math.sin(a) + M[1] * Math.cos(a), S = surf(t);
          const w = (bowl ? 30 : 14) * Math.min(1, span(t, s.at + 0.55, s.at + 0.75)) * (1 - span(t, s.at + 0.4 + pour, s.at + 0.6 + pour));
          set(stream, { d: `M ${mx.toFixed(1)} ${my.toFixed(1)} C ${(mx - 30).toFixed(1)} ${(my + 80).toFixed(1)}, ${cx + 10} ${(S.y - 160).toFixed(1)}, ${cx} ${S.y.toFixed(1)}`, 'stroke-width': w.toFixed(1), visibility: 'visible' });
        }
      });
    }

    // ---- a wooden spoon (or a whisk) circling through the contents
    for (const s of swirlSteps) {
      const sp = el('g', {}, fx), whisk = s.kind === 'whisk';
      if (whisk) { for (let i = -2; i <= 2; i++) el('path', { d: `M 0 -260 C ${i * 34} -170, ${i * 46} -40, 0 0`, fill: 'none', stroke: '#D9DDE2', 'stroke-width': 5 }, sp); el('rect', { x: -14, y: -620, width: 28, height: 370, rx: 14, fill: '#3B3E44' }, sp); }
      else { el('rect', { x: -14, y: -640, width: 28, height: 600, rx: 14, fill: '#C68A4E' }, sp); el('ellipse', { cx: 0, cy: -20, rx: 40, ry: 56, fill: '#B87A40' }, sp); }
      hooks.push(t => {
        const on = t >= s.at && t <= s.end; sp.setAttribute('visibility', on ? 'visible' : 'hidden'); if (!on) return;
        const iq = E.out(span(t, s.at, s.at + 0.35)), oq = E.in(span(t, s.end - 0.35, s.end)), S = surf(t), ph = (t - s.at) * Math.PI * (whisk ? 5 : 2.4);
        const x = cx + S.rx * 0.45 * Math.cos(ph), y = S.y + S.ry * 0.45 * Math.sin(ph) - (1 - iq) * 700 - oq * 700;
        sp.setAttribute('transform', `translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${(18 + 8 * Math.cos(ph)).toFixed(1)})`);
      });
    }

    // ---- a glass lid comes down for cook steps with lid: true and lifts off at the end
    for (const s of cooks.filter(s => s.lid)) {
      const lid = el('g', {}, fx);
      const top = -RY - 120;   // a glass dome over the rim, the knob on its crown
      el('path', { d: `M ${-RX - 8} 0 C ${-RX - 8} ${top * 0.9}, ${-RX * 0.45} ${top}, 0 ${top} C ${RX * 0.45} ${top}, ${RX + 8} ${top * 0.9}, ${RX + 8} 0 A ${RX + 8} ${RY + 6} 0 0 1 ${-RX - 8} 0 Z`, fill: 'rgba(220,235,245,0.14)' }, lid);
      el('ellipse', { cx: 0, cy: 0, rx: RX + 8, ry: RY + 6, fill: 'none', stroke: '#9AA3AD', 'stroke-width': 10 }, lid);
      el('path', { d: `M ${-RX * 0.75} ${top * 0.55} C ${-RX * 0.6} ${top * 0.95}, ${-RX * 0.3} ${top * 1.0}, ${-RX * 0.05} ${top * 0.99}`, fill: 'none', stroke: 'rgba(255,255,255,0.4)', 'stroke-width': 9, 'stroke-linecap': 'round' }, lid);
      el('rect', { x: -48, y: top - 34, width: 96, height: 40, rx: 18, fill: '#2B2C30' }, lid);
      hooks.push(t => {
        const on = t >= s.at + 0.2 && t <= s.end; lid.setAttribute('visibility', on ? 'visible' : 'hidden'); if (!on) return;
        const dq = E.out(span(t, s.at + 0.2, s.at + 0.7)), uq = E.in(span(t, s.end - 0.45, s.end));
        lid.setAttribute('transform', `translate(${cx} ${(cy - 4 - (1 - dq) * 500 - uq * 600).toFixed(1)})`);
      });
    }
    // ---- simmering: bubbles swell and pop on the surface while a cook step runs; steam once there is heat
    const rb = rng(77), bub = [];
    for (let i = 0; i < 16; i++) bub.push({ n: el('circle', { fill: 'none', stroke: 'rgba(255,255,255,0.35)', 'stroke-width': 3 }, bubbles), u: (rb() - 0.5) * 1.4, v: (rb() - 0.5) * 1.2, ph: rb(), sp: 0.9 + rb() * 0.8, r: 8 + rb() * 12 });
    const simmer = cooks.filter(s => s.bubbles !== false);
    hooks.push(t => {
      const act = simmer.reduce((a, s) => Math.max(a, span(t, s.at, s.at + 0.5) * (1 - span(t, s.end, s.end + 0.6))), 0), S = surf(t);
      const wet = liqs.some(({ s }) => t > s.at + 1);
      for (const b of bub) {
        const c = (t * b.sp + b.ph) % 1;
        if (!wet || act <= 0 || !inside(b.u * 0.8, b.v * 0.8, S)) { b.n.setAttribute('visibility', 'hidden'); continue; }
        set(b.n, { visibility: 'visible', cx: (cx + b.u * 0.8 * S.rx).toFixed(1), cy: (S.y + b.v * 0.8 * S.ry).toFixed(1), r: (b.r * E.out(c)).toFixed(1), opacity: (act * (1 - c ** 3)).toFixed(3) });
      }
    });
    const steam = [];
    if (cooks.length) for (let i = 0; i < 4; i++) steam.push({ p: el('path', { fill: 'none', stroke: '#FFFFFF', 'stroke-width': 22, 'stroke-linecap': 'round', opacity: 0 }, fx), x: cx - 180 + i * 120, ph: i * 0.37 });
    const steamFrom = cooks[0] ? cooks[0].at : null, outroAt = steps.length ? steps[steps.length - 1].end : 1e9;
    if (steamFrom !== null) hooks.push(t => {
      const on = span(t, steamFrom, steamFrom + 1.2) * (1 - 0.8 * span(t, outroAt, outroAt + 0.6)), S = surf(t);
      for (const w of steam) {
        if (on <= 0) { w.p.setAttribute('opacity', 0); continue; }
        const c = (t * 0.35 + w.ph) % 1, y0 = S.y - 40 - c * 260;
        let d = ''; for (let j = 0; j <= 6; j++) { const y = y0 - j * 40; d += (j ? ' L ' : 'M ') + (w.x + 24 * Math.sin(j * 0.9 + t * 2 + w.ph * 9)).toFixed(1) + ' ' + y.toFixed(1); }
        set(w.p, { d, opacity: (on * 0.16 * Math.sin(Math.PI * c)).toFixed(3) });
      }
    });
  }

  // ---------------------------------------------------------------- the run
  function run(host, plan) {
    const css = document.createElement('style');
    css.textContent = `
      @font-face{font-family:Montserrat;src:url(recipe/Montserrat.ttf);font-weight:100 900}
      @font-face{font-family:'Instrument Serif';src:url(recipe/InstrumentSerif-Italic.ttf);font-style:italic}
      #rc{position:absolute;inset:0;overflow:hidden;font-family:Montserrat,sans-serif;color:#fff}
      #rc .cap{position:absolute;left:0;right:0;top:1640px;text-align:center;font:700 54px/1.1 Montserrat;color:#fff;text-shadow:0 4px 18px rgba(0,0,0,.45)}`;
    document.head.appendChild(css);
    const root = document.createElement('div'); root.id = 'rc'; host.appendChild(root);
    const [bg0, bg1] = plan.bg || ['#123F44', '#071E22'];
    const accent = plan.accent || '#F2C14E';
    root.style.background = `radial-gradient(120% 80% at 50% 38%, ${bg0} 0%, ${bg1} 75%)`;
    const svg = el('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}` }, root);
    svg.style.position = 'absolute'; svg.style.inset = '0';
    const defs = el('defs', {}, svg);
    const steps = plan.steps || [];
    (plan.vessel ? dishScene : drinkScene)(svg, defs, plan, steps);

    // ---------------------------------------------------------------- type: title, step chip, measurement card
    const ui = document.createElement('div'); ui.style.cssText = 'position:absolute;inset:0;pointer-events:none'; root.appendChild(ui);
    const title = document.createElement('div');
    title.style.cssText = 'position:absolute;left:0;right:0;top:250px;text-align:center';
    title.innerHTML = `<div style="font:500 30px Montserrat;letter-spacing:8px;text-transform:uppercase;color:${accent}">${plan.tagline || '30-second recipe'}</div>
      <div style="font:italic 150px/1 'Instrument Serif';margin-top:18px">${plan.name || 'Cocktail'}</div>`;
    ui.appendChild(title);
    const chip = document.createElement('div');
    chip.style.cssText = `position:absolute;left:80px;top:190px;font:600 30px Montserrat;letter-spacing:4px;text-transform:uppercase;color:${accent}`;
    const head = document.createElement('div');
    head.style.cssText = 'position:absolute;left:80px;top:236px;font:italic 96px/1 "Instrument Serif";white-space:nowrap';
    ui.appendChild(chip); ui.appendChild(head);
    const card = document.createElement('div');
    card.style.cssText = 'position:absolute;left:80px;top:420px;padding:26px 34px;border-radius:28px;background:rgba(255,255,255,0.1);border:2px solid rgba(255,255,255,0.18);backdrop-filter:blur(2px);min-width:330px';
    const amt = document.createElement('div'); amt.style.cssText = 'font:800 104px/1 Montserrat;letter-spacing:-2px';
    const nm = document.createElement('div'); nm.style.cssText = 'font:600 40px/1.2 Montserrat;margin-top:10px';
    const ml = document.createElement('div'); ml.style.cssText = `font:600 30px Montserrat;margin-top:8px;color:${accent}`;
    const bar = document.createElement('div'); bar.style.cssText = 'height:8px;border-radius:4px;background:rgba(255,255,255,0.14);margin-top:16px;overflow:hidden';
    const barIn = document.createElement('div'); barIn.style.cssText = 'height:100%;width:0;border-radius:4px'; bar.appendChild(barIn);
    card.appendChild(amt); card.appendChild(nm); card.appendChild(ml); card.appendChild(bar); ui.appendChild(card);
    const sw = document.createElement('span'); sw.style.cssText = 'display:inline-block;width:26px;height:26px;border-radius:50%;margin-right:14px;vertical-align:middle';
    const capEl = document.createElement('div'); capEl.className = 'cap'; root.appendChild(capEl);
    const real = steps.filter(s => s.kind !== 'intro');
    const outro = { at: (steps[steps.length - 1] || { end: plan.duration - 3 }).end, list: steps.filter(s => (s.amount || s.name) && ['add', 'pour', 'top', 'ice', 'sprinkle', 'crack', 'garnish'].includes(s.kind)) };
    // the closing card: the drink's name and everything that went in
    const end = document.createElement('div');
    end.style.cssText = 'position:absolute;left:80px;right:80px;top:150px;text-align:left';
    end.innerHTML = `<div style="font:italic 132px/1 'Instrument Serif'">${plan.name || ''}</div>` + outro.list.map(s =>
      `<div style="display:flex;justify-content:space-between;font:600 38px/1.6 Montserrat;border-bottom:2px solid rgba(255,255,255,0.12)"><span>${s.name || s.title}</span><span style="color:${accent}">${s.amount ? s.amount + ' ' + (s.unit || '') : ''}</span></div>`).join('');
    ui.appendChild(end);
    hooks.push(t => {
      const first = real[0] ? real[0].at : 2.5;
      const tq = span(t, 0, 0.5) * (1 - span(t, first - 0.4, first));
      title.style.opacity = tq.toFixed(3); title.style.transform = `translateY(${((1 - E.out(span(t, 0, 0.6))) * 40).toFixed(1)}px)`;
      let cur = null; for (const s of real) if (t >= s.at && t < s.end) cur = s;
      const showEnd = t >= outro.at;
      end.style.opacity = span(t, outro.at, outro.at + 0.5).toFixed(3);
      end.style.transform = `translateY(${((1 - E.out(span(t, outro.at, outro.at + 0.6))) * 40).toFixed(1)}px)`;
      if (!cur || showEnd) { chip.style.opacity = head.style.opacity = card.style.opacity = 0; return; }
      const n = real.indexOf(cur) + 1, q = span(t, cur.at, cur.at + 0.35), qo = span(t, cur.end - 0.25, cur.end);
      chip.textContent = `Step ${n} of ${real.length}`; head.textContent = cur.title || '';
      chip.style.opacity = head.style.opacity = (E.out(q) * (1 - qo)).toFixed(3);
      head.style.transform = `translateX(${((1 - E.out(q)) * -50).toFixed(1)}px)`;
      const hasAmt = !!(cur.amount || cur.name);
      card.style.opacity = hasAmt ? (E.out(span(t, cur.at + 0.15, cur.at + 0.5)) * (1 - qo)).toFixed(3) : 0;
      card.style.transform = `translateY(${((1 - E.back(span(t, cur.at + 0.15, cur.at + 0.6))) * 60).toFixed(1)}px)`;
      if (hasAmt && amt.dataset.k !== String(n)) {
        amt.dataset.k = String(n);
        amt.textContent = cur.amount ? `${cur.amount} ${cur.unit || ''}`.trim() : '';
        nm.textContent = ''; sw.style.background = cur.color || '#fff'; nm.appendChild(sw); nm.appendChild(document.createTextNode(cur.name || ''));
        ml.textContent = cur.ml ? `${cur.ml} ml` : '';
      }
      // the bar fills while the ingredient goes in
      const pd = cur.kind === 'cook' ? Math.max(0.5, cur.end - cur.at - 0.9) : cur.kind === 'pour' || cur.kind === 'top' ? cur.pourDur || 1.6 : 1.0;
      barIn.style.background = cur.color || accent;
      barIn.style.width = (100 * E.io(span(t, cur.at + 0.6, cur.at + 0.6 + pd))).toFixed(1) + '%';
    });
    // captions: one phrase at a time along the bottom
    hooks.push(t => {
      let c = null; for (const x of plan.captions || []) if (t >= x[0]) c = x;
      capEl.textContent = c && t <= c[2] ? c[1] : '';
    });
    return t => { for (const h of hooks) h(t); };
  }

  window.RC = { run, GLASSES: Object.keys(GLASSES), VESSELS: Object.keys(VESSELS) };
})();
