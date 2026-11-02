// Exploded Teardown kit for the Animave Style Studio (window.TD): a three.js studio packshot of a product built from
// parametric parts in millimetres, taken apart along one axis, with anchored labels and perspective dimension lines.
// After the look of the lemo-opuscar "teardown" style (github.com/lemomo-ai/lemo-opuscar, MIT); made for CPU rendering.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/examples/jsm/geometries/RoundedBoxGeometry.js';
import { clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, vnoise, TAU, env, monotone } from '../common/lib.js';

export { THREE, clamp, lerp, seg, ss, eo, ei, eio, back, spring, hash, mulberry, vnoise, TAU, env };
export let SW = 1080, SH = 1920;
export function setScreen(w, h) { SW = w; SH = h; }
export const INK = '#f1efe9';
export let ACCENT = '#ff6b3d';

// —— the studio ——
// one per film: a WebGL renderer drawing into its own canvas, copied onto the page's 2D canvas each frame
export function studio(o = {}) {
  ACCENT = o.accent || ACCENT;
  const rs = o.scale ?? .75, canvas = document.createElement('canvas'); canvas.width = Math.round(SW * rs); canvas.height = Math.round(SH * rs);   // the 3D picture at 75 % (CPU), upscaled; type stays sharp on the 2D canvas
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(1); renderer.setSize(canvas.width, canvas.height, false);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = o.exposure ?? 1.0;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(renderer), .04).texture;
  scene.environmentIntensity = o.env ?? .55;
  const cam = new THREE.PerspectiveCamera(o.fov ?? 28, SW / SH, 1, 20000);
  // warm key from above front (casts the soft contact shadow), cool rim behind, soft top
  const key = new THREE.DirectionalLight(o.keyCol || '#fff1de', o.key ?? 2.4);
  key.position.set(-300, 900, 600); key.castShadow = true;
  key.shadow.mapSize.set(1024, 1024); key.shadow.radius = 6; key.shadow.bias = -.0005;
  const sc = key.shadow.camera; sc.left = -400; sc.right = 400; sc.top = 400; sc.bottom = -400; sc.near = 10; sc.far = 3000;
  const rim = new THREE.DirectionalLight(o.rimCol || '#a9c4ff', o.rim ?? 1.6); rim.position.set(500, 300, -700);
  const top = new THREE.HemisphereLight('#ffffff', '#202020', o.top ?? .35);
  scene.add(key, key.target, rim, top);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(6000, 6000), new THREE.ShadowMaterial({ opacity: o.shadow ?? .45 }));
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
  const bg = o.bg || ['#34363a', '#0d0e10'];
  const S = {
    scene, cam, renderer, key, rim, top, floor, canvas,
    add(...objs) { for (const x of objs) { scene.add(x); x.traverse?.(m => { if (m.isMesh) { m.castShadow = true; m.receiveShadow = true; } }); } return objs[0]; },
    // render the 3D picture onto the page's 2D context (background sweep first)
    render(ctx) {
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
      const g = ctx.createRadialGradient(SW / 2, SH * .42, 0, SW / 2, SH * .5, Math.hypot(SW, SH) * .62);
      g.addColorStop(0, bg[0]); g.addColorStop(1, bg[1]); ctx.fillStyle = g; ctx.fillRect(0, 0, SW, SH);
      // keep the key light's shadow box on what the camera looks at
      renderer.render(scene, cam); ctx.imageSmoothingQuality = 'high'; ctx.drawImage(canvas, 0, 0, SW, SH);
      const v = ctx.createRadialGradient(SW / 2, SH / 2, Math.min(SW, SH) * .45, SW / 2, SH / 2, Math.hypot(SW, SH) * .58);
      v.addColorStop(0, 'rgba(0,0,0,0)'); v.addColorStop(1, 'rgba(0,0,0,.45)'); ctx.fillStyle = v; ctx.fillRect(0, 0, SW, SH);
      ctx.restore();
    },
  };
  return S;
}

