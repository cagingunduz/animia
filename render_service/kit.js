/* Animave motion kit — loaded into every composition after anime.js.
 * Short, seek-safe helpers so the animator writes intent, not boilerplate.
 * Every helper sets the element's starting state immediately (at load), so nothing
 * needs a CSS initial state, and adds its tween to the timeline at `at` ms. */
(function () {
  const A = window.anime;
  const $$ = (sel) => (typeof sel === 'string' ? Array.from(document.querySelectorAll(sel)) : [].concat(sel));

  // Time hooks: functions of the timeline's current time, re-run on every render/seek, so
  // text driven by time (counters) is right whatever order the renderer seeks frames in.
  function runHooks(tl) { const t = tl.currentTime; (tl._kHooks || []).forEach((h) => h(t)); }

  function timeline(defaults) {
    const tl = A.createTimeline({
      autoplay: false,
      defaults: Object.assign({ ease: 'outExpo', duration: 650 }, defaults || {}),
      onRender: () => runHooks(tl),
      onUpdate: () => runHooks(tl),
    });
    tl._kHooks = [];
    window.__hfAnime = window.__hfAnime || [];
    window.__hfAnime.push(tl);
    return tl;
  }

  // Wrap text into animatable pieces. mode: 'words' (masked) | 'chars'.
  // Only text nodes are wrapped, so nested styling (<b>, coloured spans, font sizes) survives.
  function split(sel, mode) {
    $$(sel).forEach((el) => {
      if (el.dataset.kitSplit) return;
      el.dataset.kitSplit = mode || 'words';
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach((node) => {
        const text = node.nodeValue;
        if (!text.trim()) return;
        const frag = document.createDocumentFragment();
        if (mode === 'chars') {
          for (const c of text) {
            const sp = document.createElement('span');
            sp.className = 'k-c';
            sp.textContent = c === ' ' ? '\u00a0' : c;
            frag.appendChild(sp);
          }
        } else {
          text.split(/(\s+)/).forEach((part) => {
            if (!part) return;
            if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(' ')); return; }
            const m = document.createElement('span');
            m.className = 'k-m';
            const w = document.createElement('span');
            w.className = 'k-w';
            w.textContent = part;
            m.appendChild(w);
            frag.appendChild(m);
          });
        }
        node.parentNode.replaceChild(frag, node);
      });
    });
  }

  const set = (t, v) => A.utils.set(t, v);

  // Sound cues: every helper records what happened and when (ms on its timeline). The sound
  // designer reads window.__kCues and drops a matching effect exactly there.
  window.__kCues = window.__kCues || [];
  function cue(t, kind, dur, n) {
    window.__kCues.push({ t: Math.round(t || 0), kind, dur: Math.round(dur || 0), n: n || 1 });
  }
  const count0 = (sel) => $$(sel).length;

  // Words rise out of masks.
  function rise(tl, sel, at, o) {
    o = o || {};
    split(sel, 'words');
    const t = $$(sel).flatMap((el) => Array.from(el.querySelectorAll('.k-w')));
    // Hidden words are also transparent, so layout QA does not count them as visible text.
    set(t, { y: '110%', opacity: 0 });
    cue(at, 'rise', o.duration || 700, t.length);
    tl.add(t, {
      y: ['110%', '0%'], opacity: { from: 0, to: 1, duration: 1 },
      duration: o.duration || 700, delay: A.stagger(o.stagger || 70), ease: o.ease || 'outExpo',
    }, at || 0);
  }

  // Characters type on.
  function typeOn(tl, sel, at, o) {
    o = o || {};
    split(sel, 'chars');
    const t = $$(sel).flatMap((el) => Array.from(el.querySelectorAll('.k-c')));
    set(t, { opacity: 0 });
    cue(at, 'type', t.length * (o.perChar || 40), t.length);
    tl.add(t, { opacity: [0, 1], duration: 1, delay: A.stagger(o.perChar || 40) }, at || 0);
  }

  // Characters drop in with a little lift.
  function charsUp(tl, sel, at, o) {
    o = o || {};
    split(sel, 'chars');
    const t = $$(sel).flatMap((el) => Array.from(el.querySelectorAll('.k-c')));
    set(t, { opacity: 0, y: o.dy || 40 });
    cue(at, 'rise', (o.duration || 500) + t.length * (o.stagger || 25), t.length);
    tl.add(t, { opacity: [0, 1], y: [o.dy || 40, 0], duration: o.duration || 500, delay: A.stagger(o.stagger || 25) }, at || 0);
  }

  function fadeUp(tl, sel, at, o) {
    o = o || {};
    const t = $$(sel);
    set(t, { opacity: 0, y: o.dy || 40 });
    cue(at, 'soft', o.duration || 600, t.length);
    tl.add(t, { opacity: [0, 1], y: [o.dy || 40, 0], duration: o.duration || 600, delay: A.stagger(o.stagger || 80) }, at || 0);
  }

  // Overshoot pop (badges, icons, numbers).
  function pop(tl, sel, at, o) {
    o = o || {};
    const t = $$(sel);
    set(t, { opacity: 0, scale: o.from || 0.6 });
    t.forEach((_, i) => cue((at || 0) + i * (o.stagger || 70), 'pop', 200, 1));
    tl.add(t, { opacity: [0, 1], scale: [o.from || 0.6, 1], duration: o.duration || 550, ease: 'outBack(1.7)', delay: A.stagger(o.stagger || 70) }, at || 0);
  }

  // Clip-path reveal. dir: 'right' (default) | 'left' | 'up' | 'down'
  const CLIP = {
    right: ['inset(0 100% 0 0)', 'inset(0 0% 0 0)'], left: ['inset(0 0 0 100%)', 'inset(0 0 0 0%)'],
    up: ['inset(100% 0 0 0)', 'inset(0% 0 0 0)'], down: ['inset(0 0 100% 0)', 'inset(0 0 0% 0)'],
  };
  function wipe(tl, sel, at, o) {
    o = o || {};
    const c = CLIP[o.dir || 'right'];
    const t = $$(sel);
    set(t, { clipPath: c[0] });
    cue(at, 'swipe', o.duration || 600, t.length);
    tl.add(t, { clipPath: c, duration: o.duration || 600, ease: o.ease || 'inOutQuart', delay: A.stagger(o.stagger || 0) }, at || 0);
  }

  // Grow a bar / line from one side. axis 'x' | 'y'
  function grow(tl, sel, at, o) {
    o = o || {};
    const t = $$(sel);
    const prop = (o.axis || 'x') === 'x' ? 'scaleX' : 'scaleY';
    t.forEach((el) => { el.style.transformOrigin = o.origin || ((o.axis || 'x') === 'x' ? 'left center' : 'center bottom'); });
    set(t, { [prop]: 0 });
    cue(at, 'grow', o.duration || 700, t.length);
    tl.add(t, { [prop]: [0, 1], duration: o.duration || 700, ease: o.ease || 'outExpo', delay: A.stagger(o.stagger || 60) }, at || 0);
  }

  // Count a number up inside an element. fmt: 'int' | 'comma' | 'pct' | 'money' | function
  // ease: 'linear' | 'outCubic' | 'inOutSine' | 'outExpo' | 'outQuad' | function(p) -> p'
  const EASE = {
    linear: (p) => p,
    outQuad: (p) => 1 - (1 - p) * (1 - p),
    outCubic: (p) => 1 - Math.pow(1 - p, 3),
    outExpo: (p) => (p >= 1 ? 1 : 1 - Math.pow(2, -10 * p)),
    inOutSine: (p) => -(Math.cos(Math.PI * p) - 1) / 2,
  };
  function count(tl, sel, to, at, o) {
    o = o || {};
    const el = $$(sel)[0];
    if (!el) return;
    const from = o.from || 0;
    const dur = o.duration || 1400;
    const start = at || 0;
    const ease = typeof o.ease === 'function' ? o.ease : (EASE[o.ease] || EASE.outCubic);
    const f = typeof o.fmt === 'function' ? o.fmt
      : o.fmt === 'pct' ? (v) => Math.round(v) + '%'
        : o.fmt === 'money' ? (v) => '$' + Math.round(v).toLocaleString('en-US')
          : o.fmt === 'int' ? (v) => String(Math.round(v))
            : (v) => Math.round(v).toLocaleString('en-US');
    const render = (t) => {
      const p = Math.min(1, Math.max(0, (t - start) / dur));
      el.textContent = f(from + (to - from) * ease(p));
    };
    render(0);
    cue(start, 'count', dur, 1);
    (tl._kHooks = tl._kHooks || []).push(render);
    tl.add({ k: 0 }, { k: 1, duration: dur, ease: 'linear' }, start);  // keeps the timeline long enough
  }

  // Draw SVG strokes (path/line/circle/polyline…).
  function draw(tl, sel, at, o) {
    o = o || {};
    const d = A.svg.createDrawable(sel);
    set(d, { draw: '0 0' });
    cue(at, 'draw', o.duration || 1200, 1);
    tl.add(d, { draw: ['0 0', '0 1'], duration: o.duration || 1200, ease: o.ease || 'inOutSine', delay: A.stagger(o.stagger || 0) }, at || 0);
  }

  // Slow camera push / drift over the whole shot — secondary motion.
  function push(tl, sel, durationMs, o) {
    o = o || {};
    tl.add(sel, { scale: [1, o.scale || 1.04], x: [0, o.x || 0], y: [0, o.y || 0], duration: durationMs, ease: 'linear' }, 0);
  }

  // Exits for the shot's transition_out. kind: 'fade' | 'up' | 'down' | 'left' | 'right' | 'wipe' | 'zoom' | 'blur'
  function exit(tl, sel, at, kind, o) {
    o = o || {};
    const d = o.duration || 350;
    const k = kind || 'fade';
    const props = {
      fade: { opacity: [1, 0] }, up: { y: [0, -80], opacity: [1, 0] }, down: { y: [0, 80], opacity: [1, 0] },
      left: { x: [0, -160], opacity: [1, 0] }, right: { x: [0, 160], opacity: [1, 0] },
      wipe: { clipPath: ['inset(0 0 0 0%)', 'inset(0 0 0 100%)'] }, zoom: { scale: [1, 1.25], opacity: [1, 0] },
      blur: { filter: ['blur(0px)', 'blur(24px)'], opacity: [1, 0] },
    }[k] || { opacity: [1, 0] };
    cue(at, 'out', d, count0(sel));
    tl.add(sel, Object.assign({ duration: d, ease: 'inQuart', delay: A.stagger(o.stagger || 0) }, props), at);
    if (k === 'wipe') tl.add(sel, { opacity: 0, duration: 1 }, at + d + 1);  // fully gone for layout QA
  }

  // Static, deterministic film grain over the root.
  function grain(rootSel, opacity, blend) {
    const root = $$(rootSel || '#root')[0];
    if (!root) return;
    const w = root.offsetWidth || 1920, h = root.offsetHeight || 1080;
    root.insertAdjacentHTML('beforeend',
      `<svg class="k-grain" width="${w}" height="${h}" style="opacity:${opacity == null ? 0.1 : opacity};mix-blend-mode:${blend || 'multiply'}">` +
      '<filter id="k-n"><feTurbulence type="fractalNoise" baseFrequency=".9" numOctaves="2" seed="7"/></filter>' +
      '<rect width="100%" height="100%" filter="url(#k-n)"/></svg>');
  }

  // ─── Cinematic helpers (image-based looks: a still per beat, motion added in code) ───

  // Slow camera move over a still (Ken Burns). from/to: {scale, x, y} with x/y in % of the frame.
  function camera(tl, sel, at, duration, o) {
    o = o || {};
    const f = Object.assign({ scale: 1.0, x: 0, y: 0 }, o.from || {});
    const t = Object.assign({ scale: 1.12, x: 0, y: 0 }, o.to || {});
    $$(sel).forEach((el) => { el.style.transformOrigin = o.origin || '50% 50%'; });
    set(sel, { scale: f.scale, x: f.x + '%', y: f.y + '%' });
    tl.add(sel, { scale: [f.scale, t.scale], x: [f.x + '%', t.x + '%'], y: [f.y + '%', t.y + '%'],
      duration, ease: o.ease || 'inOutSine' }, at || 0);
  }

  // Cross-dissolve one still into the next (both full-bleed, stacked).
  function dissolve(tl, outSel, inSel, at, o) {
    o = o || {};
    const d = o.duration || 600;
    set(inSel, { opacity: 0 });
    cue(at, 'whoosh', d, 1);
    tl.add(inSel, { opacity: [0, 1], duration: d, ease: 'inOutSine' }, at);
    if (outSel) tl.add(outSel, { opacity: [1, 0], duration: d, ease: 'inOutSine' }, at + d * 0.3);
  }

  // A glowing scan line sweeping over an element (x-ray / medical look). Needs a .k-scan child.
  function scan(tl, sel, at, o) {
    o = o || {};
    const host = $$(sel)[0];
    if (!host) return;
    const line = document.createElement('div');
    line.className = 'k-scan';
    line.style.setProperty('--k-scan', o.color || '#5FE3FF');
    host.appendChild(line);
    const h = host.offsetHeight || 1920;  // sweep the host's full height (translate % would be the line's own 6 px)
    set(line, { opacity: 0, y: -20 });
    cue(at, 'scan', o.duration || 1600, 1);
    tl.add(line, { opacity: [0, 1, 1, 0], y: [-20, h + 20], duration: o.duration || 1600, ease: 'inOutSine' }, at);
  }

  // Eyelid blink to black (microsleep / cut). Adds a full-frame black layer.
  function blink(tl, at, o) {
    o = o || {};
    const root = $$(o.root || '#root')[0];
    const lid = document.createElement('div');
    lid.className = 'k-lid';
    root.appendChild(lid);
    set(lid, { opacity: 0 });
    const hold = o.hold || 500;
    cue(at, 'heartbeat', hold + 400, 1);
    tl.add(lid, { opacity: [0, 1], duration: 160, ease: 'inQuad' }, at)
      .add(lid, { opacity: [1, 0], duration: 260, ease: 'outQuad' }, at + 160 + hold);
  }

  // Short deterministic glitch: horizontal jitter + colour split on an element.
  function glitch(tl, sel, at, o) {
    o = o || {};
    const n = o.steps || 6;
    const rnd = A.createSeededRandom(o.seed || 11);
    const xs = Array.from({ length: n }, (_, i) => (i === n - 1 ? 0 : (rnd() - 0.5) * (o.amount || 40)));
    cue(at, 'glitch', 120 * n, 1);
    tl.add(sel, { x: xs.map((v) => v + 'px'), filter: xs.map((v, i) => (i === n - 1 ? 'none'
      : `drop-shadow(${v / 4}px 0 0 rgba(255,0,80,.7)) drop-shadow(${-v / 4}px 0 0 rgba(0,220,255,.7))`)),
      duration: 120 * n, ease: 'linear' }, at);
  }

  // Whiteboard eraser: an eraser scrubs the board in a zig-zag; where it passes the drawing is
  // painted over with the board colour. The eraser rides the stroke's leading edge.
  function erase(tl, at, o) {
    o = o || {};
    const root = $$(o.root || '#root')[0];
    const W = root.offsetWidth || 1080, H = root.offsetHeight || 1920;
    const dur = o.duration || 1800;
    const band = o.band || Math.round(Math.min(W, H) * 0.22);      // eraser stroke width
    const rows = Math.ceil((H + band) / (band * 0.68));
    // Hand-erasing path: wavy, slightly irregular passes (seeded, so every render is identical);
    // turns stay inside the frame so an eraser tool would stay visible.
    const rnd = A.createSeededRandom(o.seed || 7);
    const xl = Math.round(band * 0.35), xr = W - xl;
    const stepX = band * 0.5;
    const wave = (x, r) => Math.sin(x / (band * 1.6) + r * 1.7) * band * 0.14 + (rnd() - 0.5) * band * 0.12;
    let d = `M ${xl} ${-band / 4}`;
    for (let r = 0; r <= rows; r++) {
      const y = -band / 4 + r * band * 0.68;
      const ltr = r % 2 === 0;
      for (let x = xl + stepX; x <= xr; x += stepX) {
        const px = ltr ? x : W - x;
        d += ` L ${px.toFixed(1)} ${(y + wave(px, r)).toFixed(1)}`;
      }
      if (r < rows) d += ` L ${ltr ? xr : xl} ${(y + band * 0.68).toFixed(1)}`;
    }
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('class', 'k-erase');
    svg.setAttribute('width', W); svg.setAttribute('height', H);
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    // ragged eraser edge: displace the wide stroke with seeded noise
    const rough = Math.round(band * (o.rough == null ? 0.22 : o.rough));
    svg.innerHTML = `<defs><filter id="k-rough" x="-10%" y="-10%" width="120%" height="120%">`
      + `<feTurbulence type="fractalNoise" baseFrequency="0.03" numOctaves="2" seed="${o.seed || 7}"/>`
      + `<feDisplacementMap in="SourceGraphic" scale="${rough}" xChannelSelector="R" yChannelSelector="G"/></filter></defs>`
      + `<path class="k-erase-path" d="${d}" fill="none" stroke="${o.board || '#FFFFFF'}" stroke-width="${band}" `
      + `stroke-linecap="round" stroke-linejoin="round" filter="url(#k-rough)"/>`;
    root.appendChild(svg);
    const path = svg.querySelector('path');
    const [drawable] = A.svg.createDrawable(path);
    set(drawable, { draw: '0 0' });
    cue(at, 'erase', dur, 1);
    tl.add(drawable, { draw: ['0 0', '0 1'], duration: dur, ease: 'linear' }, at);
    // the eraser block follows the leading edge of the stroke (tool: false = just the wipe)
    if (o.tool === false) {
      if (o.clearAfter !== false) {
        const targets = o.clear ? $$(o.clear) : [];
        if (targets.length) tl.add(targets, { opacity: 0, duration: 1 }, at + dur);
        tl.add(svg, { opacity: [1, 0], duration: 1 }, at + dur + 2);
      }
      return;
    }
    const er = document.createElement('div');
    er.className = 'k-eraser';
    const ew = Math.round(band * 1.15), eh = Math.round(band * 0.55);
    er.style.width = ew + 'px';
    er.style.height = eh + 'px';
    er.style.marginLeft = -ew / 2 + 'px';  // centre the eraser on the stroke
    er.style.marginTop = -eh / 2 + 'px';
    root.appendChild(er);
    set(er, { opacity: 0 });
    // follow the path's position only — an eraser stays upright, with a little hand wobble
    const mp = A.svg.createMotionPath(path);
    const wob = A.createSeededRandom(o.seed || 5);
    const steps = Math.max(8, Math.round(dur / 120));
    tl.add(er, { opacity: [0, 1], duration: 120 }, at)
      .add(er, { translateX: mp.translateX, translateY: mp.translateY, duration: dur, ease: 'linear' }, at)
      .add(er, { rotate: Array.from({ length: steps }, () => (wob() - 0.5) * 10), duration: dur, ease: 'linear' }, at)
      .add(er, { opacity: [1, 0], duration: 200 }, at + dur);
    if (o.clearAfter !== false) {
      // once wiped, hide the board's content for good so QA and later beats see a clean board
      const targets = o.clear ? $$(o.clear) : [];
      if (targets.length) tl.add(targets, { opacity: 0, duration: 1 }, at + dur);
      tl.add(svg, { opacity: [1, 0], duration: 1 }, at + dur + 2);
    }
  }

  window.K = { timeline, split, rise, typeOn, charsUp, fadeUp, pop, wipe, grow, count, draw, push, exit, grain, set, cue,
    camera, dissolve, scan, blink, glitch, erase };
})();
