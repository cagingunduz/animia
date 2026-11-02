/* Block Horror kit: night-town horror Shorts with blocky R6-style characters, drawn in three.js (no game assets).
   Units are studs (a kid is ~5.4 tall). y is up, the street runs along x, houses face +z, the camera sits at +z.
   Everything is a pure function of time t (seconds): poses snap like a game, lights flicker and die on cue. */
(function () {
  const T = THREE;
  const BK = {};
  let renderer, scene, cam, W, H, capEl;
  const ups = [];                 // per-frame updaters fn(t)
  const lights = [];              // { set(k): 0..1 brightness, die?: t, back?: t }
  let shots = [], caps = [];
  let blackouts = [];             // [[t0, t1], ...]
  const C = {
    skyHorizon: '#212B54', skyTop: '#060917', moon: '#9EB8FF', grassA: '#336B24', grassB: '#42802B',
    asphaltA: '#212126', asphaltB: '#2E2E33', line: '#FAC726', window: '#FCC773', lamp: '#FFBD6B', curb: '#5E5E66',
    monster: '#0D0D0F', red: '#EC1C24',
  };
  BK.C = C;

  // ---------------------------------------------------------------- helpers
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const span = (t, a, b) => clamp((t - a) / Math.max(1e-6, b - a));
  const lerp = (a, b, s) => a + (b - a) * s;
  const smooth = s => s * s * (3 - 2 * s);
  const backOut = (s, k = 2.2) => { s = clamp(s); return 1 + (k + 1) * (s - 1) ** 3 + k * (s - 1) ** 2; };
  function rng(seed) { let s = (seed >>> 0) || 1; return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; }
  const rad = d => d * Math.PI / 180;
  BK.rng = rng; BK.span = span; BK.lerp = lerp; BK.smooth = smooth; BK.backOut = backOut;
  BK.on = fn => ups.push(fn);

  const mats = {};
  function mat(hex, o = {}) {
    const key = hex + JSON.stringify(o);
    if (!mats[key]) mats[key] = o.basic ? new T.MeshBasicMaterial({ color: new T.Color(hex), ...o.extra })
      : new T.MeshLambertMaterial({ color: new T.Color(hex), ...o.extra });
    return mats[key];
  }
  BK.mat = mat;
  function box(w, h, d, m, x = 0, y = 0, z = 0, parent) {
    const g = new T.BoxGeometry(w, h, d), mesh = new T.Mesh(g, typeof m === 'string' ? mat(m) : m);
    mesh.position.set(x, y, z); mesh.castShadow = mesh.receiveShadow = true; (parent || scene).add(mesh); return mesh;
  }
  BK.box = box;
  function vcolorBox(w, h, d, a, b, seed, cell = 2) {         // a box whose top is two noisy tones (grass, asphalt)
    const g = new T.BoxGeometry(w, h, d, Math.max(1, Math.round(w / cell)), 1, Math.max(1, Math.round(d / cell))).toNonIndexed();
    const r = rng(seed), ca = new T.Color(a), cb = new T.Color(b), col = [];
    const p = g.attributes.position;
    for (let i = 0; i < p.count; i += 3) {
      const k = r(), c = ca.clone().lerp(cb, k);
      for (let j = 0; j < 3; j++) col.push(c.r, c.g, c.b);
    }
    g.setAttribute('color', new T.Float32BufferAttribute(col, 3));
    return new T.Mesh(g, new T.MeshLambertMaterial({ vertexColors: true }));
  }

  // ---------------------------------------------------------------- faces (drawn, never catalog faces)
  // 1024 x 578 canvas mapped on the front 130 deg of a head; features in the middle 45%.
  const FACES = {};
  function faceTexture(name, glow) {
    const key = name + (glow ? '-glow' : '');
    if (FACES[key]) return FACES[key];
    const c = document.createElement('canvas'); c.width = 1024; c.height = 578;
    const g = c.getContext('2d'), ink = glow ? '#FFFFFF' : '#111111';
    g.clearRect(0, 0, 1024, 578);
    g.lineCap = 'round'; g.lineJoin = 'round'; g.strokeStyle = ink; g.fillStyle = ink;
    const cx = 512, ey = 245, ex = 82, my = 360;
    const eye = (x, rx, ry, rot = 0) => { g.save(); g.translate(x, ey); g.rotate(rot); g.beginPath(); g.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2); g.fill(); g.restore(); };
    const brow = (x1, y1, x2, y2) => { g.lineWidth = 16; g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke(); };
    const arc = (y, w, h, up) => { g.lineWidth = 18; g.beginPath(); g.moveTo(cx - w, y); g.quadraticCurveTo(cx, y + (up ? h : -h), cx + w, y); g.stroke(); };
    if (glow) {      // the tall thing: hollow tilted eyes, a grin far too wide with gaps between the teeth
      g.fillStyle = '#FFFFFF';
      for (const [x, r] of [[cx - 120, -0.35], [cx + 120, 0.35]]) {
        g.save(); g.translate(x, ey - 10); g.rotate(r); g.beginPath(); g.ellipse(0, 0, 70, 44, 0, 0, Math.PI * 2); g.fill();
        g.fillStyle = '#000000'; g.beginPath(); g.ellipse(0, 0, 50, 26, 0, 0, Math.PI * 2); g.fill(); g.restore(); g.fillStyle = '#FFFFFF';
      }
      g.beginPath(); g.moveTo(cx - 300, my - 40); g.quadraticCurveTo(cx, my + 150, cx + 300, my - 40); g.quadraticCurveTo(cx, my + 60, cx - 300, my - 40); g.fill();
      g.fillStyle = '#000000';
      for (let i = 0; i < 13; i++) { const x = cx - 270 + i * 45; const yb = my - 30 + 70 * Math.sin(Math.PI * (i + 0.5) / 13); g.fillRect(x + 30, my - 60, 8, yb - my + 90); }
    } else {
      switch (name) {
        case 'smile': eye(cx - ex, 26, 34); eye(cx + ex, 26, 34); arc(my - 10, 95, 55, true); break;
        case 'stern': eye(cx - ex, 24, 26); eye(cx + ex, 24, 26); brow(cx - 130, 175, cx - 40, 185); brow(cx + 40, 185, cx + 130, 175); g.lineWidth = 18; g.beginPath(); g.moveTo(cx - 70, my); g.lineTo(cx + 70, my); g.stroke(); break;
        case 'angry': eye(cx - ex, 24, 22); eye(cx + ex, 24, 22); brow(cx - 135, 165, cx - 35, 205); brow(cx + 35, 205, cx + 135, 165); arc(my + 20, 80, 40, false); break;
        case 'determined': eye(cx - ex, 24, 26); eye(cx + ex, 24, 26); brow(cx - 135, 180, cx - 35, 195); brow(cx + 35, 195, cx + 135, 180); g.lineWidth = 18; g.beginPath(); g.moveTo(cx - 60, my + 5); g.quadraticCurveTo(cx + 20, my + 5, cx + 70, my - 15); g.stroke(); break;
        case 'scared': eye(cx - ex, 30, 40); eye(cx + ex, 30, 40); brow(cx - 130, 165, cx - 45, 150); brow(cx + 45, 150, cx + 130, 165); g.beginPath(); g.ellipse(cx, my + 10, 34, 24, 0, 0, Math.PI * 2); g.fill(); break;
        case 'panic': eye(cx - ex, 38, 50); eye(cx + ex, 38, 50); g.fillStyle = '#FFFFFF'; g.beginPath(); g.arc(cx - ex + 8, ey - 14, 11, 0, Math.PI * 2); g.arc(cx + ex + 8, ey - 14, 11, 0, Math.PI * 2); g.fill(); g.fillStyle = ink;
          brow(cx - 135, 150, cx - 50, 135); brow(cx + 50, 135, cx + 135, 150); g.beginPath(); g.ellipse(cx, my + 25, 58, 62, 0, 0, Math.PI * 2); g.fill(); break;
        case 'shock': g.lineWidth = 16; for (const x of [cx - ex, cx + ex]) { g.beginPath(); g.arc(x, ey, 40, 0, Math.PI * 2); g.stroke(); g.beginPath(); g.arc(x, ey, 10, 0, Math.PI * 2); g.fill(); }
          g.beginPath(); g.ellipse(cx, my + 20, 30, 42, 0, 0, Math.PI * 2); g.fill(); break;
        default: eye(cx - ex, 26, 34); eye(cx + ex, 26, 34); arc(my - 10, 95, 55, true);
      }
    }
    const t = new T.CanvasTexture(c); t.colorSpace = T.SRGBColorSpace; t.anisotropy = 4;
    FACES[key] = t; return t;
  }
  BK.FACES = ['smile', 'stern', 'angry', 'scared', 'panic', 'shock', 'determined'];

  // a rounded head: a bevelled cylinder (lathe) with a face decal over its front 130 deg
  function headGeo(r, h, bevel) {
    const pts = [], n = 6;
    pts.push(new T.Vector2(0.001, -h / 2));
    for (let i = 0; i <= n; i++) { const a = -Math.PI / 2 + (Math.PI / 2) * i / n; pts.push(new T.Vector2(r - bevel + bevel * Math.cos(a), -h / 2 + bevel + bevel * Math.sin(a))); }
    for (let i = 0; i <= n; i++) { const a = (Math.PI / 2) * i / n; pts.push(new T.Vector2(r - bevel + bevel * Math.cos(a), h / 2 - bevel + bevel * Math.sin(a))); }
    pts.push(new T.Vector2(0.001, h / 2));
    return new T.LatheGeometry(pts, 32);
  }
  function faceDecal(r, h, glow) {
    const g = new T.CylinderGeometry(r * 1.004, r * 1.004, h * 0.78, 24, 1, true, -rad(65), rad(130));
    const m = new T.MeshBasicMaterial({ map: faceTexture(glow ? 'monster' : 'smile', glow), transparent: true, depthWrite: false });
    if (!glow) { m.dispose(); return new T.Mesh(g, new T.MeshLambertMaterial({ map: faceTexture('smile'), transparent: true, depthWrite: false })); }
    return new T.Mesh(g, m);
  }

  // ---------------------------------------------------------------- rigs: keyed poses that snap with a back ease
  const POSES = {
    idle: { aL: 0, aR: 0, lL: 0, lR: 0, lean: 0, head: 0, side: 0 },
    point: { aL: 0, aR: -90, lL: 0, lR: 0, lean: 0, head: 0, side: 0 },
    flashlight: { aL: 0, aR: -82, lL: 0, lR: 0, lean: 0, head: 0, side: 0 },
    scared: { aL: -120, aR: -120, lL: 10, lR: -10, lean: -6, head: 0, side: 0 },
    cower: { aL: -150, aR: -150, lL: -40, lR: -40, lean: 18, head: 14, side: 0 },
    knock: { aL: 0, aR: -100, lL: 0, lR: 0, lean: 6, head: 0, side: 0 },
    reach: { aL: -80, aR: -80, lL: 0, lR: 0, lean: 8, head: 0, side: 0 },
    hug: { aL: -70, aR: -70, lL: 0, lR: 0, lean: 4, head: 10, side: 0 },
    look_up: { aL: 0, aR: 0, lL: 0, lR: 0, lean: -4, head: -24, side: 0 },
  };
  BK.POSES = Object.keys(POSES);
  function makeRig(o, parts) {
    const rig = { root: parts.root, keys: [], runs: [], o, faceMesh: parts.face, joints: parts.joints, base: { x: o.at[0], z: o.at[1], yaw: o.yaw || 0 } };
    rig.keys.push({ t: -1, pose: Object.assign({}, POSES.idle, o.pose ? POSES[o.pose] : {}), face: o.face || 'smile', yaw: o.yaw || 0, x: o.at[0], z: o.at[1] });
    ups.push(t => applyRig(rig, t));
    return rig;
  }
  function stateAt(rig, t) {
    // the latest key before t, snapping in from the one before it over 0.14 s with a back ease
    let i = 0;
    for (let k = 0; k < rig.keys.length; k++) if (rig.keys[k].t <= t) i = k;
    const cur = rig.keys[i], prev = rig.keys[Math.max(0, i - 1)], s = backOut(span(t, cur.t, cur.t + (cur.dur || 0.14)));
    const pose = {};
    for (const k of Object.keys(POSES.idle)) pose[k] = lerp(prev.pose[k], cur.pose[k], s);
    return { pose, face: cur.face, yaw: lerp(prev.yaw, cur.yaw, s), x: cur.x, z: cur.z };
  }
  function applyRig(rig, t) {
    const st = stateAt(rig, t), J = rig.joints;
    let { x, z, yaw } = st, pose = st.pose;
    // runs: move along a line with a 2.5 Hz run cycle and a 9 deg lean
    for (const r of rig.runs) {
      if (t < r.t0) continue;
      const s = span(t, r.t0, r.t1);
      if (t <= r.t1) {
        x = lerp(r.from[0], r.to[0], s); z = lerp(r.from[1], r.to[1], s);
        yaw = Math.atan2(r.to[0] - r.from[0], r.to[1] - r.from[1]) * 180 / Math.PI;
        const ph = Math.sin((t - r.t0) * 2 * Math.PI * (r.hz || 2.5));
        pose = Object.assign({}, pose, { lL: 52 * ph, lR: -52 * ph, aL: -58 * ph, aR: r.carry ? -52 : 58 * ph, lean: 9 });
        rig.bob = Math.abs(ph) * 0.25;
      } else { x = r.to[0]; z = r.to[1]; rig.bob = 0; }       // after the run the keys decide where it faces
    }
    rig.root.position.set(x, (rig.bob || 0) * (t >= 0 ? 1 : 0), z);
    rig.root.rotation.y = rad(yaw);
    if (J.armL) J.armL.rotation.x = rad(pose.aL); if (J.armR) J.armR.rotation.x = rad(pose.aR);
    if (J.legL) J.legL.rotation.x = rad(pose.lL); if (J.legR) J.legR.rotation.x = rad(pose.lR);
    if (J.upper) J.upper.rotation.x = rad(pose.lean);
    if (J.head) { J.head.rotation.x = rad(pose.head); J.head.rotation.z = rad(pose.side); }
    if (rig.faceMesh && rig.faceName !== st.face && !rig.glow) { rig.faceMesh.material.map = faceTexture(st.face); rig.faceMesh.material.needsUpdate = true; rig.faceName = st.face; }
    if (rig.extra) rig.extra(t, pose);
  }
  // a key: from time t the rig snaps to this pose / face / facing / place (each optional)
  BK.key = function (rig, t, o = {}) {
    const last = rig.keys[rig.keys.length - 1];
    const pose = Object.assign({}, last.pose, typeof o.pose === 'string' ? POSES[o.pose] : (o.pose || {}));
    rig.keys.push({ t, pose, face: o.face || last.face, yaw: o.yaw ?? last.yaw, x: o.at ? o.at[0] : last.x, z: o.at ? o.at[1] : last.z, dur: o.dur });
    rig.keys.sort((a, b) => a.t - b.t);
    return rig;
  };
  BK.run = function (rig, t0, t1, from, to, o = {}) { rig.runs.push({ t0, t1, from, to, ...o }); BK.key(rig, t1, { at: to, yaw: o.endYaw }); return rig; };

  // a kid: R6 proportions (torso 2x2x1, arms 1x2x1 from shoulders at +-1.5, legs 1x1.62x1 + shoes, round head)
  BK.kid = function (o = {}) {
    o = Object.assign({ at: [0, 0], shirt: '#2F6FE0', pants: '#2B2B33', skin: '#F2C9A0', shoe: '#1A1A1E', hair: null, scale: 1 }, o);
    const root = new T.Group(); root.scale.setScalar(o.scale); scene.add(root);
    const upper = new T.Group(); upper.position.y = 2; root.add(upper);
    box(2, 2, 1, o.shirt, 0, 1, 0, upper);
    const head = new T.Group(); head.position.y = 2; upper.add(head);
    const hm = new T.Mesh(headGeo(0.62, 1.22, 0.22), mat(o.skin)); hm.position.y = 0.61; hm.castShadow = true; head.add(hm);
    const face = faceDecal(0.62, 1.22, false); face.position.y = 0.61; face.renderOrder = 2; head.add(face);
    if (o.hair) {                                    // a rounded cap over the top and back of the head
      const cap = new T.Mesh(new T.SphereGeometry(0.69, 24, 12, 0, Math.PI * 2, 0, Math.PI * 0.42), mat(o.hair));
      cap.position.y = 0.86; cap.scale.set(1, 0.9, 1); head.add(cap);
      const back = new T.Mesh(new T.CylinderGeometry(0.67, 0.67, 0.7, 24, 1, true, rad(115), rad(130)), mat(o.hair, { extra: { side: T.DoubleSide } }));
      back.position.y = 0.72; head.add(back);
    }
    const arm = (sx) => { const g = new T.Group(); g.position.set(sx * 1.5, 2, 0); upper.add(g); box(1, 2, 1, sx > 0 ? o.shirt : o.shirt, 0, -1, 0, g); box(1.002, 0.55, 1.002, o.skin, 0, -1.72, 0, g); return g; };
    const leg = (sx) => { const g = new T.Group(); g.position.set(sx * 0.5, 2, 0); root.add(g); box(1, 1.62, 1, o.pants, 0, -0.81, 0, g); box(1.02, 0.38, 1.04, o.shoe, 0, -1.81, 0.02, g); return g; };
    const rig = makeRig(o, { root, face, joints: { upper, head, armL: arm(1), armR: arm(-1), legL: leg(1), legR: leg(-1) } });
    rig.hand = side => (side === 'L' ? rig.joints.armL : rig.joints.armR);
    return rig;
  };

  // the tall thing: about twice a kid's height, thin, matte black, long arms with three long fingers, a glowing face
  BK.monster = function (o = {}) {
    o = Object.assign({ at: [0, 0] }, o);
    const black = mat(C.monster, { extra: {} });
    const root = new T.Group(); scene.add(root);
    const leg = (sx) => { const g = new T.Group(); g.position.set(sx * 0.5, 4.4, 0); root.add(g); box(0.62, 4.4, 0.62, black, 0, -2.2, 0, g); return g; };
    const upper = new T.Group(); upper.position.y = 4.4; root.add(upper);
    box(1.6, 3.4, 0.7, black, 0, 1.7, 0, upper);
    const head = new T.Group(); head.position.y = 3.5; upper.add(head);
    const hm = new T.Mesh(headGeo(0.86, 1.8, 0.3), black); hm.position.y = 0.95; head.add(hm);
    const face = faceDecal(0.86, 1.8, true); face.position.y = 0.95; face.renderOrder = 2; head.add(face);
    const arm = (sx) => {
      const g = new T.Group(); g.position.set(sx * 1.05, 3.2, 0); upper.add(g);
      box(0.42, 5.8, 0.42, black, 0, -2.9, 0, g);
      for (const f of [-0.16, 0, 0.16]) { const fg = new T.Group(); fg.position.set(f, -5.8, 0); fg.rotation.z = rad(f * 60); g.add(fg); box(0.1, 1.1, 0.1, black, 0, -0.55, 0, fg); }
      return g;
    };
    const glowL = new T.PointLight(new T.Color('#DDE6FF'), 18, 9, 1.6); glowL.position.set(0, 1.0, 1.6); head.add(glowL);
    const rim = new T.PointLight(new T.Color('#8FA8FF'), 40, 14, 1.4); rim.position.set(0, 2, -3); upper.add(rim);
    const rig = makeRig(Object.assign({}, o, { face: 'monster' }), { root, face, joints: { upper, head, armL: arm(1), armR: arm(-1), legL: leg(1), legR: leg(-1) } });
    rig.glow = true;
    return rig;
  };
  // bend at the hip toward the camera (deg) between t0 and t1; head snap sideways at t (back ease, 0.14 s)
  BK.bend = function (rig, t0, t1, deg = 72) {
    const prev = rig.extra;
    rig.extra = (t, pose) => { prev && prev(t, pose); rig.joints.upper.rotation.x = rad(pose.lean + deg * smooth(span(t, t0, t1))); };
    return rig;
  };
  BK.headSnap = function (rig, t, deg = 24) {
    const prev = rig.extra;
    rig.extra = (tt, pose) => { prev && prev(tt, pose); rig.joints.head.rotation.z = rad(pose.side + deg * backOut(span(tt, t, t + 0.14))); };
    return rig;
  };

  // ---------------------------------------------------------------- lights
  function registerLight(o) { lights.push(o); return o; }
  // brightness of a light at t: dies at `die` (flickering 0.12 s first), comes back at `back`, off in blackouts
  function level(L, t) {
    if (blackouts.some(([a, b]) => t >= a && t < b) && !L.survive) return 0;
    if (L.onAt != null && t < L.onAt) return 0;
    if (L.die != null && t >= L.die - 0.12 && (L.back == null || t < L.back)) {
      if (t >= L.die) return 0;
      return Math.sin(t * 61) + Math.sin(t * 37) > -0.25 ? 1 : 0;
    }
    return 1;
  }
  BK.lamp = function (x, z, o = {}) {
    const g = new T.Group(); g.position.set(x, 0, z); scene.add(g);
    box(0.5, 13.2, 0.5, '#2A2C33', 0, 6.6, 0, g); box(3.2, 0.4, 0.5, '#2A2C33', 1.4, 13.0, 0, g);
    const bulbOn = mat(C.lamp, { basic: true }), bulbOff = mat('#55565C');
    const bulb = box(1.1, 0.5, 1.1, bulbOn, 2.6, 12.6, 0, g); bulb.castShadow = false;
    const sp = new T.SpotLight(new T.Color(C.lamp), o.power ?? 420, 60, rad(59), 0.45, 1.6);
    sp.position.set(2.6, 12.4, 0); sp.target.position.set(2.6, 0, 0); g.add(sp, sp.target);
    if (o.shadow) { sp.castShadow = true; sp.shadow.mapSize.set(512, 512); sp.shadow.bias = -0.0005; }
    const pool = new T.Mesh(new T.CircleGeometry(7, 32), new T.MeshBasicMaterial({ color: new T.Color(C.lamp), transparent: true, opacity: 0.08, depthWrite: false }));
    pool.rotation.x = -Math.PI / 2; pool.position.set(2.6, 0.06, 0); g.add(pool);
    return registerLight({ group: g, set(k) { sp.intensity = (o.power ?? 420) * k; bulb.material = k > 0 ? bulbOn : bulbOff; pool.visible = k > 0; } });
  };
  // the last safe thing: one big globe light
  BK.globe = function (x, z, o = {}) {
    const g = new T.Group(); g.position.set(x, 0, z); scene.add(g);
    box(0.5, 9, 0.5, '#2A2C33', 0, 4.5, 0, g);
    const on = mat('#FFE2A8', { basic: true }), off = mat('#55565C');
    const ball = new T.Mesh(new T.SphereGeometry(1.1, 24, 16), on); ball.position.y = 9.9; g.add(ball);
    const pl = new T.PointLight(new T.Color('#FFD08A'), o.power ?? 900, 45, 1.5); pl.position.y = 9.9; g.add(pl);
    return registerLight({ group: g, set(k) { pl.intensity = (o.power ?? 900) * k; ball.material = k > 0 ? on : off; } });
  };
  BK.die = (L, t, back) => { L.die = t; if (back != null) L.back = back; return L; };
  // (sound for deaths and the blackout is placed by the scene: BK.sfx('boom', t), BK.sfx('braam', t) ...)
  BK.blackout = (t0, t1) => { blackouts.push([t0, t1]); };

  // ---------------------------------------------------------------- the town
  // a house facing +z; returns its door (a hinged group) and its lights (windows + porch)
  BK.house = function (x, z, o = {}) {
    const r = rng(o.seed || Math.round(x * 7 + z * 13 + 5));
    const w = o.w ?? 12, d = o.d ?? 10, h = o.h ?? 8;
    const wall = o.color ?? ['#B9524A', '#5E7FB8', '#7FA05B', '#D9B25A', '#9C6FB0', '#C98B5A'][Math.floor(r() * 6)];
    const g = new T.Group(); g.position.set(x, 0, z); scene.add(g);
    box(w, h, d, wall, 0, h / 2, 0, g);
    // roof: two slabs
    const roofC = o.roof ?? ['#3A2E2A', '#2E3440', '#45302B'][Math.floor(r() * 3)];
    for (const s of [-1, 1]) { const m = box(w + 1, 0.5, d / 2 + 1.6, roofC, 0, h + 1.6, s * d / 4, g); m.rotation.x = s * rad(32); }
    box(w + 1, 3.4, 0.4, wall, 0, h + 1.4, 0, g).scale.set(1, 1, 1);
    // windows
    const win = mat(C.window, { basic: true }), dark = mat('#14161E');
    const wins = [], shutters = [];
    let shutAt = null;
    for (const [wx, wy] of [[-w * 0.3, h * 0.62], [w * 0.3, h * 0.62], [-w * 0.3, h * 0.25]]) {
      const lit = r() < (o.lit ?? 0.75);
      const m = box(2.2, 2.2, 0.2, lit ? win : dark, wx, wy, d / 2 + 0.05, g); m.castShadow = false;
      box(2.6, 0.3, 0.3, '#E8E2D6', wx, wy - 1.25, d / 2 + 0.1, g);
      if (lit) wins.push(m);
      const sh = box(2.5, 2.5, 0.25, '#3B2A22', wx, wy, d / 2 + 0.22, g); sh.visible = false; shutters.push({ m: sh, y: wy });
    }
    // door on a hinge (left edge), black behind it
    box(2.3, 4.2, 0.1, '#050505', w * 0.25, 2.1, d / 2 + 0.02, g);
    const hinge = new T.Group(); hinge.position.set(w * 0.25 - 1.15, 0, d / 2 + 0.12); g.add(hinge);
    box(2.3, 4.2, 0.2, o.doorColor ?? '#5B3A26', 1.15, 2.1, 0, hinge);
    box(0.2, 0.2, 0.2, '#D8B860', 2.0, 2.1, 0.15, hinge);
    // porch light
    const pl = new T.PointLight(new T.Color(C.lamp), o.porch ?? 70, 14, 1.6); pl.position.set(w * 0.25 + 1.9, 4.8, d / 2 + 0.8); g.add(pl);
    const pb = box(0.5, 0.5, 0.5, mat(C.lamp, { basic: true }), w * 0.25 + 1.9, 4.8, d / 2 + 0.4, g);
    const L = registerLight({ group: g, set(k) { pl.intensity = (o.porch ?? 70) * k; pb.material = k > 0 ? mat(C.lamp, { basic: true }) : mat('#55565C'); for (const m of wins) m.material = k > 0 ? win : dark; } });
    const doorKeys = [[-1, 0]];
    ups.push(t => { let a = 0; for (const [kt, ang] of doorKeys) if (t >= kt) a = ang; const prev = doorKeys.filter(k => k[0] <= t).slice(-2); const s = prev.length > 1 ? backOut(span(t, prev[1][0], prev[1][0] + (prev[1][2] || 0.5))) : 1; hinge.rotation.y = rad(lerp(prev.length > 1 ? prev[0][1] : 0, a, s)); });
    ups.push(t => { for (const sh of shutters) { const on = shutAt != null && t >= shutAt; sh.m.visible = on; if (on) sh.m.position.y = sh.y + 2.6 * (1 - backOut(span(t, shutAt, shutAt + 0.14))); } });
    return {
      group: g, light: L, door: hinge, front: [x + w * 0.25, z + d / 2 + 2],
      // the door swings to `ang` degrees (-100 open, 0 shut) at t; shutters slam over the windows at t
      open: (t, ang = -100, dur = 0.6) => { doorKeys.push([t, ang, dur]); doorKeys.sort((p, q) => p[0] - q[0]); },
      shut: (t) => { shutAt = t; BK.sfx('shutter', t); },
    };
  };
  BK.tree = function (x, z, s = 1, seed = 1) {
    const r = rng(seed), g = new T.Group(); g.position.set(x, 0, z); g.scale.setScalar(s); scene.add(g);
    box(1.2, 6, 1.2, '#4A3324', 0, 3, 0, g);
    for (let i = 0; i < 4; i++) box(4 + r() * 2, 3 + r() * 1.5, 4 + r() * 2, ['#1E4A22', '#245A28', '#1A3F1E'][i % 3], (r() - 0.5) * 2.4, 7 + i * 1.3, (r() - 0.5) * 2.4, g);
    return g;
  };
  BK.fence = function (x0, x1, z) { for (let x = x0; x <= x1; x += 2) box(0.4, 3, 0.4, '#E6E0D2', x, 1.5, z); box(x1 - x0, 0.3, 0.2, '#E6E0D2', (x0 + x1) / 2, 2.2, z); box(x1 - x0, 0.3, 0.2, '#E6E0D2', (x0 + x1) / 2, 1.0, z); };

  // things that keep moving in empty shots
  BK.swing = function (x, z, o = {}) {
    const g = new T.Group(); g.position.set(x, 0, z); scene.add(g);
    for (const s of [-1, 1]) { const p = box(0.4, 9, 0.4, '#8A2E2E', s * 3, 4.5, 0, g); p.rotation.z = s * rad(-8); }
    box(7, 0.4, 0.4, '#8A2E2E', 0, 9, 0, g);
    const seat = new T.Group(); seat.position.y = 9; g.add(seat);
    for (const s of [-0.7, 0.7]) box(0.08, 6, 0.08, '#B0B0B0', s, -3, 0, seat);
    box(1.8, 0.2, 0.8, '#2B2B33', 0, -6, 0, seat);
    const hz = o.hz ?? 0.38, amp = o.amp ?? 12, ph = o.phase ?? 0;
    ups.push(t => { seat.rotation.x = rad(amp * Math.sin(2 * Math.PI * hz * t + ph)); });
    return g;
  };
  BK.rockingChair = function (x, z, o = {}) {
    const g = new T.Group(); g.position.set(x, 0, z); g.rotation.y = rad(o.yaw ?? 0); scene.add(g);
    const c = new T.Group(); g.add(c);
    box(2, 0.3, 2, '#6B4428', 0, 1.6, 0, c); box(2, 2.6, 0.3, '#6B4428', 0, 3, -0.9, c);
    for (const s of [-0.9, 0.9]) { box(0.2, 1.4, 0.2, '#6B4428', s, 0.9, 0.7, c); box(0.2, 1.4, 0.2, '#6B4428', s, 0.9, -0.7, c); box(0.25, 0.25, 3, '#4A2E1B', s, 0.15, 0, c); }
    ups.push(t => { c.rotation.x = rad(9 * Math.sin(2 * Math.PI * 0.75 * t)); });
    return g;
  };
  // a ticking wall clock: the second hand jumps once a second; `from` = the clock time in seconds at t = 0
  BK.clock = function (x, y, z, o = {}) {
    const g = new T.Group(); g.position.set(x, y, z); scene.add(g);
    const face = new T.Mesh(new T.CylinderGeometry(3, 3, 0.4, 48), mat('#F2EFE6')); face.rotation.x = Math.PI / 2; g.add(face);
    const rim = new T.Mesh(new T.TorusGeometry(3, 0.3, 8, 48), mat('#2A2C33')); g.add(rim);
    for (let i = 0; i < 12; i++) { const m = box(0.18, 0.6, 0.1, '#1A1A1E', 0, 0, 0.25, g); const a = i * Math.PI / 6; m.position.set(Math.sin(a) * 2.4, Math.cos(a) * 2.4, 0.25); m.rotation.z = -a; }
    const hand = (len, w, col) => { const p = new T.Group(); p.position.z = 0.3; g.add(p); box(w, len, 0.08, col, 0, len / 2 - 0.3, 0, p); return p; };
    const hr = hand(1.5, 0.28, '#1A1A1E'), mn = hand(2.2, 0.2, '#1A1A1E'), sc = hand(2.5, 0.08, C.red);
    const from = o.from ?? (8 * 3600 + 59 * 60 + 52);
    ups.push(t => { const s = from + Math.floor(t); sc.rotation.z = -(s % 60) / 60 * Math.PI * 2; mn.rotation.z = -((s / 60) % 60) / 60 * Math.PI * 2; hr.rotation.z = -((s / 3600) % 12) / 12 * Math.PI * 2; });
    return g;
  };
  // a cap left behind, still rocking
  BK.cap = function (x, z, t0, o = {}) {
    const g = new T.Group(); g.position.set(x, 0.3, z); scene.add(g);
    const c = new T.Mesh(new T.SphereGeometry(0.7, 16, 8, 0, Math.PI * 2, 0, Math.PI / 2), mat(o.color || '#C8322E')); g.add(c);
    box(1.2, 0.08, 0.9, o.color || '#C8322E', 0, 0, 0.8, g);
    ups.push(t => { g.visible = t >= t0; const k = Math.exp(-(t - t0) * 0.8); g.rotation.z = rad(18 * k * Math.sin((t - t0) * 7)); });
    return g;
  };
  // a flashlight in a rig's hand: spot + faint beam, clicks on at t0 (dies with the lights if die is set)
  BK.flashlight = function (rig, t0, o = {}) {
    const hand = rig.hand ? rig.hand(o.hand || 'R') : rig.root;
    // the torch sits in the hand and points along the arm (the arm's -y), so it aims wherever the arm aims
    const holder = new T.Group(); holder.position.set(0, -2.05, 0); hand.add(holder);
    box(0.36, 1.0, 0.36, '#2A2C33', 0, -0.25, 0, holder);
    const sp = new T.SpotLight(new T.Color('#FFF1D6'), o.power ?? 260, 60, rad(17), 0.35, 1.4);
    sp.position.set(0, -0.8, 0); sp.target.position.set(0, -12, 0); holder.add(sp, sp.target);
    sp.castShadow = !!o.shadow; if (o.shadow) sp.shadow.mapSize.set(512, 512);
    const beam = new T.Mesh(new T.ConeGeometry(2.6, 11, 24, 1, true), new T.MeshBasicMaterial({ color: new T.Color('#FFF1D6'), transparent: true, opacity: 0.06, depthWrite: false, side: T.DoubleSide, blending: T.AdditiveBlending }));
    beam.position.set(0, -6.3, 0); holder.add(beam);               // apex up at the lens, opening along -y
    BK.sfx('click', t0);
    return registerLight({ onAt: t0, set(k) { sp.intensity = (o.power ?? 260) * k; beam.visible = k > 0; } });
  };

  BK.town = function (o = {}) {
    const len = o.length ?? 200;
    const grass = vcolorBox(len + 200, 1, 260, C.grassA, C.grassB, 3, 3); grass.position.set(0, -0.5, -40); grass.receiveShadow = true; scene.add(grass);
    const road = vcolorBox(len + 200, 0.2, 12, C.asphaltA, C.asphaltB, 7, 1.5); road.position.set(0, 0.05, 8); road.receiveShadow = true; scene.add(road);
    box(len + 200, 0.06, 0.35, mat(C.line, { basic: false }), 0, 0.17, 8);
    box(len + 200, 0.4, 4, '#4E4F56', 0, 0.2, 0);
    for (const s of [2.1, 13.9]) box(len + 200, 0.5, 0.25, C.curb, 0, 0.25, s);
    return { street: 8, sidewalk: 0 };
  };

  // ---------------------------------------------------------------- camera shots (vertical fov) and captions
  // shot: { t0, t1, pos, look, fov, push (0..1 toward look over the shot), slide [dx, dy, dz] }
  BK.shot = (t0, t1, o) => Object.assign({ t0, t1, fov: 50, push: 0.08, slide: [0, 0, 0] }, o);
  BK.shots = list => { shots = list.slice().sort((a, b) => a.t0 - b.t0); };
  // a point that follows a rig (its head, chest or feet) plus an offset: use it as a shot's pos or look
  BK.at = function (rig, part = 'head', off = [0, 0, 0]) {
    return () => {
      const j = part === 'head' ? rig.joints.head : part === 'chest' ? rig.joints.upper : rig.root;
      j.updateWorldMatrix(true, false);
      const v = new T.Vector3(0, part === 'head' ? 0.7 * (rig.glow ? 1.4 : 1) : part === 'chest' ? 1.2 : 0, 0).applyMatrix4(j.matrixWorld);
      return [v.x + off[0], v.y + off[1], v.z + off[2]];
    };
  };
  function placeCamera(t) {
    const s = shots.find(x => t >= x.t0 && t < x.t1) || shots[shots.length - 1];
    if (!s) return;
    const k = smooth(span(t, s.t0, s.t1));
    const val = v => (typeof v === 'function' ? v(t) : v);
    const p = new T.Vector3(...val(s.pos)), l = new T.Vector3(...val(s.look));
    p.lerp(l, (s.push || 0) * k).add(new T.Vector3(...s.slide).multiplyScalar(k));
    cam.fov = s.fov; cam.updateProjectionMatrix(); cam.position.copy(p); cam.lookAt(l.add(new T.Vector3(...s.slide).multiplyScalar(k * 0.5)));
  }
  BK.captions = (list) => { caps = list; };   // [[t, 'Word', tEnd, isKey], ...]
  function placeCaption(t) {
    if (!capEl) return;
    let cur = null; for (const c of caps) if (t >= c[0]) cur = c;
    if (!cur || t > cur[2]) { capEl.style.opacity = 0; return; }
    if (capEl.textContent !== cur[1]) capEl.textContent = cur[1];
    capEl.style.color = cur[3] ? C.red : '#FFFFFF';
    capEl.style.opacity = 1;
  }

  // ---------------------------------------------------------------- sky, moon and the render loop
  let skyU, moonL, moonMesh, stars, fill;
  const FILL = 1.0;
  BK.init = function (o) {
    W = o.width; H = o.height; capEl = o.caption || null;
    renderer = new T.WebGLRenderer({ canvas: o.canvas, antialias: true, preserveDrawingBuffer: true });
    renderer.setSize(W, H, false); renderer.outputColorSpace = T.SRGBColorSpace; renderer.toneMapping = T.NoToneMapping;
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = T.PCFShadowMap;
    scene = new T.Scene();
    cam = new T.PerspectiveCamera(50, W / H, 0.1, 1200);
    skyU = { uH: { value: new T.Color(C.skyHorizon) }, uT: { value: new T.Color(C.skyTop) }, uK: { value: 1 } };
    const sky = new T.Mesh(new T.SphereGeometry(600, 32, 16), new T.ShaderMaterial({
      side: T.BackSide, depthWrite: false, uniforms: skyU,
      vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: 'uniform vec3 uH; uniform vec3 uT; uniform float uK; varying vec3 vP; void main(){ gl_FragColor = vec4(mix(uH, uT, smoothstep(0.0, 0.55, vP.y)) * uK, 1.0); #include <colorspace_fragment> }',
    }));
    scene.add(sky);
    const r = rng(9), sp = [];
    for (let i = 0; i < 1100; i++) { const a = r() * Math.PI * 2, e = 0.08 + r() * 1.4; sp.push(Math.cos(a) * Math.cos(e) * 560, Math.sin(e) * 560, Math.sin(a) * Math.cos(e) * 560); }
    stars = new T.Points(new T.BufferGeometry().setAttribute('position', new T.Float32BufferAttribute(sp, 3)), new T.PointsMaterial({ color: 0xffffff, size: 2.4, sizeAttenuation: false }));
    scene.add(stars);
    moonL = new T.DirectionalLight(new T.Color(C.moon), 0.55); moonL.position.set(-80, 120, 60); scene.add(moonL);
    moonMesh = new T.Mesh(new T.SphereGeometry(14, 24, 16), new T.MeshBasicMaterial({ color: new T.Color('#DCE6FF') })); moonMesh.position.set(-200, 260, -420); scene.add(moonMesh);
    scene.add(BK.hemi = new T.HemisphereLight(new T.Color('#4A5580'), new T.Color('#1A1A14'), 0.6));
    fill = new T.DirectionalLight(new T.Color('#FFE9D2'), FILL); cam.add(fill); fill.position.set(2, 3, 0); fill.target.position.set(0, 0, -10); cam.add(fill.target); scene.add(cam);
    BK.three = { renderer, scene, camera: cam };
    return BK;
  };
  BK.probe = function (times) {
    const errs = [];
    for (const t of times) { try { for (const f of ups) f(t); placeCamera(t); placeCaption(t); } catch (e) { errs.push(`at ${t.toFixed(1)} s: ${(e && e.message) || e}`); if (errs.length >= 4) break; } }
    return errs;
  };
  BK.renderAt = function (ms) {
    const t = ms / 1000;
    for (const f of ups) f(t);
    const dark = blackouts.some(([a, b]) => t >= a && t < b);
    // blackout: every practical light dies; a trace of moonlight keeps the roofs readable against the stars
    skyU.uK.value = dark ? 0.8 : 1; moonL.intensity = dark ? 0.22 : 0.55; moonMesh.visible = !dark; BK.hemi.intensity = dark ? 0.14 : 0.6;
    fill.intensity = dark ? 0 : FILL;
    for (const L of lights) L.set(level(L, t));
    placeCamera(t); placeCaption(t);
    renderer.render(scene, cam);
  };
  // ---------------------------------------------------------------- more verbs
  // sound cues for the sound designer (read from window.__kCues after load)
  window.__kCues = window.__kCues || [];
  BK.sfx = (kind, t) => { window.__kCues.push({ t: Math.round(t * 1000), kind, dur: 0, n: 1 }); };
  // gone: the rig is there until t, then it isn't (snap); leave something behind with BK.cap
  BK.vanish = function (rig, t) { ups.push(tt => { if (tt >= t) rig.root.visible = false; else rig.root.visible = true; }); return rig; };
  // pound on a door: the right arm hits forward three times a second from t0 to t1
  BK.knock = function (rig, t0, t1) {
    const prev = rig.extra;
    rig.extra = (t, pose) => { prev && prev(t, pose); if (t >= t0 && t <= t1) rig.joints.armR.rotation.x = rad(-100 + 22 * Math.abs(Math.sin((t - t0) * Math.PI * 3))); };
    for (let k = t0; k < t1; k += 1 / 3) BK.sfx('knock', k + 0.05);
    return rig;
  };
  // a crowd of townspeople running home: n kids from random spots near `around` to doors
  BK.crowd = function (t0, t1, targets, o = {}) {
    const r = rng(o.seed || 17), out = [];
    const shirts = ['#E0533A', '#3FA34D', '#E8C13A', '#7A55C8', '#2FA6C8', '#D9558F', '#8A8A92'];
    targets.forEach((to, i) => {
      const from = [to[0] + (r() - 0.5) * 24, 10 + r() * 6];
      const k = BK.kid({ at: from, shirt: shirts[i % shirts.length], pants: '#2B2B33', hair: r() < 0.6 ? '#2A1B12' : null, scale: r() < 0.3 ? 0.8 : 1, face: 'scared' });
      const a = t0 + r() * 0.3, b = Math.min(t1, a + 1.2 + r() * 0.8);
      BK.run(k, a, b, from, to);
      BK.vanish(k, b + 0.05);          // through the door
      out.push(k);
    });
    return out;
  };
  // narration timing: W.t(id, 'word', n) = when that word starts; W.line(id) = {start, end}; W.end
  BK.timing = function (tm) {
    const norm = w => String(w).toLowerCase().replace(/[^a-z0-9']/g, '');
    const by = {}; for (const l of tm.lines) by[l.id] = l;
    return {
      end: tm.end, lines: tm.lines,
      line: id => by[id] || { start: 0, end: 0, words: [] },
      t: (id, w, n = 1) => { const l = by[id]; if (!l) return 0; let k = 0; for (const x of l.words || []) if (norm(x.w) === norm(w) && ++k === n) return x.start; return l.start; },
    };
  };
  window.BK = BK;
})();