// —— the camera: keys [[t, azimuthDeg, elevationDeg, distance, [tx, ty, tz]], ...], monotone (no overshoot) ——
export function orbit(keys) {
  const f = [1, 2, 3].map(j => monotone(keys.map(k => [k[0], k[j]])));
  const tg = [0, 1, 2].map(j => monotone(keys.map(k => [k[0], (k[4] || [0, 0, 0])[j]])));
  return (S, t) => {
    const az = f[0](t) * Math.PI / 180, el = f[1](t) * Math.PI / 180, d = f[2](t), T = tg.map(q => q(t));
    S.cam.position.set(T[0] + Math.sin(az) * Math.cos(el) * d, T[1] + Math.sin(el) * d, T[2] + Math.cos(az) * Math.cos(el) * d);
    S.cam.lookAt(T[0], T[1], T[2]);
    S.rim.position.set(T[0] - Math.sin(az) * 700, T[1] + 300, T[2] - Math.cos(az) * 700);   // the rim follows the camera
    S.key.target.position.set(T[0], T[1], T[2]); S.key.position.set(T[0] - 300, T[1] + 900, T[2] + 600);
  };
}

// —— materials ——
const _mats = new Map();
export const mat = {
  plastic: (color = '#d9d6cf', rough = .6) => new THREE.MeshPhysicalMaterial({ color, roughness: rough, metalness: 0, sheen: .3, sheenRoughness: .8, clearcoat: .05 }),
  metal: (color = '#c8ccd2', rough = .28) => new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: 1 }),
  anodized: (color = '#5a6270', rough = .4) => new THREE.MeshPhysicalMaterial({ color, roughness: rough, metalness: .85, clearcoat: .3 }),
  rubber: (color = '#2a2a2c', rough = .9) => new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: 0 }),
  glass: (color = '#e8f2ff', rough = .05) => new THREE.MeshPhysicalMaterial({ color, roughness: rough, metalness: 0, transmission: .9, thickness: 2, ior: 1.5, transparent: true, opacity: .55 }),
  screen: (color = '#0a0c10', glow = '#000000', k = 0) => new THREE.MeshPhysicalMaterial({ color, roughness: .15, metalness: 0, clearcoat: 1, emissive: glow, emissiveIntensity: k }),
  emissive: (color = '#ffb35a', k = 2) => new THREE.MeshStandardMaterial({ color: '#111', emissive: color, emissiveIntensity: k }),
  copper: () => new THREE.MeshStandardMaterial({ color: '#c8865a', roughness: .35, metalness: 1 }),
  gold: () => new THREE.MeshStandardMaterial({ color: '#e0b860', roughness: .3, metalness: 1 }),
  chip: () => new THREE.MeshStandardMaterial({ color: '#1c1d20', roughness: .55, metalness: .1 }),
};

