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

  // Words rise out of masks.
  function rise(tl, sel, at, o) {
    o = o || {};
    split(sel, 'words');
    const t = $$(sel).flatMap((el) => Array.from(el.querySelectorAll('.k-w')));
    // Hidden words are also transparent, so layout QA does not count them as visible text.
    set(t, { y: '110%', opacity: 0 });
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
    tl.add(t, { opacity: [0, 1], duration: 1, delay: A.stagger(o.perChar || 40) }, at || 0);
  }

  // Characters drop in with a little lift.
  function charsUp(tl, sel, at, o) {
    o = o || {};
    split(sel, 'chars');
    const t = $$(sel).flatMap((el) => Array.from(el.querySelectorAll('.k-c')));
    set(t, { opacity: 0, y: o.dy || 40 });
    tl.add(t, { opacity: [0, 1], y: [o.dy || 40, 0], duration: o.duration || 500, delay: A.stagger(o.stagger || 25) }, at || 0);
  }

  function fadeUp(tl, sel, at, o) {
    o = o || {};
    const t = $$(sel);
    set(t, { opacity: 0, y: o.dy || 40 });
    tl.add(t, { opacity: [0, 1], y: [o.dy || 40, 0], duration: o.duration || 600, delay: A.stagger(o.stagger || 80) }, at || 0);
  }

  // Overshoot pop (badges, icons, numbers).
  function pop(tl, sel, at, o) {
    o = o || {};
    const t = $$(sel);
    set(t, { opacity: 0, scale: o.from || 0.6 });
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
    tl.add(t, { clipPath: c, duration: o.duration || 600, ease: o.ease || 'inOutQuart', delay: A.stagger(o.stagger || 0) }, at || 0);
  }

  // Grow a bar / line from one side. axis 'x' | 'y'
  function grow(tl, sel, at, o) {
    o = o || {};
    const t = $$(sel);
    const prop = (o.axis || 'x') === 'x' ? 'scaleX' : 'scaleY';
    t.forEach((el) => { el.style.transformOrigin = o.origin || ((o.axis || 'x') === 'x' ? 'left center' : 'center bottom'); });
    set(t, { [prop]: 0 });
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
    (tl._kHooks = tl._kHooks || []).push(render);
    tl.add({ k: 0 }, { k: 1, duration: dur, ease: 'linear' }, start);  // keeps the timeline long enough
  }

  // Draw SVG strokes (path/line/circle/polyline…).
  function draw(tl, sel, at, o) {
    o = o || {};
    const d = A.svg.createDrawable(sel);
    set(d, { draw: '0 0' });
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

  window.K = { timeline, split, rise, typeOn, charsUp, fadeUp, pop, wipe, grow, count, draw, push, exit, grain, set };
})();