// —— parts (millimetres; each returns a THREE.Group sitting on y = 0, centred in x and z) ——
const G = (...m) => { const g = new THREE.Group(); m.forEach(x => g.add(x)); return g; };
const mesh = (geo, m) => { const x = new THREE.Mesh(geo, m); x.castShadow = x.receiveShadow = true; return x; };
// a rounded block (housings, lids, batteries, buttons, chips)
export function block(w, h, d, { r = 1, m = mat.plastic() } = {}) { const x = mesh(new RoundedBoxGeometry(w, h, d, 3, Math.min(r, w / 2 - .01, h / 2 - .01, d / 2 - .01)), m); x.position.y = h / 2; return G(x); }
// an open shell: a box with walls and a floor (the bottom case), wall thickness t
export function shell(w, h, d, { t = 2, r = 4, m = mat.plastic('#3a3d42', .55) } = {}) {
  const s = new THREE.Shape(); const rr = Math.min(r, w / 2, d / 2);
  s.moveTo(-w / 2 + rr, -d / 2); s.lineTo(w / 2 - rr, -d / 2); s.quadraticCurveTo(w / 2, -d / 2, w / 2, -d / 2 + rr); s.lineTo(w / 2, d / 2 - rr); s.quadraticCurveTo(w / 2, d / 2, w / 2 - rr, d / 2); s.lineTo(-w / 2 + rr, d / 2); s.quadraticCurveTo(-w / 2, d / 2, -w / 2, d / 2 - rr); s.lineTo(-w / 2, -d / 2 + rr); s.quadraticCurveTo(-w / 2, -d / 2, -w / 2 + rr, -d / 2);
  const hole = new THREE.Path(); const iw = w - 2 * t, id = d - 2 * t, ir = Math.max(.5, rr - t);
  hole.moveTo(-iw / 2 + ir, -id / 2); hole.lineTo(iw / 2 - ir, -id / 2); hole.quadraticCurveTo(iw / 2, -id / 2, iw / 2, -id / 2 + ir); hole.lineTo(iw / 2, id / 2 - ir); hole.quadraticCurveTo(iw / 2, id / 2, iw / 2 - ir, id / 2); hole.lineTo(-iw / 2 + ir, id / 2); hole.quadraticCurveTo(-iw / 2, id / 2, -iw / 2, id / 2 - ir); hole.lineTo(-iw / 2, -id / 2 + ir); hole.quadraticCurveTo(-iw / 2, -id / 2, -iw / 2 + ir, -id / 2);
  const ws = s.clone(); ws.holes.push(hole);
  const wall = mesh(new THREE.ExtrudeGeometry(ws, { depth: h, bevelEnabled: true, bevelSize: .4, bevelThickness: .4, bevelSegments: 2, curveSegments: 10 }), m); wall.rotation.x = -Math.PI / 2;
  const base = mesh(new THREE.ExtrudeGeometry(s, { depth: t, bevelEnabled: true, bevelSize: .4, bevelThickness: .4, bevelSegments: 2, curveSegments: 10 }), m); base.rotation.x = -Math.PI / 2;
  return G(wall, base);
}
// a flat plate with round holes [[x, z, r], ...] (frames, shields, plates)
export function plate(w, d, t = 1.5, { r = 2, holes = [], m = mat.metal('#b8bcc2', .4) } = {}) {
  const s = new THREE.Shape(); const rr = Math.min(r, w / 2, d / 2);
  s.moveTo(-w / 2 + rr, -d / 2); s.lineTo(w / 2 - rr, -d / 2); s.quadraticCurveTo(w / 2, -d / 2, w / 2, -d / 2 + rr); s.lineTo(w / 2, d / 2 - rr); s.quadraticCurveTo(w / 2, d / 2, w / 2 - rr, d / 2); s.lineTo(-w / 2 + rr, d / 2); s.quadraticCurveTo(-w / 2, d / 2, -w / 2, d / 2 - rr); s.lineTo(-w / 2, -d / 2 + rr); s.quadraticCurveTo(-w / 2, -d / 2, -w / 2 + rr, -d / 2);
  for (const [x, z, hr] of holes) { const p = new THREE.Path(); p.absarc(x, -z, hr, 0, TAU, true); s.holes.push(p); }
  const x = mesh(new THREE.ExtrudeGeometry(s, { depth: t, bevelEnabled: false, curveSegments: 16 }), m); x.rotation.x = -Math.PI / 2;
  return G(x);
}
// a circuit board painted in code: traces, vias, pads, silkscreen (seeded); chips = [[x, z, w, d, h], ...] placed on it
export function board(w, d, { t = 1.6, seed = 1, color = '#1f5b3a', chips = [], ppm = 6 } = {}) {
  const W = Math.min(2048, Math.ceil(w * ppm)), H = Math.min(2048, Math.ceil(d * ppm)), c = document.createElement('canvas'); c.width = W; c.height = H;
  const x = c.getContext('2d'), R = mulberry(seed), k = W / w;
  x.fillStyle = color; x.fillRect(0, 0, W, H);
  const cu = '#d9a35c', mask = 'rgba(120,220,150,.18)';
  x.lineCap = 'round'; x.lineJoin = 'round';
  for (let i = 0; i < Math.round(w * d / 90); i++) {   // traces: 45° routing
    let px = R() * W, py = R() * H; x.strokeStyle = mask; x.lineWidth = (.25 + R() * .35) * k; x.beginPath(); x.moveTo(px, py);
    for (let s = 0; s < 4; s++) { const a = Math.floor(R() * 8) * Math.PI / 4, l = (3 + R() * 18) * k; px += Math.cos(a) * l; py += Math.sin(a) * l; x.lineTo(px, py); }
    x.stroke(); x.fillStyle = '#c8b070'; x.beginPath(); x.arc(px, py, .45 * k, 0, TAU); x.fill();
  }
  for (const [cx, cz, cw, cd] of chips) {   // pads around each chip footprint
    const X = (cx + w / 2) * k, Y = (cz + d / 2) * k; x.fillStyle = cu;
    const n = Math.max(2, Math.round(cw / 1.2));
    for (let i = 0; i < n; i++) { const u = (i + .5) / n - .5; x.fillRect(X + u * cw * k - .2 * k, Y - (cd / 2 + .9) * k, .4 * k, .8 * k); x.fillRect(X + u * cw * k - .2 * k, Y + (cd / 2 + .1) * k, .4 * k, .8 * k); }
    x.strokeStyle = 'rgba(240,240,230,.75)'; x.lineWidth = .15 * k; x.strokeRect(X - (cw / 2 + 1.3) * k, Y - (cd / 2 + 1.3) * k, (cw + 2.6) * k, (cd + 2.6) * k);
  }
  for (let i = 0; i < 6; i++) { x.fillStyle = cu; x.beginPath(); x.arc((R() * .9 + .05) * W, (R() * .9 + .05) * H, 1.4 * k, 0, TAU); x.fill(); x.fillStyle = '#111'; x.beginPath(); x.arc(0, 0, 0, 0, 0); x.fill(); }
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
  const top = new THREE.MeshPhysicalMaterial({ map: tex, roughness: .6, metalness: .05, clearcoat: .25, clearcoatRoughness: .5 });
  const edge = new THREE.MeshStandardMaterial({ color: '#c9b98a', roughness: .7 });
  const b = mesh(new THREE.BoxGeometry(w, t, d), [edge, edge, top, edge, edge, edge]); b.position.y = t / 2;
  const grp = G(b);
  for (const [cx, cz, cw, cd, ch = 1] of chips) { const ci = block(cw, ch, cd, { r: .3, m: mat.chip() }); ci.position.set(cx, t, cz); grp.add(ci); }
  return grp;
}
// a cylinder (cells, motors, knobs, capacitors, lenses' barrels)
export function cyl(r, h, { m = mat.metal(), seg = 48, axis = 'y' } = {}) { const x = mesh(new THREE.CylinderGeometry(r, r, h, seg), m); if (axis === 'x') { x.rotation.z = Math.PI / 2; x.position.y = r; } else if (axis === 'z') { x.rotation.x = Math.PI / 2; x.position.y = r; } else x.position.y = h / 2; return G(x); }
// a screw: head + shaft, length l, head radius r
export function screw(l = 6, r = 1.4, { m = mat.metal('#9aa0a8', .3) } = {}) {
  const head = mesh(new THREE.CylinderGeometry(r, r, r * .7, 24), m); head.position.y = l + r * .35;
  const slot = mesh(new THREE.BoxGeometry(r * 1.4, r * .3, r * .3), mat.rubber('#222')); slot.position.y = l + r * .72;
  const sh = mesh(new THREE.CylinderGeometry(r * .5, r * .45, l, 16), m); sh.position.y = l / 2;
  return G(head, slot, sh);
}
// a lens: a glass disc in a black ring
export function lens(r = 6, h = 3) { const ring = mesh(new THREE.TorusGeometry(r, h * .35, 12, 48), mat.rubber('#151515', .5)); ring.rotation.x = Math.PI / 2; ring.position.y = h / 2; const gl = mesh(new THREE.CylinderGeometry(r, r, h * .6, 48), mat.glass()); gl.position.y = h / 2; return G(ring, gl); }
// a flat ribbon / flex cable from a to b ([x, y, z]) of width w
export function ribbon(a, b, w = 6, { m = new THREE.MeshStandardMaterial({ color: '#c88a2a', roughness: .5, metalness: .2, side: THREE.DoubleSide }) } = {}) {
  const A = new THREE.Vector3(...a), B = new THREE.Vector3(...b), mid = A.clone().lerp(B, .5).add(new THREE.Vector3(0, A.distanceTo(B) * .25, 0));
  const curve = new THREE.QuadraticBezierCurve3(A, mid, B), pts = curve.getPoints(30), pos = [], idx = [];
  pts.forEach((p, i) => { pos.push(p.x - w / 2, p.y, p.z, p.x + w / 2, p.y, p.z); if (i) { const k = i * 2; idx.push(k - 2, k - 1, k, k - 1, k + 1, k); } });
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); geo.setIndex(idx); geo.computeVertexNormals();
  return G(mesh(geo, m));
}
// a key cap (for keyboards, remotes, buttons): w x d footprint, height h
export function keycap(w = 18, d = 18, h = 8, { m = mat.plastic('#e8e4da', .65) } = {}) {
  const k = mesh(new RoundedBoxGeometry(w, h, d, 3, 2), m); k.position.y = h / 2; k.scale.set(1, 1, 1);
  const top = mesh(new RoundedBoxGeometry(w * .72, 1, d * .72, 2, .4), m); top.position.y = h + .2;
  return G(k, top);
}
// a fan: a hub and n blades of radius r
export function fan(r = 20, n = 7, { m = mat.plastic('#202226', .5) } = {}) {
  const grp = G(); const hub = cyl(r * .32, 6, { m }); grp.add(hub);
  for (let i = 0; i < n; i++) { const b = mesh(new THREE.BoxGeometry(r * .7, .8, r * .28), m); b.position.set(Math.cos(i / n * TAU) * r * .62, 3, Math.sin(i / n * TAU) * r * .62); b.rotation.y = -i / n * TAU; b.rotation.x = .35; grp.add(b); }
  return grp;
}
// the same part repeated on a grid: rows x cols, pitch [px, pz]
export function grid(make, rows, cols, px, pz) { const g = G(), list = []; for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) { const p = make(r, c); p.position.set((c - (cols - 1) / 2) * px, 0, (r - (rows - 1) / 2) * pz); g.add(p); list.push(p); } g.userData.items = list; return g; }

// —— the explode ——
// layers = [{ obj, y (assembled height of its base, mm), gap (how far it lifts when apart) }], bottom first.
// Returns set(k, t): k 0 = assembled, 1 = apart; layers leave top first with a stagger, land bottom first.
export function stack(layers, { stagger = .18, float = .6 } = {}) {
  const n = layers.length;
  return (k, t = 0) => {
    layers.forEach((L, i) => {
      const order = (n - 1 - i) / Math.max(1, n - 1);                    // the top layer moves first
      const u = clamp((k * (1 + stagger * (n - 1)) - order * stagger * (n - 1)));
      const e = eio(u), fl = k > .98 ? Math.sin(t * 1.3 + i * 1.7) * float : 0;
      L.obj.position.y = L.y + (L.gap ?? 0) * e + fl;
    });
  };
}
// a wave across repeated parts (keys, cells, tiles): each item's delay grows with its distance from a corner
export function wave(items, k, { lift = 20, spread = .5, from = [-1e4, -1e4] } = {}) {
  const ds = items.map(p => Math.hypot(p.position.x - from[0], p.position.z - from[1])), mx = Math.max(...ds), mn = Math.min(...ds);
  items.forEach((p, i) => { const d = (ds[i] - mn) / Math.max(1e-6, mx - mn); p.userData.y0 ??= p.position.y; p.position.y = p.userData.y0 + lift * eio(clamp((k * (1 + spread) - d * spread))); });
}

// —— overlay: labels and dimension lines anchored to 3D points, drawn on the 2D context after S.render ——
export function project(S, p) { const v = (p.isVector3 ? p.clone() : new THREE.Vector3(...p)).project(S.cam); return [(v.x * .5 + .5) * SW, (-v.y * .5 + .5) * SH, v.z]; }
export function worldOf(obj, local = [0, 0, 0]) { obj.updateWorldMatrix(true, false); return new THREE.Vector3(...local).applyMatrix4(obj.matrixWorld); }
// a label: an accent index, a name, one spec line; the leader runs from a dot on the part to a column on one side
// a = 0..1 appearance (dot, then the leader grows, then the text slides in); side 'left' | 'right'; y = column height (0..1 of the screen)
export function label(ctx, S, at, { idx = '01', name = '', spec = '', side = 'right', y = null, a = 1 } = {}) {
  if (a <= .001) return;
  const [px, py, z] = project(S, at); if (z > 1) return;
  const k = SW / 1080, colX = side === 'right' ? SW * .64 : SW * .36, ty = y != null ? y * SH : py;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  const d = clamp(a / .25), l = clamp((a - .2) / .4), tx = clamp((a - .5) / .5);
  ctx.globalAlpha = d; ctx.fillStyle = ACCENT; ctx.beginPath(); ctx.arc(px, py, 6 * k, 0, TAU); ctx.fill();
  ctx.strokeStyle = 'rgba(241,239,233,.85)'; ctx.lineWidth = 2 * k;
  const ex = lerp(px, colX, l), ey = lerp(py, ty, l);
  ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(ex, ey); if (l >= 1) ctx.lineTo(colX + (side === 'right' ? 40 : -40) * k, ty); ctx.stroke();
  if (tx > 0) {
    const sx = (side === 'right' ? 1 : -1), x0 = colX + sx * (52 + (1 - eo(tx)) * 10) * k; ctx.globalAlpha = eo(tx);
    ctx.textAlign = side === 'right' ? 'left' : 'right'; ctx.textBaseline = 'middle';
    ctx.font = `500 ${26 * k}px JetBrainsMono`; ctx.fillStyle = ACCENT; ctx.fillText(idx, x0, ty - 22 * k);
    ctx.font = `700 ${36 * k}px Inter`; ctx.fillStyle = INK; ctx.shadowColor = 'rgba(0,0,0,.7)'; ctx.shadowBlur = 10 * k; ctx.fillText(name, x0, ty + 14 * k);
    if (spec) { ctx.font = `500 ${25 * k}px JetBrainsMono`; ctx.fillStyle = 'rgba(241,239,233,.62)'; ctx.fillText(spec, x0, ty + 52 * k); }
  }
  ctx.restore();
}
// a dimension line between two 3D points, with ticks and the measurement on a small dark plate; a = 0..1 draws it in
export function dimension(ctx, S, p1, p2, text, { a = 1, off = [0, 0, 0] } = {}) {
  if (a <= .001) return;
  const P1 = new THREE.Vector3(...(p1.isVector3 ? p1.toArray() : p1)).add(new THREE.Vector3(...off)), P2 = new THREE.Vector3(...(p2.isVector3 ? p2.toArray() : p2)).add(new THREE.Vector3(...off));
  const [x1, y1] = project(S, P1), [x2, y2] = project(S, P2), k = SW / 1080, u = eio(clamp(a / .7));
  const mx = lerp(x1, x2, .5), my = lerp(y1, y2, .5), hx = (x2 - x1) / 2 * u, hy = (y2 - y1) / 2 * u, ang = Math.atan2(y2 - y1, x2 - x1), nx = -Math.sin(ang) * 12 * k, ny = Math.cos(ang) * 12 * k;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.strokeStyle = ACCENT; ctx.lineWidth = 2.5 * k;
  ctx.beginPath(); ctx.moveTo(mx - hx, my - hy); ctx.lineTo(mx + hx, my + hy);
  ctx.moveTo(mx - hx - nx, my - hy - ny); ctx.lineTo(mx - hx + nx, my - hy + ny); ctx.moveTo(mx + hx - nx, my + hy - ny); ctx.lineTo(mx + hx + nx, my + hy + ny); ctx.stroke();
  const ta = clamp((a - .6) / .4);
  if (ta > 0) {
    let r = ang; if (r > Math.PI / 2) r -= Math.PI; if (r < -Math.PI / 2) r += Math.PI;
    ctx.translate(mx, my); ctx.rotate(r); ctx.globalAlpha = ta; ctx.font = `500 ${26 * k}px JetBrainsMono`;
    const tw = ctx.measureText(text).width + 22 * k; ctx.fillStyle = 'rgba(10,11,13,.85)'; ctx.beginPath(); ctx.roundRect(-tw / 2, -50 * k, tw, 36 * k, 6 * k); ctx.fill();
    ctx.fillStyle = INK; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(text, 0, -32 * k);
  }
  ctx.restore();
}
// a title card in screen space (top third), a = 0..1
export function title(ctx, text, sub = '', a = 1) {
  if (a <= .001) return; const k = SW / 1080;
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = a; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.shadowColor = 'rgba(0,0,0,.6)'; ctx.shadowBlur = 16 * k;
  ctx.font = `700 ${72 * k}px Inter`; ctx.fillStyle = INK; ctx.fillText(text, SW / 2, SH * .14);
  if (sub) { ctx.font = `500 ${28 * k}px JetBrainsMono`; ctx.fillStyle = ACCENT; ctx.fillText(sub, SW / 2, SH * .14 + 66 * k); }
  ctx.restore();
}
// subtitles: a centred strip in the bottom 12 %, soft shadow, no box
export function subtitles(T, o = {}) {
  const subs = [];
  for (const L of T.lines) {
    if (L.nocap || !L.words || !L.words.length) continue;
    const parts = L.text.split(/(?<=[,.;:!?…])\s+/).reduce((acc, p) => { const last = acc[acc.length - 1]; if (last != null && (last + ' ' + p).length <= (o.maxChars ?? 38)) acc[acc.length - 1] = last + ' ' + p; else acc.push(p); return acc; }, []);
    const ws = L.words, tot = parts.reduce((a, p) => a + p.length, 0); let c0 = 0;
    for (const p of parts) { const f0 = c0 / tot, f1 = (c0 + p.length) / tot; c0 += p.length; const at = f => ws[Math.min(ws.length - 1, Math.floor(f * ws.length))].s; subs.push({ t0: (f0 === 0 ? ws[0].s : at(f0)) - .1, t1: f1 >= .999 ? ws[ws.length - 1].e + .4 : at(f1), text: p }); }
  }
  for (let i = 0; i < subs.length - 1; i++) subs[i].t1 = Math.min(Math.max(subs[i].t1, subs[i].t0 + 1.4), subs[i + 1].t0 - .05);
  return {
    subs,
    draw(ctx, t) {
      const s = subs.find(s => t >= s.t0 && t < s.t1); if (!s) return; const k = SW / 1080;
      const a = Math.min(ss(seg(t, s.t0, s.t0 + .15)), 1 - ss(seg(t, s.t1 - .15, s.t1)));
      ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.globalAlpha = a; ctx.font = `500 ${44 * k}px Inter`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      let rows = [s.text]; if (ctx.measureText(s.text).width > SW * .86) { const w = s.text.split(' '), m = Math.ceil(w.length / 2); rows = [w.slice(0, m).join(' '), w.slice(m).join(' ')]; }
      ctx.shadowColor = 'rgba(0,0,0,.85)'; ctx.shadowBlur = 14 * k; ctx.fillStyle = INK;
      rows.forEach((r, i) => ctx.fillText(r, SW / 2, SH * .9 - (rows.length - 1 - i) * 56 * k));
      ctx.restore();
    },
  };
}
// sound events: [{ t, type, v, pan }] with type in lift (layers rising), land (a layer seating), clack (plastic),
// click (a switch), tick (a label), hiss (a dimension line), thud (the case), whoosh (a camera dive)
export function sounds(list) { return list.map(e => ({ t: +(+e.t).toFixed(3), type: e.type, v: e.v ?? 1, pan: e.pan ?? 0, d: e.d })).filter(e => isFinite(e.t)).sort((a, b) => a.t - b.t); }
