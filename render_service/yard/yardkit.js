/* Yard kit for three.js: the cut-away yard explainer set (a soil block cut open at y = 0, a striped lawn on top,
   the house behind), authored in kit coordinates: x right, y back (away from the camera), z up, metres.
   Every object lives under YK.world, which turns kit z into three's up. Textures come from <img id="tx_NAME">
   tags in the page, so the renderer waits for them before the first frame. */
(function () {
  const T = THREE;
  const YK = {};
  let renderer, scene, world, cam, W, H;
  const updaters = [];            // fn(t seconds), run every frame before the camera and the render
  let shots = [], captions = [], capEl = null;

  // ---------------------------------------------------------------- helpers
  function rng(seed) { let s = seed >>> 0 || 1; return () => { s = (s * 16807) % 2147483647; return (s - 1) / 2147483646; }; }
  const R = rng(3);
  const clamp = (x, a, b) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, s) => a + (b - a) * s;
  function ease(s, kind = 'inout') {
    s = clamp(s, 0, 1);
    if (kind === 'out') return 1 - (1 - s) ** 3;
    if (kind === 'in') return s ** 3;
    if (kind === 'back') { const c = 1.70158; return 1 + (c + 1) * (s - 1) ** 3 + c * (s - 1) ** 2; }
    if (kind === 'linear') return s;
    return s < 0.5 ? 4 * s ** 3 : 1 - (-2 * s + 2) ** 3 / 2;
  }
  const span = (t, t0, t1) => clamp((t - t0) / Math.max(1e-6, t1 - t0), 0, 1);
  // kit (x, y, z) -> three
  const V = (x, y, z) => new T.Vector3(x, z, -y);
  function hash3(x, y, z) { const s = Math.sin(x * 127.1 + y * 311.7 + z * 74.7) * 43758.5453; return s - Math.floor(s); }
  function vnoise(x, y, z) {
    const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z), xf = x - xi, yf = y - yi, zf = z - zi;
    const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf), w = zf * zf * (3 - 2 * zf);
    let o = 0;
    for (let a = 0; a < 2; a++) for (let b = 0; b < 2; b++) for (let c = 0; c < 2; c++)
      o += hash3(xi + a, yi + b, zi + c) * (a ? u : 1 - u) * (b ? v : 1 - v) * (c ? w : 1 - w);
    return o;
  }
  YK.ease = ease; YK.span = span; YK.lerp = lerp; YK.clamp = clamp; YK.rng = rng;

  // ---------------------------------------------------------------- textures and materials
  const TEX = {};
  function tex(name, rx = 1, ry = 1) {
    const img = document.getElementById('tx_' + name);
    if (!img) throw new Error('missing texture tx_' + name);
    const list = TEX[name] || (TEX[name] = []);
    const t = new T.Texture(img);
    t.colorSpace = T.SRGBColorSpace; t.wrapS = t.wrapT = T.RepeatWrapping; t.anisotropy = 8; t.repeat.set(rx, ry);
    list.push(t);
    const ready = () => list.forEach(x => { x.needsUpdate = true; });
    if (img.complete && img.naturalWidth) t.needsUpdate = true; else img.addEventListener('load', ready, { once: true });
    return t;
  }

  const TRI_V = `
    varying vec3 vWP; varying vec3 vWN;`;
  const TRI_V_MAIN = `
    #ifdef USE_INSTANCING
      mat4 mW = modelMatrix * instanceMatrix;
    #else
      mat4 mW = modelMatrix;
    #endif
    vWP = (mW * vec4(transformed, 1.0)).xyz; vWN = normalize(mat3(mW) * objectNormal);`;
  const TRI_F = `
    varying vec3 vWP; varying vec3 vWN;
    uniform float uScale; uniform vec3 uTint; uniform float uSat; uniform float uBright;
    // one texture read per pixel, projected along the face's main axis (CPU rendering pays per read)
    vec2 triUV() {
      vec3 n = abs(vWN);
      return n.x >= max(n.y, n.z) ? vWP.zy : (n.y >= n.z ? vWP.xz : vWP.xy);
    }
    vec3 triS(sampler2D s, float k) { return texture2D(s, triUV() * k).rgb; }
    vec3 grade(vec3 c, float sat, float bright, vec3 tint) {
      float l = dot(c, vec3(0.2126, 0.7152, 0.0722)); return mix(vec3(l), c, sat) * bright * tint;
    }`;

  // triplanar, world-space texture (no stretching however a part is sized): plaster, wood, pavers, mud, leaves
  function triMat(o) {
    const m = new T.MeshStandardMaterial({ map: tex(o.tex), roughness: o.rough ?? 0.9, metalness: 0, envMapIntensity: o.env ?? 0.7 });
    m.onBeforeCompile = sh => {
      Object.assign(sh.uniforms, {
        uScale: { value: 1 / o.size }, uTint: { value: new T.Vector3(...(o.tint || [1, 1, 1])) },
        uSat: { value: o.sat ?? 1 }, uBright: { value: o.bright ?? 1 },
      });
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>' + TRI_V)
        .replace('#include <begin_vertex>', '#include <begin_vertex>' + TRI_V_MAIN);
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>' + TRI_F)
        .replace('#include <map_fragment>', 'diffuseColor.rgb *= grade(triS(map, uScale), uSat, uBright, uTint);');
    };
    m.customProgramCacheKey = () => 'tri';
    return m;
  }

  // pits: organic holes dug into the soil block. The block itself is never rebuilt: its lawn and cut face are
  // discarded per pixel inside any pit, and each pit draws its own walls (a loft of rings) behind the cut.
  const MAXPIT = 4, MAXRING = 8;
  const PIT_U = {
    uPitN: { value: 0 },
    uPitA: { value: Array.from({ length: MAXPIT }, () => new T.Vector4()) },   // cx, cy, rx, ry
    uPitB: { value: Array.from({ length: MAXPIT }, () => new T.Vector4()) },   // exponent, depth scale, ring count, -
    uPitW: { value: Array.from({ length: MAXPIT }, () => new T.Vector4()) },   // wobble amplitudes (k = 2, 3, 5)
    uPitP: { value: Array.from({ length: MAXPIT }, () => new T.Vector4()) },   // wobble phases
    uPitR: { value: Array.from({ length: MAXPIT * MAXRING }, () => new T.Vector2()) }, // rings (scale, z)
  };
  const PIT_GLSL = `
    #define MAXPIT ${MAXPIT}
    #define MAXRING ${MAXRING}
    uniform int uPitN; uniform vec4 uPitA[MAXPIT]; uniform vec4 uPitB[MAXPIT]; uniform vec4 uPitW[MAXPIT]; uniform vec4 uPitP[MAXPIT];
    uniform vec2 uPitR[MAXPIT * MAXRING];
    float pitRho(int i, vec2 p) {
      vec2 d = (p - uPitA[i].xy) / uPitA[i].zw;
      float a = atan(d.y, d.x), e = uPitB[i].x;
      float nn = pow(pow(abs(d.x), e) + pow(abs(d.y), e), 1.0 / e);
      float f = 1.0 + uPitW[i].x * sin(2.0 * a + uPitP[i].x) + uPitW[i].y * sin(3.0 * a + uPitP[i].y) + uPitW[i].z * sin(5.0 * a + uPitP[i].z);
      return nn / f;
    }
    float pitH(int i, float r) {
      int n = int(uPitB[i].z); float s = uPitB[i].y;
      vec2 prev = uPitR[i * MAXRING];
      for (int k = 1; k < MAXRING; k++) {
        if (k >= n) break;
        vec2 L = uPitR[i * MAXRING + k];
        if (r >= L.x) return mix(prev.y, L.y, (prev.x - r) / max(1e-4, prev.x - L.x)) * s;
        prev = L;
      }
      return prev.y * s;
    }
    bool inPit(vec3 wp) {          // wp in three coords: kit (x, y, z) = (wp.x, -wp.z, wp.y)
      for (int i = 0; i < MAXPIT; i++) {
        if (i >= uPitN) break;
        if (uPitB[i].y < 0.001) continue;
        float r = pitRho(i, vec2(wp.x, -wp.z));
        if (r < uPitR[i * MAXRING].x && wp.y > pitH(i, r) + 0.003) return true;
      }
      return false;
    }`;

  // the ground: one material for the soil block, pit walls and the lawn. Faces that point up at lawn height are
  // mown grass with 1.6 m stripes; everything else is cut soil, dark in the first 35 cm and warmer clay below 2.5 m.
  // uWet darkens the soil around a point of the cut face (water soaking in): (u, z, radius, strength).
  const GROUND_U = { uWet: { value: new T.Vector4(0, -0.8, 0, 0) } };
  function groundMat(cutsPits) {
    const m = new T.MeshStandardMaterial({ map: tex('excavated_soil_wall'), roughness: 0.95, metalness: 0, envMapIntensity: 0.55 });
    const grass = tex('leafy_grass');
    m.onBeforeCompile = sh => {
      Object.assign(sh.uniforms, PIT_U, {
        uScale: { value: 1 / 3.2 }, uTint: { value: new T.Vector3(0.72, 0.58, 0.48) }, uSat: { value: 1.05 }, uBright: { value: 1.0 },
        gMap: { value: grass }, uWet: GROUND_U.uWet,
      });
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>' + TRI_V)
        .replace('#include <begin_vertex>', '#include <begin_vertex>' + TRI_V_MAIN);
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>' + TRI_F + PIT_GLSL + `
        uniform sampler2D gMap; uniform vec4 uWet;`)
        .replace('#include <clipping_planes_fragment>', '#include <clipping_planes_fragment>\n' + (cutsPits ? 'if (inPit(vWP)) discard;' : ''))
        .replace('#include <map_fragment>', `
          vec3 n = normalize(vWN);
          float z = vWP.y;
          float isGrass = step(0.7, n.y) * step(-0.06, z);
          vec3 raw = isGrass > 0.5 ? texture2D(gMap, vWP.xz / 1.2).rgb : triS(map, uScale);
          vec3 soil = grade(raw, uSat, uBright, uTint);
          float topF = clamp((z + 0.45) / 0.30, 0.0, 1.0);
          soil = mix(soil, soil * vec3(0.42, 0.33, 0.27), topF);
          float deepF = clamp((-2.2 - z) / 1.8, 0.0, 1.0);
          soil = mix(soil, soil * vec3(1.0, 0.82, 0.66), deepF);
          float wd = length((vec2(vWP.x, z) - uWet.xy) * vec2(0.75, 1.0)) + 0.35 * (raw.r - 0.5);
          float wet = uWet.w * (1.0 - smoothstep(uWet.z - 0.12, uWet.z, wd));
          soil *= mix(1.0, 0.45, wet * step(0.7, n.z));
          vec3 g = grade(raw, 1.5, 0.85, vec3(0.42, 0.85, 0.22));
          float stripe = mod(floor(vWP.x / 1.6), 2.0);
          g *= mix(vec3(1.0), vec3(0.66, 0.78, 0.55), stripe);
          diffuseColor.rgb *= mix(soil, g, isGrass);`)
        .replace('#include <roughnessmap_fragment>', '#include <roughnessmap_fragment>\nroughnessFactor = mix(0.95, 1.0, step(0.7, normalize(vWN).y));');
    };
    m.customProgramCacheKey = () => 'ground' + (cutsPits ? 'cut' : '');
    return m;
  }
  // shadows of the block: the same per-pixel pit cut, or the lawn would shade the inside of every hole
  function groundDepthMat() {
    const m = new T.MeshDepthMaterial({ depthPacking: T.RGBADepthPacking });
    m.onBeforeCompile = sh => {
      Object.assign(sh.uniforms, PIT_U);
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 vWP;')
        .replace('#include <begin_vertex>', '#include <begin_vertex>\nvWP = (modelMatrix * vec4(transformed, 1.0)).xyz;');
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vWP;' + PIT_GLSL)
        .replace('#include <clipping_planes_fragment>', '#include <clipping_planes_fragment>\nif (inPit(vWP)) discard;');
    };
    m.customProgramCacheKey = () => 'grounddepth';
    return m;
  }
  // water: clear teal, darker with depth, see-through head on (the cut face shows what's inside), more solid at a glance
  const WATER_U = { uAlgae: { value: 0 } };
  function waterMat() {
    const m = new T.MeshStandardMaterial({ roughness: 0.04, metalness: 0.0, transparent: true, envMapIntensity: 1.3, depthWrite: false, side: T.DoubleSide });
    m.onBeforeCompile = sh => {
      Object.assign(sh.uniforms, WATER_U);
      sh.vertexShader = sh.vertexShader.replace('#include <common>', '#include <common>' + TRI_V)
        .replace('#include <begin_vertex>', '#include <begin_vertex>' + TRI_V_MAIN);
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nvarying vec3 vWP; varying vec3 vWN; uniform float uAlgae;')
        .replace('#include <color_fragment>', `#include <color_fragment>
          float dz = clamp((vWP.y + 0.1) / -1.2, 0.0, 1.0);
          vec3 clearC = mix(vec3(0.09, 0.5, 0.62), vec3(0.02, 0.17, 0.34), dz);
          vec3 greenC = mix(vec3(0.04, 0.14, 0.02), vec3(0.45, 0.58, 0.14), 0.5 + 0.5 * sin(vWP.x * 3.1 + vWP.z * 2.3));
          diffuseColor.rgb = mix(clearC, greenC, uAlgae);`)
        .replace('#include <opaque_fragment>', `
          float facing = 1.0 - abs(dot(normalize(normal), normalize(vViewPosition)));
          diffuseColor.a = mix(mix(0.22, 0.7, smoothstep(0.0, 0.8, facing)), 0.75, uAlgae);
          #include <opaque_fragment>`);
    };
    m.customProgramCacheKey = () => 'water';
    return m;
  }

  const MAT = {};
  const YK_plastic = (rgb, rough) => new T.MeshStandardMaterial({ color: new T.Color(...rgb), roughness: rough, envMapIntensity: 0.8 });
  function mats() {
    Object.assign(MAT, {
      ground: groundMat(true), pitWall: groundMat(false), groundDepth: groundDepthMat(),
      plaster: triMat({ tex: 'plastered_wall', size: 2.5, tint: [0.66, 0.63, 0.6], sat: 0.4, bright: 1.05, rough: 0.9 }),
      trim: new T.MeshStandardMaterial({ color: new T.Color(0.92, 0.92, 0.9), roughness: 0.55 }),
      shutter: new T.MeshStandardMaterial({ color: new T.Color(0.018, 0.035, 0.09), roughness: 0.75, envMapIntensity: 0.4 }),
      glass: new T.MeshStandardMaterial({ color: new T.Color(0.05, 0.07, 0.1), roughness: 0.06, metalness: 0.2, envMapIntensity: 1.6 }),
      concrete: triMat({ tex: 'square_concrete_pavers', size: 3, sat: 0.2, bright: 0.9, rough: 0.9 }),
      pavers: triMat({ tex: 'square_concrete_pavers', size: 1.6, sat: 0.6, bright: 1.0, rough: 0.85 }),
      wood: triMat({ tex: 'dark_wooden_planks', size: 1.4, tint: [1.0, 0.86, 0.7], sat: 0.8, bright: 1.7, rough: 0.8 }),
      brick: new T.MeshStandardMaterial({ color: new T.Color(0.42, 0.16, 0.1), roughness: 0.9 }),
      mud: triMat({ tex: 'brown_mud', size: 1.6, tint: [0.75, 0.6, 0.48], sat: 1.0, bright: 1.0, rough: 0.95 }),
      clod: triMat({ tex: 'excavated_soil_wall', size: 1.2, tint: [0.62, 0.5, 0.4], rough: 0.95 }),
      leaves: triMat({ tex: 'leafy_grass', size: 0.7, tint: [0.32, 0.55, 0.16], sat: 1.4, bright: 0.85, rough: 0.85 }),
      leaves2: triMat({ tex: 'leafy_grass', size: 0.6, tint: [0.24, 0.42, 0.13], sat: 1.3, bright: 0.8, rough: 0.85 }),
      bark: new T.MeshStandardMaterial({ color: new T.Color(0.2, 0.13, 0.08), roughness: 0.95 }),
      hose: new T.MeshStandardMaterial({ color: new T.Color(0.05, 0.38, 0.1), roughness: 0.35 }),
      water: waterMat(),
      stream: new T.MeshStandardMaterial({ color: new T.Color(0.6, 0.8, 0.95), roughness: 0.05, transparent: true, opacity: 0.6, envMapIntensity: 1.5 }),
      liner: new T.MeshStandardMaterial({ color: new T.Color(0.035, 0.035, 0.04), roughness: 0.45, side: T.DoubleSide }),
      arrow: new T.MeshStandardMaterial({ color: new T.Color(0.95, 0.97, 1.0), roughness: 0.35, emissive: new T.Color(0.25, 0.27, 0.3) }),
      arrowBlue: new T.MeshStandardMaterial({ color: new T.Color(0.2, 0.5, 1.0), roughness: 0.35, emissive: new T.Color(0.04, 0.12, 0.3) }),
      pvc: YK_plastic([0.85, 0.85, 0.82], 0.4), steel: new T.MeshStandardMaterial({ color: new T.Color(0.6, 0.62, 0.64), roughness: 0.35, metalness: 0.85 }),
      rubber: new T.MeshStandardMaterial({ color: new T.Color(0.035, 0.035, 0.04), roughness: 0.6 }),
      copper: new T.MeshStandardMaterial({ color: new T.Color(0.75, 0.4, 0.22), roughness: 0.3, metalness: 0.9 }),
      stone: triMat({ tex: 'excavated_soil_wall', size: 0.5, tint: [0.62, 0.6, 0.56], sat: 0.15, bright: 1.3, rough: 0.85 }),
      gravelBed: triMat({ tex: 'dirt', size: 0.8, tint: [0.55, 0.53, 0.5], sat: 0.2, bright: 1.0, rough: 0.95 }),
      flow: new T.MeshStandardMaterial({ color: new T.Color(0.55, 0.78, 0.95), roughness: 0.05, transparent: true, opacity: 0.75, envMapIntensity: 1.5 }),
      air: new T.MeshStandardMaterial({ color: new T.Color(0.95, 0.97, 1), roughness: 0.3, transparent: true, opacity: 0.55 }),
      bubble: new T.MeshStandardMaterial({ color: new T.Color(0.85, 0.95, 1), roughness: 0.05, transparent: true, opacity: 0.55, envMapIntensity: 1.6 }),
      speck: new T.MeshStandardMaterial({ color: new T.Color(0.05, 0.05, 0.05), roughness: 0.6 }),
      rain: new T.MeshBasicMaterial({ color: new T.Color(0.7, 0.8, 0.95), transparent: true, opacity: 0.45 }),
      arrowRed: new T.MeshStandardMaterial({ color: new T.Color(0.95, 0.2, 0.15), roughness: 0.35, emissive: new T.Color(0.25, 0.04, 0.03) }),
      sand: triMat({ tex: 'dirt', size: 1.2, tint: [1.15, 0.95, 0.7], sat: 0.6, bright: 1.25, rough: 0.95 }),
    });
    MAT.roof = (rx, ry) => { const m = new T.MeshStandardMaterial({ map: tex('clay_roof_tiles', rx, ry), roughness: 0.8, envMapIntensity: 0.6 }); return m; };
    return MAT;
  }
  YK.MAT = MAT;
  YK.mat = (o) => triMat(o);

  // ---------------------------------------------------------------- geometry
  // a batch merges many static parts that share one material into one mesh (one draw call per pass)
  const batches = new Map();
  function batch(mat) {
    if (!batches.has(mat)) batches.set(mat, []);
    return batches.get(mat);
  }
  function addGeo(geo, mat, matrix) {
    const g = geo.index ? geo.toNonIndexed() : geo;
    if (matrix) g.applyMatrix4(matrix);
    if (!g.attributes.uv) g.setAttribute('uv', new T.Float32BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2));
    batch(mat).push(g);
  }
  function flush() {
    for (const [mat, list] of batches) {
      let n = 0; list.forEach(g => { n += g.attributes.position.count; });
      const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3), uv = new Float32Array(n * 2);
      let o = 0;
      for (const g of list) {
        pos.set(g.attributes.position.array, o * 3); nor.set(g.attributes.normal.array, o * 3); uv.set(g.attributes.uv.array, o * 2);
        o += g.attributes.position.count;
      }
      const geo = new T.BufferGeometry();
      geo.setAttribute('position', new T.BufferAttribute(pos, 3)); geo.setAttribute('normal', new T.BufferAttribute(nor, 3));
      geo.setAttribute('uv', new T.BufferAttribute(uv, 2));
      const mesh = new T.Mesh(geo, mat); mesh.castShadow = mesh.receiveShadow = true; world.add(mesh);
    }
    batches.clear();
  }
  const M4 = () => new T.Matrix4();
  // a static box: size (sx, sy, sz), loc = bottom centre (origin 'bottom'), 'top' or 'center'
  function box(size, loc, mat, origin = 'bottom', rotZ = 0) {
    const [sx, sy, sz] = size, [x, y, z] = loc;
    const g = new T.BoxGeometry(sx, sy, sz);
    const dz = origin === 'bottom' ? sz / 2 : origin === 'top' ? -sz / 2 : 0;
    const m = M4().makeTranslation(x, y, z + dz); if (rotZ) m.multiply(M4().makeRotationZ(rotZ));
    addGeo(g, mat, m);
  }
  YK.box = box;
  // a moving box: its own mesh, pivot at the given origin
  function boxMesh(size, loc, mat, origin = 'bottom') {
    const [sx, sy, sz] = size;
    const g = new T.BoxGeometry(sx, sy, sz);
    g.translate(0, 0, origin === 'bottom' ? sz / 2 : origin === 'top' ? -sz / 2 : 0);
    const m = new T.Mesh(g, mat); m.position.set(...loc); m.castShadow = m.receiveShadow = true; world.add(m); return m;
  }
  YK.boxMesh = boxMesh;

  // a prism: a closed outline [(u, z), ...] in the cut face (u = x), running from y0 back to y1.
  function prismGeo(poly, y0, y1) {
    const pts = poly.map(([u, z]) => new T.Vector2(u, z));
    const area = pts.reduce((a, p, i) => { const q = pts[(i + 1) % pts.length]; return a + p.x * q.y - q.x * p.y; }, 0);
    if (area < 0) pts.reverse();
    const P = [], N = [];
    const tri = (a, b, c, n) => {
      const ab = new T.Vector3().subVectors(b, a), ac = new T.Vector3().subVectors(c, a), cr = ab.cross(ac);
      if (cr.dot(n) < 0) [b, c] = [c, b];
      for (const v of [a, b, c]) { P.push(v.x, v.y, v.z); N.push(n.x, n.y, n.z); }
    };
    const tris = T.ShapeUtils.triangulateShape(pts, []);
    const v3 = (p, y) => new T.Vector3(p.x, y, p.y);
    for (const [a, b, c] of tris) {
      tri(v3(pts[a], y0), v3(pts[b], y0), v3(pts[c], y0), new T.Vector3(0, -1, 0));
      tri(v3(pts[a], y1), v3(pts[b], y1), v3(pts[c], y1), new T.Vector3(0, 1, 0));
    }
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i], q = pts[(i + 1) % pts.length];
      const du = q.x - p.x, dz = q.y - p.y, L = Math.hypot(du, dz); if (L < 1e-6) continue;
      const n = new T.Vector3(dz / L, 0, -du / L);
      tri(v3(p, y0), v3(q, y0), v3(q, y1), n); tri(v3(p, y0), v3(q, y1), v3(p, y1), n);
    }
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.Float32BufferAttribute(P, 3)); g.setAttribute('normal', new T.Float32BufferAttribute(N, 3));
    g.setAttribute('uv', new T.Float32BufferAttribute(new Float32Array(P.length / 3 * 2), 2));
    return g;
  }
  YK.prismGeo = prismGeo;


  // clip a closed polygon to z <= level
  function clipBelow(poly, level) {
    const out = [];
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i], b = poly[(i + 1) % poly.length], ina = a[1] <= level, inb = b[1] <= level;
      if (ina) out.push(a);
      if (ina !== inb) { const s = (level - a[1]) / (b[1] - a[1]); out.push([a[0] + (b[0] - a[0]) * s, level]); }
    }
    return out;
  }

  // noisy blob (clods, piles, tree crowns)
  function blobGeo(r, squash = 1, noise = 0.3, detail = 2, seed = 1) {
    const g = new T.IcosahedronGeometry(r, detail);
    const p = g.attributes.position, v = new T.Vector3();
    for (let i = 0; i < p.count; i++) {
      v.fromBufferAttribute(p, i);
      const k = 1 + noise * (vnoise(v.x * 2.1 / r + seed, v.y * 2.1 / r, v.z * 2.1 / r) - 0.5) * 2;
      v.multiplyScalar(k); v.z *= squash; p.setXYZ(i, v.x, v.y, v.z);
    }
    g.computeVertexNormals();
    return smoothNormals(g);
  }
  YK.blobGeo = blobGeo;
  // the icosahedron is unindexed (flat faces): average the normals of vertices that share a position
  function smoothNormals(g) {
    const p = g.attributes.position, n = g.attributes.normal, acc = new Map(), key = i => `${p.getX(i).toFixed(5)},${p.getY(i).toFixed(5)},${p.getZ(i).toFixed(5)}`;
    for (let i = 0; i < p.count; i++) { const k = key(i), a = acc.get(k) || [0, 0, 0]; a[0] += n.getX(i); a[1] += n.getY(i); a[2] += n.getZ(i); acc.set(k, a); }
    for (let i = 0; i < p.count; i++) { const a = acc.get(key(i)), L = Math.hypot(a[0], a[1], a[2]) || 1; n.setXYZ(i, a[0] / L, a[1] / L, a[2] / L); }
    n.needsUpdate = true; return g;
  }

  // ---------------------------------------------------------------- the set
  const BLOCK = { w: 30, d: 16, h: 16 };
  function soilBlock() {
    const { w, d, h } = BLOCK;
    const m = new T.Mesh(prismGeo([[-w / 2, -h], [w / 2, -h], [w / 2, 0], [-w / 2, 0]], 0, d), MAT.ground);
    m.customDepthMaterial = MAT.groundDepth; m.castShadow = m.receiveShadow = true; world.add(m);
  }

  // ---- pit maths, mirrored in PIT_GLSL
  const pits = [];
  function wobbleF(P, a) { return 1 + P.amp[0] * Math.sin(2 * a + P.ph[0]) + P.amp[1] * Math.sin(3 * a + P.ph[1]) + P.amp[2] * Math.sin(5 * a + P.ph[2]); }
  function rhoAt(P, x, y) {
    const dx = (x - P.cx) / P.rx, dy = (y - P.cy) / P.ry, a = Math.atan2(dy, dx);
    return Math.pow(Math.abs(dx) ** P.e + Math.abs(dy) ** P.e, 1 / P.e) / wobbleF(P, a);
  }
  function ringsH(rings, r) {
    if (r >= rings[0][0]) return null;
    let prev = rings[0];
    for (let k = 1; k < rings.length; k++) {
      const L = rings[k];
      if (r >= L[0]) return lerp(prev[1], L[1], (prev[0] - r) / Math.max(1e-4, prev[0] - L[0]));
      prev = L;
    }
    return prev[1];
  }
  function outlineAt(P, a, sc) {
    const c = Math.cos(a), s = Math.sin(a), N = Math.pow(Math.abs(c) ** P.e + Math.abs(s) ** P.e, 1 / P.e), f = wobbleF(P, a) * sc / N;
    return [P.cx + P.rx * c * f, P.cy + P.ry * s * f];
  }
  const pitRings = (P, s) => P.rings.map(([sc, z]) => [sc, z * s]);
  // a layer lying on the pit walls, g metres in from the soil, rim at z = top
  function grownRings(P, g, top, s = 1) {
    const k = g / ((P.rx + P.ry) / 2);
    return pitRings(P, s).map(([sc, z], i) => [Math.max(0.02, sc - k), i === 0 ? top : z + g]);
  }

  // clip triangles (flat arrays) to the part behind the cut face, y >= 0
  function clipY(P, N) {
    const op = [], on = [];
    for (let i = 0; i < P.length; i += 9) {
      let poly = [0, 1, 2].map(k => ({ p: P.slice(i + k * 3, i + k * 3 + 3), n: N.slice(i + k * 3, i + k * 3 + 3) }));
      const out = [];
      for (let k = 0; k < 3; k++) {
        const a = poly[k], b = poly[(k + 1) % 3], ina = a.p[1] >= 0, inb = b.p[1] >= 0;
        if (ina) out.push(a);
        if (ina !== inb) {
          const s = a.p[1] / (a.p[1] - b.p[1]);
          out.push({ p: a.p.map((v, j) => v + (b.p[j] - v) * s), n: a.n.map((v, j) => v + (b.n[j] - v) * s) });
        }
      }
      for (let k = 1; k + 1 < out.length; k++) for (const v of [out[0], out[k], out[k + 1]]) { op.push(...v.p); on.push(...v.n); }
    }
    return [op, on];
  }
  // the walls of a pit: bands between rings (smooth around, sharp between bands) and a floor; only behind the cut
  function loftGeo(P, rings, n = 144) {
    const pos = [], nor = [];
    const ref = (x, y) => { const dx = P.cx - x, dy = P.cy - y, L = Math.hypot(dx, dy) || 1; return [dx / L, dy / L, 1]; };
    for (let b = 0; b + 1 < rings.length; b++) {
      const [s0, z0] = rings[b], [s1, z1] = rings[b + 1];
      if (Math.abs(s0 - s1) < 1e-5 && Math.abs(z0 - z1) < 1e-5) continue;
      const vp = [];
      for (let j = 0; j < n; j++) { const a = 2 * Math.PI * j / n, o = outlineAt(P, a, s0), q = outlineAt(P, a, s1); vp.push([o[0], o[1], z0], [q[0], q[1], z1]); }
      const idx = [];
      for (let j = 0; j < n; j++) { const a0 = 2 * j, a1 = 2 * ((j + 1) % n); idx.push(a0, a1, a1 + 1, a0, a1 + 1, a0 + 1); }
      // orient toward the inside of the pit
      const [A, B, C] = [vp[idx[0]], vp[idx[1]], vp[idx[2]]];
      const cr = new T.Vector3(...B).sub(new T.Vector3(...A)).cross(new T.Vector3(...C).sub(new T.Vector3(...A)));
      const rf = ref(A[0], A[1]);
      if (cr.x * rf[0] + cr.y * rf[1] + cr.z * rf[2] < 0) for (let k = 0; k < idx.length; k += 3) [idx[k + 1], idx[k + 2]] = [idx[k + 2], idx[k + 1]];
      const g = new T.BufferGeometry();
      g.setAttribute('position', new T.Float32BufferAttribute(vp.flat(), 3)); g.setIndex(idx); g.computeVertexNormals();
      const ng = g.toNonIndexed();
      pos.push(...ng.attributes.position.array); nor.push(...ng.attributes.normal.array);
    }
    const [sl, zl] = rings[rings.length - 1];
    for (let j = 0; j < n; j++) {
      const a = outlineAt(P, 2 * Math.PI * j / n, sl), b = outlineAt(P, 2 * Math.PI * (j + 1) / n, sl);
      pos.push(P.cx, P.cy, zl, a[0], a[1], zl, b[0], b[1], zl); nor.push(0, 0, 1, 0, 0, 1, 0, 0, 1);
    }
    const [cp, cn] = clipY(pos, nor);
    const g = new T.BufferGeometry();
    g.setAttribute('position', new T.Float32BufferAttribute(cp, 3)); g.setAttribute('normal', new T.Float32BufferAttribute(cn, 3));
    g.setAttribute('uv', new T.Float32BufferAttribute(new Float32Array(cp.length / 3 * 2), 2));
    return g;
  }
  // the pit's outline in the cut face (y = 0), left rim -> right rim along the bottom
  function profileAt(P, rings) {
    const out = [], x0 = P.cx - 1.7 * P.rx, x1 = P.cx + 1.7 * P.rx;
    let inside = false;
    for (let x = x0; x <= x1; x += 0.01) {
      const h = ringsH(rings, rhoAt(P, x, 0));
      if (h != null && !inside) { out.push([x, rings[0][1]]); inside = true; }
      if (h != null) out.push([x, h]);
      if (h == null && inside) { out.push([x - 0.01, rings[0][1]]); break; }
    }
    return out;
  }
  // a flat face in the cut face plane (y = y0), facing the camera
  function capGeo(poly, y0 = 0) {
    if (poly.length < 3) return null;
    const pts = poly.map(([u, z]) => new T.Vector2(u, z));
    const P = [], N = [];
    for (const [a, b, c] of T.ShapeUtils.triangulateShape(pts, [])) {
      let v = [pts[a], pts[b], pts[c]];
      const cr = (v[1].x - v[0].x) * (v[2].y - v[0].y) - (v[2].x - v[0].x) * (v[1].y - v[0].y);
      if (cr > 0) v = [v[0], v[2], v[1]];    // (u, z) counter-clockwise faces +y; we want -y
      for (const q of v) { P.push(q.x, y0, q.y); N.push(0, -1, 0); }
    }
    return [P, N];
  }
  function geoFrom(parts) {
    const P = [], N = [];
    for (const g of parts) {
      if (!g) continue;
      if (Array.isArray(g)) { P.push(...g[0]); N.push(...g[1]); }
      else { P.push(...g.attributes.position.array); N.push(...g.attributes.normal.array); }
    }
    const geo = new T.BufferGeometry();
    geo.setAttribute('position', new T.Float32BufferAttribute(P, 3)); geo.setAttribute('normal', new T.Float32BufferAttribute(N, 3));
    geo.setAttribute('uv', new T.Float32BufferAttribute(new Float32Array(P.length / 3 * 2), 2));
    return geo;
  }
  function updatePits(t) {
    PIT_U.uPitN.value = pits.length;
    pits.forEach((P, i) => {
      const s = P.depth(t);
      PIT_U.uPitA.value[i].set(P.cx, P.cy, P.rx, P.ry);
      PIT_U.uPitB.value[i].set(P.e, s, P.rings.length, 0);
      PIT_U.uPitW.value[i].set(...P.amp, 0); PIT_U.uPitP.value[i].set(...P.ph, 0);
      P.rings.forEach((r, k) => PIT_U.uPitR.value[i * MAXRING + k].set(r[0], r[1]));
      const key = s.toFixed(4);
      if (key === P.key) return;
      P.key = key; P.s = s;
      P.mesh.visible = s > 0.001;
      if (!P.mesh.visible) return;
      P.mesh.geometry.dispose(); P.mesh.geometry = loftGeo(P, pitRings(P, s));
    });
  }

  // a two-storey suburban house, front facing the camera; loc = centre of the front wall's base
  function house(loc, o = {}) {
    const [x0, y0, z0] = loc, w = o.w ?? 11, d = o.d ?? 7.5, floors = o.floors ?? 2, fh = 2.9, h = floors * fh + 0.3;
    const wall = o.wall ? triMat({ tex: 'plastered_wall', size: 2.5, tint: o.wall, sat: 0.4, bright: 1.05 }) : MAT.plaster;
    const sh = o.shutters ? new T.MeshStandardMaterial({ color: new T.Color(...o.shutters), roughness: 0.5 }) : MAT.shutter;
    box([w, d, h], [x0, y0 + d / 2, z0], wall);
    box([w + 0.08, d + 0.08, 0.45], [x0, y0 + d / 2, z0 - 0.05], MAT.concrete);
    const ov = 0.45, rise = 2.7, rw = w + 2 * ov, rd = d + 2 * ov, top = z0 + h;
    const run = rd / 2, drop = rise + 0.25, L = Math.hypot(run, drop), ang = Math.atan2(drop, run);
    const roof = MAT.roof(rw / 2.2, L / 2.2);
    for (const s of [-1, 1]) {           // two slopes: thin slabs from the eave up to the ridge
      const g = new T.BoxGeometry(rw, L, 0.18);
      const m = M4().makeTranslation(x0, y0 + d / 2 + s * run / 2, top - 0.25 + drop / 2)
        .multiply(M4().makeRotationX(-s * ang)).multiply(M4().makeTranslation(0, 0, 0.09));
      addGeo(g, roof, m);
    }
    for (const sx of [-1, 1]) {          // gable ends
      const shp = new T.Shape([new T.Vector2(-d / 2, 0), new T.Vector2(d / 2, 0), new T.Vector2(0, rise - 0.25)]);
      const g = new T.ExtrudeGeometry(shp, { depth: 0.2, bevelEnabled: false });
      const m = M4().makeTranslation(x0 + sx * w / 2 - (sx > 0 ? 0.2 : 0), y0 + d / 2, top)
        .multiply(new T.Matrix4().set(0, 0, 1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1));
      addGeo(g, wall, m);
    }
    box([rw, 0.06, 0.22], [x0, y0 - ov + 0.02, top - 0.42], MAT.trim);
    box([rw, 0.14, 0.14], [x0, y0 - ov - 0.04, top - 0.36], MAT.trim);
    box([0.8, 0.8, 2.6], [x0 + w * 0.3, y0 + d * 0.62, top + 0.6], MAT.brick);
    box([0.95, 0.95, 0.12], [x0 + w * 0.3, y0 + d * 0.62, top + 3.2], MAT.concrete);
    const cols = [-0.36, -0.12, 0.12, 0.36];
    for (let fl = 0; fl < floors; fl++) {
      const zc = z0 + 0.3 + fl * fh + (fl ? 1.55 : 1.45);
      cols.forEach((cx, i) => { if (!(fl === 0 && (i === 1 || i === 2))) windowAt([x0 + cx * w, y0, zc], 1.15, 1.45, sh); });
      if (fl === 0) doorAt([x0, y0, z0 + 0.3], 2.4, 2.2);
    }
  }
  function windowAt([x, y, z], ww, wh, sh) {
    box([ww, 0.04, wh], [x, y - 0.0, z - wh / 2], MAT.glass);
    const t = 0.08;
    for (const [dx, dz, sx, sz] of [[0, wh / 2, ww + t, t], [0, -wh / 2, ww + t, t], [-ww / 2, 0, t, wh], [ww / 2, 0, t, wh], [0, 0, ww, t * 0.6], [0, 0, t * 0.6, wh]])
      box([sx, 0.1, sz], [x + dx, y - 0.05, z + dz - sz / 2], MAT.trim);
    box([ww + 0.25, 0.22, 0.07], [x, y - 0.1, z - wh / 2 - 0.1], MAT.trim);
    for (const s of [-1, 1]) box([ww * 0.48, 0.06, wh + 0.05], [x + s * (ww / 2 + ww * 0.26), y - 0.06, z - wh / 2 - 0.02], sh);
  }
  function doorAt([x, y, z], ww, wh) {
    box([ww, 0.04, wh], [x, y, z], MAT.glass);
    const t = 0.09;
    for (const [dx, sx] of [[-ww / 2, t], [ww / 2, t], [0, t * 0.7]]) box([sx, 0.1, wh], [x + dx, y - 0.05, z], MAT.trim);
    box([ww + t, 0.1, t], [x, y - 0.05, z + wh], MAT.trim);
    box([ww + 1.4, 1.1, 0.1], [x, y - 0.55, z + wh + 0.35], MAT.trim);
    for (const s of [-1, 1]) box([0.1, 0.1, wh + 0.35], [x + s * (ww / 2 + 0.6), y - 1.05, z], MAT.trim);
  }
  function fence(x0, x1, y) {
    const n = Math.floor((x1 - x0) / 0.16);
    for (let i = 0; i < n; i++) box([0.145, 0.03, 1.75 + 0.03 * Math.sin(i * 1.7)], [x0 + i * 0.16, y, -0.02], MAT.wood);
    for (const zz of [0.35, 1.45]) box([x1 - x0, 0.06, 0.09], [(x0 + x1) / 2, y + 0.05, zz], MAT.wood);
  }
  // a broadleaf tree: trunk and a crown of noisy leaf blobs
  function tree(loc, scale = 1, seed = 1) {
    const [x, y, z] = loc, r = rng(seed * 97 + 5);
    const th = 2.6 * scale;
    const tg = new T.CylinderGeometry(0.12 * scale, 0.2 * scale, th, 8);
    addGeo(tg, MAT.bark, M4().makeTranslation(x, y, z + th / 2).multiply(M4().makeRotationX(Math.PI / 2)));
    const n = 7;
    for (let i = 0; i < n; i++) {
      const a = r() * Math.PI * 2, rr = (0.4 + r() * 0.9) * scale, cz = z + th + (r() * 1.6 - 0.2) * scale;
      const g = blobGeo((1.0 + r() * 0.7) * scale, 0.85, 0.35, 2, seed * 13 + i);
      addGeo(g, i % 3 ? MAT.leaves : MAT.leaves2, M4().makeTranslation(x + Math.cos(a) * rr, y + Math.sin(a) * rr, cz));
    }
  }
  function shrub(loc, scale = 1, seed = 1) {
    const [x, y, z] = loc, r = rng(seed * 31 + 7);
    for (let i = 0; i < 4; i++) {
      const g = blobGeo((0.55 + r() * 0.35) * scale, 0.75, 0.35, 2, seed * 7 + i);
      addGeo(g, MAT.leaves2, M4().makeTranslation(x + (r() - 0.5) * 1.4 * scale, y + (r() - 0.5) * 0.6 * scale, z + 0.35 * scale));
    }
  }
  YK.tree = tree; YK.shrub = shrub; YK.house = house;

  YK.yard = function (o = {}) {
    const { w, d } = BLOCK;
    soilBlock();
    // endless lawn around and behind the block, just under the lawn line
    box([220, 160, 0.2], [0, d + 80 - 0.01, -0.203], MAT.ground);
    box([95, d, 0.2], [-w / 2 - 47.5, d / 2, -0.203], MAT.ground);
    box([95, d, 0.2], [w / 2 + 47.5, d / 2, -0.203], MAT.ground);
    if (o.house !== false) house([0.6, 9.8, 0], { w: 11.5, d: 7.5 });
    if (o.neighbours !== false) {
      house([-17.5, 15.5, 0], { w: 9.5, d: 7, wall: [0.92, 0.88, 0.8], shutters: [0.2, 0.3, 0.25] });
      house([18, 16.5, 0], { w: 10, d: 7, wall: [0.86, 0.86, 0.9], shutters: [0.45, 0.15, 0.12] });
    }
    fence(-13, 13, d - 0.6);
    if (o.props !== false) {
      tree([-7.6, 7.2, 0], 1.25, 1); tree([8.2, 8.6, 0], 1.1, 2); tree([-12.5, 13, 0], 1.0, 3); tree([12.5, 14.5, 0], 1.15, 4);
      shrub([-9.5, 14.2, 0], 1, 5); shrub([9, 14.2, 0], 1, 6); shrub([-4.2, 9.3, 0], 0.7, 7); shrub([5.6, 9.3, 0], 0.7, 8);
      box([8.5, 2.6, 0.08], [0.6, 8.4, -0.04], MAT.pavers);
    }
  };

  // ---------------------------------------------------------------- animation verbs
  // pit: dig an organic hole into the block. at = outline centre (x, y), size = radii (x, y); keep part of the
  // outline at y < 0 so the cut face slices it. levels = [[scale, z], ...] from the rim down, e.g. a pond with a
  // plant shelf: [[1, -0.04], [0.95, -0.38], [0.72, -0.42], [0.6, -1.3]]. A straight-sided box: exponent 8, [[1, -depth]].
  // dig = [t0, t1] digs it over that time (start = how deep it already is at t0), throwing clods onto a pile.
  YK.pit = function (o) {
    const r = rng(o.seed ?? 3), wob = o.wobble ?? 0.07;
    const levels = o.levels || [[1, -0.04], [0.95, -0.38], [0.72, -0.42], [0.6, -1.3]];
    const P = {
      cx: o.at[0], cy: o.at[1], rx: o.size[0], ry: o.size[1], e: o.exponent ?? 2,
      amp: [0, 0, 0].map(() => (r() * 2 - 1) * wob), ph: [0, 0, 0].map(() => r() * 6.283),
      rings: [[levels[0][0], 0], ...levels].slice(0, MAXRING), key: '', s: 1,
    };
    const [t0, t1] = o.dig || [-1, -1], st = o.start ?? 0;
    P.depth = t => (t0 < 0 ? 1 : st + (1 - st) * ease(span(t, t0, t1), st ? 'out' : 'inout'));
    P.mesh = new T.Mesh(new T.BufferGeometry(), MAT.pitWall); P.mesh.castShadow = P.mesh.receiveShadow = true; world.add(P.mesh);
    pits.push(P);
    if (t0 >= 0) digFx(P, t0, t1, o);
    return P;
  };
  function digFx(P, t0, t1, o) {
    const cx = P.cx, cy = Math.max(0.3, P.cy);
    const [px, py] = o.pile || [cx - P.rx - 1.6, cy + 1.5], ps = o.pileSize ?? 1, st = o.start ?? 0;
    const pile = new T.Mesh(blobGeo(1.4 * ps, 0.45, 0.25, 3, 2), MAT.mud);
    pile.position.set(px, py, -0.15); pile.castShadow = pile.receiveShadow = true; world.add(pile);
    const r = rng(11), n = o.clods ?? 18, clods = [];
    for (let i = 0; i < n; i++) {
      const m = new T.Mesh(blobGeo(0.13 + 0.08 * r(), 0.75, 0.55, 1, i), MAT.clod); m.castShadow = true; world.add(m);
      const ts = t0 + (t1 - t0 - 0.7) * i / Math.max(1, n - 1) - (st && i < 4 ? 0.1 * (4 - i) : 0);
      clods.push({ m, ts, sx: cx + (r() - 0.5) * P.rx, sy: cy + r() * P.ry * 0.6, ex: px + (r() - 0.5) * 1.2, ey: py + (r() - 0.5) * 0.8,
        peak: (o.arc ?? 1.5) * (0.75 + 0.5 * r()), spin: [r() * 7, r() * 7, r() * 7] });
    }
    for (let k = 0; k <= Math.floor((t1 - t0) / 0.35); k++) YK.sfx('dig', t0 + 0.35 * k);
    updaters.push(t => {
      const s = span(t, t0 + (st ? 0 : 0.2), t1);
      pile.visible = st > 0 || t >= t0 + 0.2; pile.scale.setScalar(Math.max(0.05, st * 0.6 + (1 - st * 0.6) * ease(s, 'out')));
      for (const c of clods) {
        const q = (t - c.ts) / 0.7;
        c.m.visible = q >= 0 && q <= 1;
        if (!c.m.visible) continue;
        c.m.position.set(lerp(c.sx, c.ex, q), lerp(c.sy, c.ey, q), -0.2 + 4 * c.peak * q * (1 - q) + 0.1 * q);
        c.m.rotation.set(c.spin[0] * q, c.spin[1] * q, c.spin[2] * q);
      }
    });
    return pile;
  }

  // water (or mud, oil) in a pit: keys = [[t, surface z], ...] (start below the floor for empty); inset = metres
  // inside the soil wall (use the liner's inset + thickness once there is a liner)
  YK.water = function (P, keys, o = {}) {
    for (let i = 0; i < keys.length - 1; i++) if (keys[i + 1][1] > keys[i][1] + 0.2) YK.sfx('pour', keys[i][0], keys[i + 1][0] - keys[i][0]);
    const mesh = new T.Mesh(new T.BufferGeometry(), o.mat ? matOf(o.mat) : MAT.water); mesh.renderOrder = 2; world.add(mesh);
    let last = null;
    updaters.push(t => {
      let z = keys[0][1];
      for (let i = 0; i < keys.length - 1; i++) if (t >= keys[i][0]) z = lerp(keys[i][1], keys[i + 1][1], ease(span(t, keys[i][0], keys[i + 1][0])));
      const rings = grownRings(P, o.inset ?? 0.0, 0, P.depth(t));
      const zfloor = rings[rings.length - 1][1];
      mesh.visible = z > zfloor + 0.01 && (o.until == null || t < o.until) && (o.from == null || t >= o.from);
      if (!mesh.visible) return;
      const L = Math.min(z, -0.015), kk = L.toFixed(4) + '|' + P.depth(t).toFixed(4);
      if (kk === last) return; last = kk;
      let lo = 0, hi = rings[0][0] - 1e-4;                       // the ring where the surface meets the wall
      if (ringsH(rings, hi) > L) { for (let i = 0; i < 40; i++) { const m = (lo + hi) / 2; if (ringsH(rings, m) > L) hi = m; else lo = m; } }
      const top = loftGeo(P, [[hi, L]]);
      const prof = profileAt(P, rings);
      mesh.geometry.dispose(); mesh.geometry = geoFrom([top, capGeo(clipBelow(prof, L), 0.001)]);
    });
    return mesh;
  };

  // a layer lying on the pit walls (sand bed, rubber liner, concrete shell): inset = metres in from the soil,
  // thick = its thickness, rim at z = top. With t it arrives at that time (drop | rise | pop).
  YK.shell = function (P, thick, mat, o = {}) {
    const inset = o.inset ?? 0, top = o.top ?? 0.0;
    const outer = grownRings(P, inset, top), inner = grownRings(P, inset + thick, top);
    const surf = loftGeo(P, [outer[0], ...inner]);
    const strip = capGeo(profileAt(P, outer).concat(profileAt(P, inner).reverse()), 0.002);
    const mesh = new T.Mesh(geoFrom([surf, strip]), matOf(mat)); mesh.castShadow = mesh.receiveShadow = true; world.add(mesh);
    const t = o.t, how = o.how || 'drop';
    if (t != null) YK.sfx(how === 'drop' ? 'thud' : 'pop', t + (how === 'drop' ? 0.42 : 0));
    if (t != null) updaters.push(tt => {
      const s = span(tt, t, t + 0.6);
      mesh.visible = tt >= t && (o.until == null || tt < o.until);
      if (how === 'drop') mesh.position.z = s < 0.7 ? 1.2 * (1 - (s / 0.7) ** 2) : 0.03 * Math.sin(Math.PI * (s - 0.7) / 0.3);
      else if (how === 'rise') mesh.position.z = -1.2 * (1 - ease(s, 'out'));
      else mesh.scale.setScalar(Math.max(0.001, ease(s, 'back')));
    });
    return mesh;
  };

  // a garden hose lying on the lawn, its nozzle over the hole, with a stream from t0 to t1
  YK.hose = function (pts, t0, t1, aim) {
    const curve = new T.CatmullRomCurve3(pts.map(p => new T.Vector3(...p)));
    addGeo(new T.TubeGeometry(curve, 80, 0.035, 8, false), MAT.hose);
    const end = curve.getPoint(1), dir = curve.getTangent(1);
    const [ax, ay, az] = aim;
    const sc = new T.QuadraticBezierCurve3(end.clone(), end.clone().add(dir.clone().multiplyScalar(0.5)), new T.Vector3(ax, ay, az));
    const stream = new T.Mesh(new T.TubeGeometry(sc, 30, 0.028, 6, false), MAT.stream); world.add(stream);
    updaters.push(t => { stream.visible = t >= t0 && t <= t1; });
  };

  // wet soil spreading around a point of the cut face: keys = [[t, radius, strength], ...]
  YK.wet = function (u, z, keys) {
    updaters.push(t => {
      let r = keys[0][1], k = keys[0][2];
      for (let i = 0; i < keys.length - 1; i++) if (t >= keys[i][0]) { const s = ease(span(t, keys[i][0], keys[i + 1][0])); r = lerp(keys[i][1], keys[i + 1][1], s); k = lerp(keys[i][2], keys[i + 1][2], s); }
      GROUND_U.uWet.value.set(u, z, r, k);
    });
  };
  // fat 3D arrows (seeping, flowing, pushing): starts = [[x, y, z], ...], dir = [dx, dy, dz] in the cut face plane;
  // they pop in at t0, slide along dir in a loop, and pop out at t1. Put y just in front of the cut (-0.25).
  YK.arrows = function (starts, dir, t0, t1, o = {}) {
    const len = o.length ?? 0.8, w = o.width ?? 0.32;
    const shp = new T.Shape([[-0.18 * w, 0], [0.18 * w, 0], [0.18 * w, 0.58 * len], [0.5 * w, 0.58 * len], [0, len], [-0.5 * w, 0.58 * len], [-0.18 * w, 0.58 * len]].map(([x, y]) => new T.Vector2(x, y)));
    const g = new T.ExtrudeGeometry(shp, { depth: 0.08, bevelEnabled: true, bevelThickness: 0.02, bevelSize: 0.02, bevelSegments: 2 });
    g.applyMatrix4(new T.Matrix4().makeRotationX(Math.PI / 2));       // shape in the x-z plane, pointing up (+z)
    const mat = o.mat ? matOf(o.mat) : MAT.arrow;
    const d = new T.Vector3(...dir).normalize(), q = new T.Quaternion().setFromUnitVectors(new T.Vector3(0, 0, 1), d);
    const ms = starts.map(p => { const m = new T.Mesh(g, mat); m.quaternion.copy(q); m.castShadow = true; world.add(m); return { m, p }; });
    updaters.push(t => {
      const on = t >= t0 && t <= t1 + 0.3;
      const k = Math.min(ease(span(t, t0, t0 + 0.35), 'back'), 1 - ease(span(t, t1, t1 + 0.3), 'in'));
      const slide = (((t - t0) * (o.speed ?? 0.9)) % 1) * (o.travel ?? 0.35);
      for (const { m, p } of ms) {
        m.visible = on && k > 0.001; if (!m.visible) continue;
        m.scale.setScalar(Math.max(0.001, k));
        m.position.set(p[0] + d.x * slide, p[1] + d.y * slide, p[2] + d.z * slide);
      }
    });
  };
  YK.on = fn => updaters.push(fn);
  // narration timing: T[id].start / .end per line, T.word(id, 'word') = when that word is spoken, T.end = video end
  YK.timing = function (tm) {
    const T = { end: tm.end, list: tm.lines };
    const norm = w => String(w).toLowerCase().replace(/[^a-z0-9']/g, '');
    for (const l of tm.lines) T[l.id] = l;
    T.word = (id, w, nth = 1) => {
      const l = T[id];
      if (!l) return 0;
      let k = 0;
      for (const x of l.words || []) if (norm(x.w) === norm(w) && ++k === nth) return x.start;
      return l.start;
    };
    return T;
  };

  // ---------------------------------------------------------------- sound cues
  // The sound designer reads window.__kCues after load and drops a matching effect there.
  // kinds: dig, thud, pop, splash, pour, bubble, whoosh, click, hum, chime
  window.__kCues = window.__kCues || [];
  YK.sfx = (kind, t, dur = 0) => { window.__kCues.push({ t: Math.round(t * 1000), kind, dur: Math.round(dur * 1000), n: 1 }); };

  // ---------------------------------------------------------------- more materials
  YK.plastic = (rgb, rough = 0.45) => new T.MeshStandardMaterial({ color: new T.Color(...rgb), roughness: rough, envMapIntensity: 0.8 });
  YK.foam = rgb => triMat({ tex: 'dirt', size: 0.25, tint: rgb.map(c => c * 2.2), sat: 0, bright: 1, rough: 1 });
  YK.flat = (rgb, o = {}) => new T.MeshStandardMaterial({ color: new T.Color(...rgb), roughness: o.rough ?? 0.6, metalness: o.metal ?? 0,
    transparent: (o.alpha ?? 1) < 1, opacity: o.alpha ?? 1, emissive: new T.Color(...(o.emit || [0, 0, 0])) });
  YK.texMat = (texName, size, o = {}) => triMat({ tex: texName, size, tint: o.tint, sat: o.sat, bright: o.bright, rough: o.rough });
  const matOf = m => (typeof m === 'string' ? MAT[m] : m) || MAT.concrete;

  // ---------------------------------------------------------------- things
  function own(geo, mat, loc, o = {}) {
    const m = new T.Mesh(geo, matOf(mat)); m.position.set(...loc);
    if (o.rot) m.rotation.set(...o.rot.map(d => d * Math.PI / 180));
    m.castShadow = o.shadow !== false; m.receiveShadow = true; world.add(m); return m;
  }
  // box (pivot at its bottom centre unless origin 'center' / 'top'); returns the mesh, ready to animate
  YK.part = function (size, loc, mat, o = {}) {
    const [sx, sy, sz] = size, g = new T.BoxGeometry(sx, sy, sz);
    const or = o.origin || 'bottom'; g.translate(0, 0, or === 'bottom' ? sz / 2 : or === 'top' ? -sz / 2 : 0);
    return own(g, mat, loc, o);
  };
  // cylinder: axis 'z' (upright, pivot at the bottom), 'x' or 'y' (lying, pivot at its centre)
  YK.cyl = function (r, h, loc, mat, o = {}) {
    const g = new T.CylinderGeometry(o.r2 ?? r, r, h, o.seg || 40, 1, !!o.open);
    const ax = o.axis || 'z';
    if (ax === 'z') { g.rotateX(Math.PI / 2); g.translate(0, 0, h / 2); }
    else if (ax === 'x') g.rotateZ(Math.PI / 2);
    return own(g, mat, loc, o);
  };
  YK.sphere = (r, loc, mat, o = {}) => own(blobGeo(r, o.squash ?? 1, o.noise ?? 0, o.detail ?? 3, o.seed ?? 1), mat, loc, o);
  // a pipe through kit points; with t0/t1 it grows along its path
  YK.pipe = function (points, r, mat = 'pvc', o = {}) {
    const curve = new T.CatmullRomCurve3(points.map(p => new T.Vector3(...p)), false, 'catmullrom', o.tension ?? 0.1);
    const segs = Math.max(24, Math.round(curve.getLength() * 20));
    const g = new T.TubeGeometry(curve, segs, r, 16, false);
    const m = own(g, mat, [0, 0, 0], o);
    if (o.t0 != null) {
      const total = g.index.count;
      updaters.push(t => { const s = ease(span(t, o.t0, o.t1 ?? o.t0 + 0.8), 'out'); m.visible = s > 0.001; g.setDrawRange(0, Math.floor(total * s / 6) * 6); });
    }
    m.curve = curve; return m;
  };
  // an open-fronted tank or box cut open at the cut face: size (sx, sy, sz), loc = front-bottom centre (y = front)
  YK.tank = function (size, loc, mat = 'pvc', o = {}) {
    const [sx, sy, sz] = size, [x, y, z] = loc, w = o.wall ?? 0.06, grp = new T.Group();
    const add = (s, p) => { const g = new T.BoxGeometry(...s); const m = new T.Mesh(g, matOf(mat)); m.position.set(...p); m.castShadow = m.receiveShadow = true; grp.add(m); };
    add([sx, w, sz], [0, sy - w / 2, sz / 2]);                       // back
    add([w, sy, sz], [-sx / 2 + w / 2, sy / 2, sz / 2]); add([w, sy, sz], [sx / 2 - w / 2, sy / 2, sz / 2]);
    add([sx, sy, w], [0, sy / 2, w / 2]);                           // floor
    if (o.lid) add([sx + 0.04, sy, w], [0, sy / 2, sz - w / 2]);
    grp.position.set(x, y, z); world.add(grp);
    grp.inner = { x0: x - sx / 2 + w, x1: x + sx / 2 - w, y0: y + 0.01, y1: y + sy - w, z0: z + w, z1: z + sz - (o.lid ? w : 0) };
    return grp;
  };
  // liquid in a tank (or any box region {x0,x1,y0,y1,z0,z1}): keys = [[t, fraction full], ...]
  YK.fill = function (box, keys, mat = 'water') {
    const b = box.inner || box, h = b.z1 - b.z0;
    const g = new T.BoxGeometry(b.x1 - b.x0, b.y1 - b.y0, h); g.translate(0, 0, h / 2);
    const m = new T.Mesh(g, matOf(mat)); m.position.set((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, b.z0); m.renderOrder = 2; world.add(m);
    updaters.push(t => {
      let v = keys[0][1];
      for (let i = 0; i < keys.length - 1; i++) if (t >= keys[i][0]) v = lerp(keys[i][1], keys[i + 1][1], ease(span(t, keys[i][0], keys[i + 1][0])));
      m.visible = v > 0.005; m.scale.z = Math.max(0.001, v);
    });
    return m;
  };
  // a layer of soil-like stuff (gravel bed, sand, concrete, fill) in a box region, rising into place at t
  YK.layer = function (region, mat, o = {}) {
    const [[x0, x1], [y0, y1], [z0, z1]] = region;
    const m = YK.part([x1 - x0, y1 - y0, z1 - z0], [(x0 + x1) / 2, (y0 + y1) / 2, z0], mat);
    if (o.t != null) YK.appear(m, o.t, o.how || 'grow_z', o.dur ?? 0.6);
    return m;
  };
  // gravel: hundreds of small stones on the cut face and the top of a region (never a flat textured box)
  YK.gravel = function (region, o = {}) {
    const [[x0, x1], [y0, y1], [z0, z1]] = region, size = o.size ?? 0.045, r = rng(o.seed ?? 21);
    const base = new T.Mesh(new T.BoxGeometry(x1 - x0, y1 - y0 - 0.04, z1 - z0 - 0.02).translate(0, 0, (z1 - z0 - 0.02) / 2), MAT.gravelBed);
    base.position.set((x0 + x1) / 2, (y0 + y1) / 2 + 0.02, z0); base.receiveShadow = true;
    const pts = [];
    const nFace = Math.min(900, Math.round((x1 - x0) * (z1 - z0) / (size * size * 1.6)));
    for (let i = 0; i < nFace; i++) pts.push([x0 + r() * (x1 - x0), y0 + r() * 0.05, z0 + r() * (z1 - z0)]);
    const nTop = Math.min(900, Math.round((x1 - x0) * (y1 - y0) / (size * size * 2.2)));
    for (let i = 0; i < nTop; i++) pts.push([x0 + r() * (x1 - x0), y0 + r() * (y1 - y0), z1 - r() * 0.03]);
    const inst = new T.InstancedMesh(blobGeo(size, 0.7, 0.5, 1, 4), MAT.stone, pts.length);
    const M = new T.Matrix4(), q = new T.Quaternion(), e = new T.Euler();
    pts.forEach((p, i) => { e.set(r() * 6, r() * 6, r() * 6); q.setFromEuler(e); const k = 0.6 + r() * 0.9; M.compose(new T.Vector3(...p), q, new T.Vector3(k, k * (0.8 + r() * 0.4), k)); inst.setMatrixAt(i, M); });
    inst.castShadow = inst.receiveShadow = true;
    const grp = new T.Group(); grp.add(base, inst); world.add(grp);
    if (o.t != null) YK.appear(grp, o.t, o.how || 'drop', 0.6, 1.5);
    return grp;
  };
  // rocks / pebbles (irregular)
  YK.rock = (loc, size = 0.3, o = {}) => YK.sphere(size, loc, o.mat || MAT.stone, { squash: o.squash ?? 0.7, noise: 0.45, detail: 2, seed: o.seed ?? 7 });
  YK.tree = (loc, scale = 1, seed = 1) => { tree(loc, scale, seed); };
  YK.shrub = (loc, scale = 1, seed = 1) => { shrub(loc, scale, seed); };

  // ---------------------------------------------------------------- animation verbs for any object
  // appear: pop | grow_z | rise | drop | slide_x | slide_y | fade. Hidden before t.
  YK.appear = function (obj, t, how = 'pop', dur = 0.5, dist = 3.0) {
    const p = obj.position.clone(), s = obj.scale.clone();
    if (how === 'drop') YK.sfx('thud', t + dur * 0.7); else if (how === 'pop' || how === 'grow_z') YK.sfx('pop', t);
    updaters.push(tt => {
      if (tt < t) { obj.visible = false; return; }
      if (obj.userData.goneAt != null && tt >= obj.userData.goneAt) return;
      obj.visible = true;
      const q = span(tt, t, t + dur);
      if (q >= 1 && obj.userData.settled) return;
      obj.userData.settled = q >= 1;
      if (how === 'pop') obj.scale.copy(s).multiplyScalar(Math.max(0.001, ease(q, 'back')));
      else if (how === 'grow_z') obj.scale.set(s.x, s.y, s.z * Math.max(0.001, ease(q, 'out')));
      else if (how === 'rise') obj.position.set(p.x, p.y, p.z - dist * (1 - ease(q, 'out')));
      else if (how === 'drop') obj.position.set(p.x, p.y, p.z + (q < 0.7 ? dist * (1 - (q / 0.7) ** 2) : 0.018 * dist * Math.sin(Math.PI * (q - 0.7) / 0.3)));
      else if (how === 'slide_x') obj.position.set(p.x + dist * (1 - ease(q, 'out')), p.y, p.z);
      else if (how === 'slide_y') obj.position.set(p.x, p.y + dist * (1 - ease(q, 'out')), p.z);
      else if (how === 'fade') obj.traverse(c => { if (c.material) { c.material.transparent = true; c.material.opacity = ease(q); } });
    });
    return obj;
  };
  YK.vanish = function (obj, t, how = 'pop', dur = 0.4, dist = 3.0) {
    obj.userData.goneAt = t + dur;
    let p0 = null, s0 = null;
    updaters.push(tt => {
      if (tt < t) return;
      if (!p0) { p0 = obj.position.clone(); s0 = obj.scale.clone(); }
      const q = span(tt, t, t + dur);
      obj.visible = tt < t + dur;
      if (how === 'pop') obj.scale.copy(s0).multiplyScalar(Math.max(0.001, 1 - ease(q, 'in')));
      else if (how === 'sink') obj.position.set(p0.x, p0.y, p0.z - dist * ease(q, 'in'));
    });
    return obj;
  };
  YK.hideFrom = (obj, t) => { updaters.push(tt => { if (tt >= t) obj.visible = false; }); return obj; };
  // glide to loc / rot (degrees) / scale between t0 and t1
  YK.move = function (obj, t0, t1, o = {}) {
    let a = null;
    updaters.push(t => {
      if (t < t0) return;
      if (!a) a = { p: obj.position.clone(), r: obj.rotation.clone(), s: obj.scale.clone() };
      const q = ease(span(t, t0, t1), o.kind || 'inout');
      if (o.loc) obj.position.set(lerp(a.p.x, o.loc[0], q), lerp(a.p.y, o.loc[1], q), lerp(a.p.z, o.loc[2], q));
      if (o.rot) obj.rotation.set(...o.rot.map((d, i) => lerp([a.r.x, a.r.y, a.r.z][i], d * Math.PI / 180, q)));
      if (o.scale != null) { const k = Array.isArray(o.scale) ? o.scale : [o.scale, o.scale, o.scale]; obj.scale.set(lerp(a.s.x, k[0], q), lerp(a.s.y, k[1], q), lerp(a.s.z, k[2], q)); }
    });
    return obj;
  };
  // drive along any path fn(s) -> [x, y, z], s 0..1 over t0..t1; face 'xy' turns it left/right toward the motion
  YK.follow = function (obj, t0, t1, fn, o = {}) {
    updaters.push(t => {
      if (t < t0 || t > t1 + 0.001) return;
      const s = span(t, t0, t1), p = fn(s), q = fn(Math.min(1, s + 0.01));
      obj.position.set(...p);
      if (o.face) { const dx = q[0] - p[0], dy = q[1] - p[1]; if (Math.hypot(dx, dy) > 1e-5) obj.rotation.z = Math.atan2(dy, dx); }
    });
    return obj;
  };
  // raise / lower something with its pivot at the bottom: keys = [[t, fraction], ...]
  YK.level = function (obj, keys) {
    const s = obj.scale.z;
    updaters.push(t => {
      let v = keys[0][1];
      for (let i = 0; i < keys.length - 1; i++) if (t >= keys[i][0]) v = lerp(keys[i][1], keys[i + 1][1], ease(span(t, keys[i][0], keys[i + 1][0])));
      obj.scale.z = s * Math.max(0.001, v); obj.visible = v > 0.002 && obj.visible !== false;
    });
    return obj;
  };
  // spin around an axis ('x' | 'y' | 'z'), turns per second
  YK.spin = (obj, t0, t1, axis = 'z', tps = 1) => { updaters.push(t => { if (t >= t0 && t <= t1) obj.rotation[axis] = 2 * Math.PI * tps * (t - t0); }); return obj; };

  // ---------------------------------------------------------------- effects
  // water streaming along a path as stretched droplets (a pour: n 10+, size 0.025-0.04; air: mat 'air')
  YK.flow = function (points, t0, t1, o = {}) {
    const curve = new T.CatmullRomCurve3(points.map(p => new T.Vector3(...p)));
    const n = o.n ?? 10, size = o.size ?? 0.05, mat = matOf(o.mat || 'flow'), speed = o.speed ?? 1, len = curve.getLength();
    const g = new T.SphereGeometry(size, 10, 8);
    const drops = Array.from({ length: n }, () => { const m = new T.Mesh(g, mat); m.renderOrder = 3; world.add(m); return m; });
    YK.sfx(o.sound || 'pour', t0, t1 - t0);
    updaters.push(t => {
      const on = t >= t0 && t <= t1;
      drops.forEach((m, i) => {
        m.visible = on; if (!on) return;
        const u = ((t - t0) * speed * 1.6 / Math.max(0.3, len) + i / n) % 1;
        const p = curve.getPointAt(u), d = curve.getTangentAt(u);
        m.position.copy(p); m.quaternion.setFromUnitVectors(new T.Vector3(0, 0, 1), d);
        m.scale.set(1, 1, o.stretch ?? 2.4);
      });
    });
  };
  YK.bubbles = function (origin, t0, t1, o = {}) {
    const n = o.n ?? 10, rise = o.rise ?? 1.0, spread = o.spread ?? 0.4, r = rng(o.seed ?? 5);
    const g = new T.SphereGeometry(o.size ?? 0.03, 10, 8), mat = matOf(o.mat || 'bubble');
    const bs = Array.from({ length: n }, () => ({ m: (() => { const m = new T.Mesh(g, mat); m.renderOrder = 3; world.add(m); return m; })(), dx: (r() - 0.5) * spread, dy: r() * spread * 0.5, ph: r() }));
    YK.sfx('bubble', t0);
    updaters.push(t => bs.forEach(b => {
      const on = t >= t0 && t <= t1; b.m.visible = on; if (!on) return;
      const u = ((t - t0) * 0.8 + b.ph) % 1;
      b.m.position.set(origin[0] + b.dx + 0.03 * Math.sin(u * 20), origin[1] + b.dy, origin[2] + u * rise);
    }));
  };
  // a cloud of small things buzzing around a centre (insects, bacteria, specks)
  YK.swarm = function (center, t0, t1, o = {}) {
    const n = o.n ?? 14, rad = o.radius ?? 0.8, r = rng(o.seed ?? 9);
    const g = new T.SphereGeometry(o.size ?? 0.03, 8, 6), mat = matOf(o.mat || 'speck');
    const ps = Array.from({ length: n }, () => ({ m: (() => { const m = new T.Mesh(g, mat); world.add(m); return m; })(), a: r() * 6.3, b: r() * 6.3, w: 1 + r() * 2, k: 0.4 + r() * 0.6 }));
    updaters.push(t => ps.forEach(p => {
      const on = t >= t0 && t <= t1; p.m.visible = on; if (!on) return;
      const a = p.a + t * p.w, b = p.b + t * p.w * 0.7;
      p.m.position.set(center[0] + rad * p.k * Math.cos(a), center[1] + 0.5 * rad * p.k * Math.sin(b), center[2] + 0.5 * rad * p.k * Math.sin(a * 1.3));
    }));
  };
  YK.rain = function (t0, t1, o = {}) {
    const n = o.n ?? 260, [[x0, x1], [y0, y1]] = o.area || [[-10, 10], [0.3, 16]], r = rng(17);
    const g = new T.CylinderGeometry(0.008, 0.008, 0.35, 4); g.rotateX(Math.PI / 2);
    const inst = new T.InstancedMesh(g, MAT.rain, n), M = new T.Matrix4(), dr = [];
    for (let i = 0; i < n; i++) dr.push([x0 + r() * (x1 - x0), y0 + r() * (y1 - y0), r()]);
    world.add(inst);
    updaters.push(t => {
      inst.visible = t >= t0 && t <= t1; if (!inst.visible) return;
      dr.forEach((d, i) => { const z = 9 - ((t * 9 + d[2] * 9) % 9); M.makeTranslation(d[0], d[1], z); inst.setMatrixAt(i, M); });
      inst.instanceMatrix.needsUpdate = true;
    });
  };
  // a cave-in: lumps break off inside region and fall by 'fall' metres, tumbling
  YK.chunks = function (region, t, o = {}) {
    const [[x0, x1], [y0, y1], [z0, z1]] = region, n = o.n ?? 10, r = rng(o.seed ?? 13), fall = o.fall ?? 1.5, dur = o.dur ?? 0.9;
    YK.sfx('thud', t + dur * 0.8);
    for (let i = 0; i < n; i++) {
      const m = own(blobGeo((o.size ?? 0.35) * (0.6 + 0.8 * r()), 0.85, 0.45, 1, i + 3), o.mat || MAT.clod, [x0 + r() * (x1 - x0), y0 + r() * (y1 - y0), z0 + r() * (z1 - z0)]);
      const p = m.position.clone(), sp = [r() * 4, r() * 4, r() * 4], dl = r() * 0.25;
      updaters.push(tt => { const q = span(tt, t + dl, t + dl + dur); m.position.set(p.x, p.y, p.z - fall * q * q); m.rotation.set(sp[0] * q, sp[1] * q, sp[2] * q); });
    }
  };
  // a tinted patch on the cut face (wet soil, groundwater, heat, cold): rect = [x0, x1, z0, z1], with a natural
  // top edge; how 'up' fills from the bottom, 'down' from the top, 'out' grows from the middle, 'fade'
  YK.overlay = function (rect, color, t0, t1, o = {}) {
    const [x0, x1, z0, z1] = rect, alpha = o.alpha ?? 0.45;
    const mat = new T.ShaderMaterial({
      transparent: true, depthWrite: false,
      uniforms: { uC: { value: new T.Color(...color) }, uA: { value: alpha }, uP: { value: 0 }, uR: { value: new T.Vector4(x0, x1, z0, z1) }, uHow: { value: { up: 0, down: 1, out: 2, fade: 3 }[o.how || 'up'] ?? 0 } },
      vertexShader: 'varying vec2 vP; void main(){ vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }',
      fragmentShader: `uniform vec3 uC; uniform float uA; uniform float uP; uniform vec4 uR; uniform float uHow; varying vec2 vP;
        float h(float x){ return fract(sin(x * 12.9898) * 43758.5453); }
        float n1(float x){ float i = floor(x), f = fract(x); return mix(h(i), h(i + 1.0), f * f * (3.0 - 2.0 * f)); }
        void main(){
          float u = (vP.x - uR.x) / (uR.y - uR.x), v = (vP.y - uR.z) / (uR.w - uR.z);
          float edge = 0.04 * (n1(vP.x * 3.0) - 0.5) + 0.02 * (n1(vP.x * 9.0) - 0.5);
          float a = uA;
          if (uHow < 0.5) a *= step(v, uP + edge);
          else if (uHow < 1.5) a *= step(1.0 - uP + edge, v);
          else if (uHow < 2.5) a *= step(length(vec2(u - 0.5, (v - 0.5) * 0.7)) + edge, 0.62 * uP);
          else a *= uP;
          float soft = smoothstep(0.0, 0.03, u) * smoothstep(0.0, 0.03, 1.0 - u) * smoothstep(0.0, 0.03, v);
          gl_FragColor = vec4(uC, a * soft);
          #include <colorspace_fragment>
        }`,
    });
    // the plane's own (x, y) is the cut face's (x, z); turning it up stands it on the cut face, facing the camera
    const g = new T.PlaneGeometry(x1 - x0, z1 - z0); g.translate((x0 + x1) / 2, (z0 + z1) / 2, 0);
    const m = new T.Mesh(g, mat); m.rotation.x = Math.PI / 2; m.position.y = -0.004; m.renderOrder = 1; world.add(m);
    updaters.push(t => { const p = ease(span(t, t0, t1 ?? t0 + 1), 'inout'); m.visible = t >= t0 && (o.until == null || t < o.until); mat.uniforms.uP.value = p; });
    return m;
  };
  // sky brightness over time (night, storm): keys = [[t, 0..1.2], ...]
  YK.sky = function (keys) {
    updaters.push(t => {
      let v = keys[0][1];
      for (let i = 0; i < keys.length - 1; i++) if (t >= keys[i][0]) v = lerp(keys[i][1], keys[i + 1][1], ease(span(t, keys[i][0], keys[i + 1][0])));
      renderer.toneMappingExposure = v; scene.backgroundIntensity = v;
    });
  };
  YK.algae = function (keys) {
    updaters.push(t => {
      let v = keys[0][1];
      for (let i = 0; i < keys.length - 1; i++) if (t >= keys[i][0]) v = lerp(keys[i][1], keys[i + 1][1], ease(span(t, keys[i][0], keys[i + 1][0])));
      WATER_U.uAlgae.value = v;
    });
  };

  // ================================================================ the body set (health explainers)
  // A standing person (feet at z = 0, 1.75 m tall) facing the camera (-y): an x-ray skin, a skeleton, organs and
  // vessels. The person's left is +x. Every organ has its own glowing material for highlights.
  const BODY_VIEWS = {
    full: [[0, -2.9, 0.1], [0, 0, 0], 34], torso: [[0, -1.5, 0.05], [0, 0, 0], 34],
    organ: [[0.12, -0.62, 0.06], [0, 0, 0], 34], close: [[0.05, -0.32, 0.03], [0, 0, 0], 32],
    left: [[-1.0, -1.2, 0.2], [0, 0, 0], 34], right: [[1.0, -1.2, 0.2], [0, 0, 0], 34],
    high: [[0, -1.0, 0.85], [0, 0, 0], 34], low: [[0, -1.25, -0.45], [0, 0, 0.08], 34],
    micro: [[0, -2.3, 0.35], [0, 0, 0], 30], microClose: [[0.4, -1.3, 0.15], [0, 0, 0], 30],
  };
  YK.BODY_VIEWS = BODY_VIEWS;
  const BODY = {};   // organ meshes by name, filled by YK.body()

  // organs: glossy, with a soft rim light and a glow you can pulse (YK.glow)
  function organMat(rgb, o = {}) {
    const glow = { value: 0 }, glowC = { value: new T.Color(...(o.glow || [1.0, 0.85, 0.4])) };
    const m = new T.MeshStandardMaterial({ color: new T.Color(...rgb), roughness: o.rough ?? 0.38, metalness: 0, envMapIntensity: 0.5,
      transparent: (o.alpha ?? 1) < 1, opacity: o.alpha ?? 1 });
    m.onBeforeCompile = sh => {
      sh.uniforms.uGlow = glow; sh.uniforms.uGlowC = glowC; sh.uniforms.uRim = { value: new T.Color(...(o.rim || [0.55, 0.75, 1.0])) };
      sh.fragmentShader = sh.fragmentShader.replace('#include <common>', '#include <common>\nuniform float uGlow; uniform vec3 uGlowC; uniform vec3 uRim;')
        .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
          float fr = pow(1.0 - abs(dot(normalize(normal), normalize(vViewPosition))), 2.5);
          totalEmissiveRadiance += uRim * fr * 0.22 + uGlowC * uGlow * (0.35 + 0.65 * fr);`);
    };
    m.customProgramCacheKey = () => 'organ';
    m.userData.glow = glow; m.userData.glowColor = glowC.value;
    return m;
  }
  YK.organMat = (rgb, o) => organMat(rgb, o);
  // the skin: an x-ray shell, see-through head on and bright at the edges
  function xrayMat(rgb = [0.35, 0.7, 1.0], k = 1) {
    return new T.ShaderMaterial({
      transparent: true, depthWrite: false, blending: T.AdditiveBlending, side: T.FrontSide,
      uniforms: { uC: { value: new T.Color(...rgb) }, uK: { value: k } },
      vertexShader: `varying vec3 vN; varying vec3 vV;
        void main(){ vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = -mv.xyz; gl_Position = projectionMatrix * mv; }`,
      fragmentShader: `uniform vec3 uC; uniform float uK; varying vec3 vN; varying vec3 vV;
        void main(){ float f = pow(1.0 - abs(dot(normalize(vN), normalize(vV))), 2.2);
          gl_FragColor = vec4(uC * (0.035 + 0.6 * f) * uK, 1.0);
          #include <colorspace_fragment>
        }`,
    });
  }
  YK.xrayMat = xrayMat;
  const mk = (geo, mat, name) => { const m = new T.Mesh(geo, mat); m.name = name || ''; world.add(m); return m; };
  // a capsule between two kit points
  function limb(a, b, r, mat) {
    const A = new T.Vector3(...a), B = new T.Vector3(...b), d = new T.Vector3().subVectors(B, A), L = d.length();
    const g = new T.CapsuleGeometry(r, L, 6, 16);
    const m = new T.Mesh(g, mat); m.position.copy(A).addScaledVector(d, 0.5);
    m.quaternion.setFromUnitVectors(new T.Vector3(0, 1, 0), d.normalize()); return m;
  }
  function tubeGeo(points, r, segs = 64, rs = 10) {
    return new T.TubeGeometry(new T.CatmullRomCurve3(points.map(p => new T.Vector3(...p))), segs, r, rs, false);
  }
  // several blobs along a path, merged into one organic shape (stomach, pancreas)
  function blobChain(points, radii, seed = 1) {
    const parts = points.map((p, i) => { const g = blobGeo(radii[i], 1, 0.12, 2, seed + i); g.translate(...p); return g.toNonIndexed(); });
    let n = 0; parts.forEach(g => { n += g.attributes.position.count; });
    const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3); let o = 0;
    for (const g of parts) { pos.set(g.attributes.position.array, o * 3); nor.set(g.attributes.normal.array, o * 3); o += g.attributes.position.count; }
    const geo = new T.BufferGeometry(); geo.setAttribute('position', new T.BufferAttribute(pos, 3)); geo.setAttribute('normal', new T.BufferAttribute(nor, 3));
    return geo;
  }
  function organ(name, geo, rgb, loc, o = {}) {
    const m = mk(geo, organMat(rgb, o), name); m.position.set(...loc);
    if (o.scale) m.scale.set(...o.scale); if (o.rot) m.rotation.set(...o.rot.map(d => d * Math.PI / 180));
    BODY[name] = m; return m;
  }
  function studio(top = '#0b1830', bottom = '#02050c') {
    const c = document.createElement('canvas'); c.width = 16; c.height = 512;
    const g = c.getContext('2d'), gr = g.createLinearGradient(0, 0, 0, 512);
    gr.addColorStop(0, top); gr.addColorStop(0.55, '#06101f'); gr.addColorStop(1, bottom);
    g.fillStyle = gr; g.fillRect(0, 0, 16, 512);
    const t = new T.CanvasTexture(c); t.colorSpace = T.SRGBColorSpace; return t;
  }

  // YK.body({ organs: ['heart', ...] | 'all', skeleton: true, skin: true }) builds the person; returns the organ map.
  // Organs: brain, heart, lungL, lungR, liver, stomach, pancreas, kidneyL, kidneyR, intestines, colon, bladder,
  // and the vessels aorta (red) and vena (blue).
  YK.body = function (o = {}) {
    VIEWS = BODY_VIEWS;
    scene.background = studio();
    renderer.shadowMap.enabled = false;
    if (lights.sun) { lights.sun.castShadow = false; lights.sun.intensity = 1.6; lights.sun.position.copy(V(-3, -6, 6)); lights.sun.target.position.copy(V(0, 0, 1.2)); }
    if (lights.fill) { lights.fill.intensity = 1.0; lights.fill.color.setRGB(0.45, 0.75, 1.0); lights.fill.position.copy(V(2, 6, 3)); }
    if (lights.hemi) { lights.hemi.intensity = 0.4; lights.hemi.groundColor.setRGB(0.1, 0.12, 0.2); }
    const want = n => !o.organs || o.organs === 'all' || o.organs.includes(n);
    if (o.skin !== false) {
      const sk = xrayMat([0.35, 0.7, 1.0], 0.75), grp = new T.Group();
      const torso = new T.LatheGeometry([[0.001, 0.9], [0.15, 0.91], [0.17, 0.97], [0.165, 1.05], [0.145, 1.12], [0.155, 1.22], [0.17, 1.32],
        [0.18, 1.4], [0.165, 1.46], [0.07, 1.5], [0.001, 1.505]].map(([r, z]) => new T.Vector2(r, z)), 32);
      torso.rotateX(Math.PI / 2); torso.scale(1.1, 0.62, 1);
      grp.add(new T.Mesh(torso, sk));
      const head = new T.Mesh(new T.SphereGeometry(0.1, 32, 24), sk); head.scale.set(0.82, 0.95, 1.12); head.position.set(0, 0.0, 1.64); grp.add(head);
      grp.add(limb([0, 0, 1.47], [0, 0, 1.56], 0.05, sk));
      for (const s of [-1, 1]) {
        grp.add(limb([s * 0.17, 0, 1.43], [s * 0.21, 0, 1.43], 0.055, sk));
        grp.add(limb([s * 0.22, 0, 1.41], [s * 0.27, 0.01, 1.13], 0.045, sk));
        grp.add(limb([s * 0.27, 0.01, 1.13], [s * 0.3, -0.02, 0.88], 0.037, sk));
        const hand = new T.Mesh(new T.SphereGeometry(0.045, 16, 12), sk); hand.scale.set(0.6, 0.9, 1.3); hand.position.set(s * 0.305, -0.025, 0.81); grp.add(hand);
        grp.add(limb([s * 0.09, 0, 0.93], [s * 0.1, 0, 0.5], 0.068, sk));
        grp.add(limb([s * 0.1, 0, 0.5], [s * 0.1, 0.01, 0.09], 0.05, sk));
        const foot = new T.Mesh(new T.SphereGeometry(0.05, 16, 12), sk); foot.scale.set(0.8, 2.0, 0.6); foot.position.set(s * 0.1, -0.07, 0.03); grp.add(foot);
      }
      grp.renderOrder = 5; grp.traverse(c => { c.renderOrder = 5; });
      world.add(grp); BODY.skin = grp;
    }
    if (o.skeleton !== false) {
      const bone = organMat([0.8, 0.77, 0.7], { rough: 0.6, rim: [0.25, 0.35, 0.45], alpha: 0.55 }), grp = new T.Group();
      for (let i = 0; i < 24; i++) { const v = new T.Mesh(new T.CylinderGeometry(0.016, 0.016, 0.022, 10), bone); v.rotation.x = Math.PI / 2; v.position.set(0, 0.065, 0.93 + i * 0.026); grp.add(v); }
      for (let i = 0; i < 10; i++) {
        const z = 1.42 - i * 0.025, w = 0.125 + 0.03 * Math.sin(Math.min(1, i / 6) * Math.PI / 2), d = 0.075;
        for (const s of [-1, 1]) {
          const pts = []; for (let k = 0; k <= 12; k++) { const th = (k / 12) * 0.86 * Math.PI; pts.push([s * w * Math.sin(th), 0.005 + 0.068 * Math.cos(th), z - 0.045 * (k / 12)]); }
          grp.add(new T.Mesh(tubeGeo(pts, 0.0045, 24, 6), bone));
        }
      }
      const pelvis = new T.Mesh(new T.TorusGeometry(0.1, 0.012, 10, 32), bone); pelvis.scale.set(1.25, 0.7, 1); pelvis.position.set(0, 0.035, 0.93); grp.add(pelvis);
      world.add(grp); BODY.skeleton = grp;
    }
    if (want('brain')) organ('brain', blobGeo(0.075, 1, 0.22, 4, 9), [0.82, 0.45, 0.52], [0, 0.008, 1.67], { scale: [0.85, 1.05, 0.72] });
    if (want('lungL')) organ('lungL', blobGeo(0.07, 1, 0.12, 3, 3), [0.82, 0.32, 0.38], [0.085, 0.01, 1.32], { scale: [0.95, 0.72, 1.6], alpha: 0.92 });
    if (want('lungR')) organ('lungR', blobGeo(0.07, 1, 0.12, 3, 4), [0.82, 0.32, 0.38], [-0.085, 0.01, 1.32], { scale: [0.95, 0.72, 1.6], alpha: 0.92 });
    if (want('heart')) organ('heart', blobGeo(0.05, 1, 0.16, 3, 5), [0.72, 0.07, 0.1], [0.022, -0.025, 1.31], { scale: [1, 0.9, 1.18], rot: [0, -20, -25] });
    if (want('liver')) organ('liver', blobGeo(0.065, 1, 0.14, 3, 6), [0.48, 0.12, 0.1], [-0.06, -0.01, 1.17], { scale: [1.65, 0.8, 0.72], rot: [0, 12, 0] });
    if (want('stomach')) organ('stomach', blobChain([[0.07, 0, 1.2], [0.075, -0.005, 1.165], [0.055, -0.01, 1.135], [0.025, -0.01, 1.125]], [0.04, 0.042, 0.033, 0.024], 11), [0.85, 0.36, 0.34], [0, 0, 0]);
    if (want('pancreas')) organ('pancreas', blobChain([[-0.03, 0.02, 1.115], [0.0, 0.02, 1.12], [0.03, 0.02, 1.125], [0.058, 0.02, 1.13]], [0.016, 0.018, 0.015, 0.012], 21), [0.92, 0.66, 0.38], [0, 0, 0]);
    for (const [n, s] of [['kidneyL', 1], ['kidneyR', -1]]) if (want(n)) organ(n, blobGeo(0.03, 1, 0.1, 3, 7 + s), [0.58, 0.14, 0.15], [s * 0.068, 0.045, 1.1], { scale: [0.7, 0.6, 1.25], rot: [0, s * 12, 0] });
    if (want('intestines')) {
      const pts = [];                                    // a meandering coil filling the belly
      for (let i = 0; i <= 44; i++) pts.push([0.075 * Math.sin(i * 0.95) * (0.75 + 0.25 * Math.sin(i * 0.31)), -0.022 + 0.018 * Math.sin(i * 0.63),
        1.065 - 0.12 * (i / 44) + 0.014 * Math.cos(i * 1.37)]);
      organ('intestines', tubeGeo(pts, 0.013, 260, 8), [0.85, 0.42, 0.4], [0, 0, 0]);
    }
    if (want('colon')) organ('colon', tubeGeo([[-0.09, -0.01, 0.94], [-0.105, -0.01, 1.02], [-0.1, -0.015, 1.09], [0, -0.03, 1.1], [0.1, -0.015, 1.09], [0.105, -0.01, 1.01], [0.08, -0.01, 0.95], [0.03, 0.0, 0.93]], 0.022, 80, 10), [0.66, 0.33, 0.3], [0, 0, 0]);
    if (want('bladder')) organ('bladder', blobGeo(0.03, 1, 0.1, 3, 8), [0.82, 0.62, 0.28], [0, -0.025, 0.9]);
    if (want('aorta')) organ('aorta', tubeGeo([[0.015, -0.01, 1.34], [0.03, 0.0, 1.42], [0.0, 0.04, 1.43], [-0.005, 0.045, 1.35], [-0.005, 0.045, 1.1], [0.0, 0.04, 0.96], [0.06, 0.02, 0.9], [0.09, 0.0, 0.6], [0.095, 0.0, 0.2]], 0.009, 120, 8), [0.8, 0.08, 0.1], [0, 0, 0], { glow: [1, 0.3, 0.3] });
    if (want('vena')) organ('vena', tubeGeo([[0.0, -0.005, 1.3], [-0.02, 0.03, 1.32], [-0.02, 0.035, 1.1], [-0.02, 0.03, 0.96], [-0.07, 0.02, 0.9], [-0.095, 0.0, 0.6], [-0.1, 0.0, 0.2]], 0.01, 120, 8), [0.15, 0.25, 0.8], [0, 0, 0], { glow: [0.4, 0.6, 1] });
    // a soft glowing ring under the feet
    const ring = mk(new T.RingGeometry(0.42, 0.45, 64), new T.MeshBasicMaterial({ color: new T.Color(0.3, 0.7, 1.0), transparent: true, opacity: 0.55, side: T.DoubleSide }));
    ring.position.set(0, 0, 0.002);
    const disc = mk(new T.CircleGeometry(0.42, 64), new T.MeshBasicMaterial({ color: new T.Color(0.08, 0.18, 0.32), transparent: true, opacity: 0.35 }));
    disc.position.set(0, 0, 0.001);
    return BODY;
  };
  YK.organs = BODY;

  // make an organ (or any object built with organ materials) glow from t0 to t1: soft in and out, optional pulsing
  YK.glow = function (obj, t0, t1, o = {}) {
    const mats = [];
    obj.traverse(c => { if (c.material && c.material.userData && c.material.userData.glow) mats.push(c.material); });
    if (o.color) mats.forEach(m => m.userData.glowColor.setRGB(...o.color));
    const amt = o.amount ?? 1, pulse = o.pulse ?? 0;
    const fn = t => {
      if (t < t0 || t > t1 + 0.4) return 0;
      const k = Math.min(ease(span(t, t0, t0 + 0.35)), 1 - ease(span(t, t1, t1 + 0.4)));
      return amt * k * (pulse ? 0.75 + 0.25 * Math.sin((t - t0) * pulse * 2 * Math.PI) : 1);
    };
    for (const m of mats) {                       // several glows on one organ: the strongest wins
      if (!m.userData.glowFns) { m.userData.glowFns = []; updaters.push(t => { m.userData.glow.value = Math.max(0, ...m.userData.glowFns.map(f => f(t))); }); }
      m.userData.glowFns.push(fn);
    }
    return obj;
  };
  // a beat: the object swells and settles (heart: bpm 70, amount 0.08)
  YK.pulse = function (obj, t0, t1, bpm = 70, amount = 0.08) {
    const s = obj.scale.clone();
    updaters.push(t => {
      if (t < t0 || t > t1) { obj.scale.copy(s); return; }
      const ph = ((t - t0) * bpm / 60) % 1, k = ph < 0.15 ? Math.sin(ph / 0.15 * Math.PI) : ph < 0.35 ? 0.5 * Math.sin((ph - 0.15) / 0.2 * Math.PI) : 0;
      obj.scale.copy(s).multiplyScalar(1 + amount * k);
    });
    return obj;
  };

  // ---------------------------------------------------------------- the micro set: a blood vessel cut open
  // YK.vessel({ at: [x, y, z], length: 8, radius: 0.6 }) lays a vessel along x, its front half cut away so you see
  // inside (y >= 0). Far from the body by default; frame it with YK.view('micro', V.F, ...). Returns { F, along }.
  const MICRO = [];
  YK.vessel = function (o = {}) {
    const [x, y, z] = o.at || [40, 0, 1.2], L = o.length ?? 8, r = o.radius ?? 0.6, wall = r * 0.12;
    const inner = new T.CylinderGeometry(r, r, L, 48, 1, true, 0, Math.PI); inner.rotateZ(Math.PI / 2);
    const outer = new T.CylinderGeometry(r + wall, r + wall, L, 48, 1, true, 0, Math.PI); outer.rotateZ(Math.PI / 2);
    const inMat = triMat({ tex: 'brown_mud', size: 0.6, tint: [1.7, 0.42, 0.4], sat: 0.5, bright: 1.35, rough: 0.45 });
    const outMat = organMat([0.75, 0.22, 0.22], { rough: 0.45 });
    const grp = new T.Group();
    // the half cylinder opens toward the camera: rotate so its open side faces -y
    const a = new T.Mesh(inner, inMat), b = new T.Mesh(outer, outMat);
    grp.add(a, b);                                      // angles 0..pi of a cylinder along x: the half at y >= 0
    inMat.side = T.DoubleSide;
    const cutMat = organMat([0.95, 0.55, 0.5], { rough: 0.6 });
    for (const s of [-1, 1]) { const e = new T.Mesh(new T.BoxGeometry(L, 0.004, wall), cutMat); e.position.set(0, 0, s * (r + wall / 2)); grp.add(e); }
    grp.position.set(x, y, z); world.add(grp);
    const v = { F: [x, y + r * 0.2, z], at: [x, y, z], length: L, radius: r, group: grp };
    v.along = [[x - Math.min(L / 2, 2.6), y + r * 0.35, z], [x + Math.min(L / 2, 2.6), y + r * 0.35, z]];   // the part the camera sees
    MICRO.push(v); return v;
  };

  // cells and molecules that drift along a path (or through a vessel): kind = red | white | platelet | glucose |
  // insulin | virus | bacteria | fat | antibody | oxygen. Returns the list of meshes (YK.vanish works on each).
  function cellGeo(kind, s) {
    if (kind === 'red') {
      // a squashed sphere, thin in the middle and thick at the rim (biconcave)
      const g = new T.SphereGeometry(s, 28, 18), p = g.attributes.position;
      for (let i = 0; i < p.count; i++) { const x = p.getX(i), y = p.getY(i), z = p.getZ(i), rho = Math.min(1, Math.hypot(x, z) / s);
        p.setY(i, (y / s) * s * 0.42 * (0.28 + 0.72 * rho * rho)); }
      g.computeVertexNormals(); return g;
    }
    if (kind === 'white') return blobGeo(s * 1.3, 1, 0.35, 3, 17);
    if (kind === 'platelet') return blobGeo(s * 0.45, 0.4, 0.4, 2, 23);
    if (kind === 'glucose') return new T.TorusGeometry(s * 0.6, s * 0.16, 6, 6);
    if (kind === 'fat') return blobGeo(s * 0.9, 1, 0.2, 2, 29);
    if (kind === 'bacteria') { const g = new T.CapsuleGeometry(s * 0.35, s * 1.3, 6, 12); g.rotateZ(Math.PI / 2); return g; }
    if (kind === 'oxygen') { const a = new T.SphereGeometry(s * 0.4, 12, 10); a.translate(-s * 0.28, 0, 0); const b = new T.SphereGeometry(s * 0.4, 12, 10); b.translate(s * 0.28, 0, 0); return blobChainGeo([a, b]); }
    if (kind === 'insulin') { const parts = [0, 1, 2].map(i => { const g = new T.SphereGeometry(s * 0.3, 12, 10); g.translate(s * 0.3 * Math.cos(i * 2.1), s * 0.3 * Math.sin(i * 2.1), 0); return g; }); return blobChainGeo(parts); }
    if (kind === 'antibody') {
      const parts = [[0, -0.5, 0, 0], [-0.35, 0.3, 0, 0.7], [0.35, 0.3, 0, -0.7]].map(([px, py, , rz]) => { const g = new T.CylinderGeometry(s * 0.12, s * 0.12, s * 0.9, 8); g.rotateZ(rz); g.translate(px * s, py * s, 0); return g; });
      return blobChainGeo(parts);
    }
    if (kind === 'virus') {
      const parts = [new T.SphereGeometry(s * 0.6, 16, 12)], r = rng(5);
      for (let i = 0; i < 18; i++) { const d = new T.Vector3(r() - 0.5, r() - 0.5, r() - 0.5).normalize(); const g = new T.CylinderGeometry(s * 0.05, s * 0.05, s * 0.3, 6); g.translate(0, s * 0.72, 0); const q = new T.Quaternion().setFromUnitVectors(new T.Vector3(0, 1, 0), d); g.applyQuaternion(q); parts.push(g); const k = new T.SphereGeometry(s * 0.09, 8, 6); k.translate(d.x * s * 0.9, d.y * s * 0.9, d.z * s * 0.9); parts.push(k); }
      return blobChainGeo(parts);
    }
    return blobGeo(s, 1, 0.3, 2, 3);
  }
  function blobChainGeo(list) {
    const parts = list.map(g => (g.index ? g.toNonIndexed() : g));
    let n = 0; parts.forEach(g => { n += g.attributes.position.count; });
    const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3); let o = 0;
    for (const g of parts) { if (!g.attributes.normal) g.computeVertexNormals(); pos.set(g.attributes.position.array, o * 3); nor.set(g.attributes.normal.array, o * 3); o += g.attributes.position.count; }
    const geo = new T.BufferGeometry(); geo.setAttribute('position', new T.BufferAttribute(pos, 3)); geo.setAttribute('normal', new T.BufferAttribute(nor, 3)); return geo;
  }
  const CELL_COLORS = { red: [0.75, 0.05, 0.07], white: [0.92, 0.9, 0.85], platelet: [0.95, 0.8, 0.55], glucose: [1.0, 0.75, 0.15],
    insulin: [0.25, 0.55, 1.0], virus: [0.35, 0.85, 0.3], bacteria: [0.6, 0.3, 0.85], fat: [1.0, 0.85, 0.35], antibody: [0.95, 0.95, 1.0], oxygen: [0.95, 0.35, 0.3] };
  YK.cells = function (kind, t0, t1, o = {}) {
    const path = o.path || (MICRO.length ? MICRO[MICRO.length - 1].along : null);
    if (!path) throw new Error('YK.cells needs o.path or a YK.vessel() first');
    const curve = new T.CatmullRomCurve3(path.map(p => new T.Vector3(...p)));
    const n = o.n ?? 22, size = o.size ?? (MICRO.length && !o.path ? 0.14 : 0.012), spread = o.spread ?? (MICRO.length && !o.path ? 0.32 : 0.01);
    const geo = cellGeo(kind, size), mat = organMat(o.color || CELL_COLORS[kind] || [0.8, 0.8, 0.8], { rough: 0.35, glow: o.glow });
    const r = rng(o.seed ?? (kind.length * 7 + n)), speed = o.speed ?? 0.12, len = curve.getLength();
    const out = [];
    for (let i = 0; i < n; i++) {
      const m = mk(geo, mat); const c = { m, ph: r(), dx: (r() - 0.5) * 2 * spread, dy: r() * spread, dz: (r() - 0.5) * 2 * spread, sp: [r() * 3, r() * 3, r() * 3], v: 0.75 + 0.5 * r() };
      out.push(m);
      updaters.push(t => {
        const on = t >= t0 && t <= t1;
        m.visible = on; if (!on) return;
        const u = (c.ph + (t - t0) * speed * c.v / Math.max(0.3, len) * 8) % 1;
        const p = curve.getPointAt(u);
        m.position.set(p.x + c.dx, p.y + c.dy, p.z + c.dz);
        m.rotation.set(c.sp[0] * t, c.sp[1] * t, c.sp[2] * t);
        const s = Math.min(ease(span(t, t0, t0 + 0.4)), 1); m.scale.setScalar(Math.max(0.001, s));
      });
    }
    return out;
  };

  // ---------------------------------------------------------------- camera
  // framings around a focus F, always from the open side (y < 0): offset, look, lens (mm, 36 mm tall sensor)
  let VIEWS = {
    wide: [[0.6, -13.0, 4.4], [0.0, 5.0, 0.4], 34], section: [[0.0, -9.0, 1.2], [0.0, 0.8, -0.5], 34],
    close: [[0.6, -5.6, 0.35], [0.0, 0.6, -0.45], 32], high: [[0.0, -7.0, 5.2], [0.0, 1.8, -0.5], 32],
    left: [[-6.0, -8.0, 2.6], [0.0, 1.2, -0.4], 32], right: [[6.0, -8.0, 2.6], [0.0, 1.2, -0.4], 32],
    low: [[1.0, -7.0, -0.3], [0.0, 0.8, -0.2], 32], house: [[0.5, -9.0, 1.2], [0.3, 9.0, 3.8], 34],
  };
  YK.VIEWS = VIEWS;
  const add3 = (a, b) => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
  const mix3 = (a, b, s) => [lerp(a[0], b[0], s), lerp(a[1], b[1], s), lerp(a[2], b[2], s)];
  YK.view = function (kind, F, t0, t1, o = {}) {
    const [off, look, ln] = VIEWS[kind], push = o.push ?? 0.1, slide = o.slide ?? 0, lift = o.lift ?? 0;
    const pa = add3(F, off), la = add3(F, look);
    const pb = add3(mix3(pa, la, push), [slide, 0, lift]);
    return { t0, t1, a: [pa, la], b: [pb, add3(la, [slide * 0.3, 0, 0])], lens: o.lens || ln };
  };
  YK.cuts = function (t0, t1, F, kinds, every = 2.2, push = 0.1) {
    const n = Math.max(1, Math.round((t1 - t0) / every)), out = [];
    for (let i = 0; i < n; i++)
      out.push(YK.view(kinds[i % kinds.length], F, t0 + (t1 - t0) * i / n, t0 + (t1 - t0) * (i + 1) / n, { push, slide: i % 2 ? 0.5 : -0.5 }));
    return out;
  };
  YK.shots = list => { shots = (Array.isArray(list) ? list : []).filter(s => s && s.a && s.b).sort((p, q) => p.t0 - q.t0); };
  function placeCamera(t) {
    const sh = shots.find(s => t >= s.t0 && t < s.t1) || shots[shots.length - 1];
    if (!sh) return;
    const s = ease(span(t, sh.t0, sh.t1), 'linear');
    const p = mix3(sh.a[0], sh.b[0], s), l = mix3(sh.a[1], sh.b[1], s);
    cam.fov = 2 * Math.atan(18 / sh.lens) * 180 / Math.PI; cam.updateProjectionMatrix();
    cam.position.copy(V(...p)); cam.up.set(0, 1, 0); cam.lookAt(V(...l));
  }

  // ---------------------------------------------------------------- captions: one word at a time
  YK.captions = list => { captions = list; };   // [[t, 'word'], ...]
  function placeCaption(t) {
    if (!capEl) return;
    let cur = null;
    for (const c of captions) if (t >= c[0]) cur = c;
    const end = cur && (cur[2] ?? Infinity);
    if (!cur || t > end) { capEl.style.opacity = 0; return; }
    capEl.textContent = cur[1];
    const s = span(t, cur[0], cur[0] + 0.09);
    capEl.style.opacity = 1;
    capEl.style.transform = `translate(-50%, -50%) scale(${0.84 + 0.16 * ease(s, 'out')})`;
  }

  // ---------------------------------------------------------------- setup and the frame loop
  let envDone = false, sky;
  const lights = {};
  YK.init = function (o) {
    W = o.width; H = o.height;
    renderer = new T.WebGLRenderer({ canvas: o.canvas, antialias: o.antialias ?? true, preserveDrawingBuffer: true });
    renderer.setSize(W, H, false);
    renderer.outputColorSpace = T.SRGBColorSpace;
    renderer.toneMapping = T.ACESFilmicToneMapping; renderer.toneMappingExposure = o.exposure ?? 1.0;
    renderer.shadowMap.enabled = o.shadows ?? true; renderer.shadowMap.type = o.shadowType === 'soft' ? T.PCFSoftShadowMap : T.PCFShadowMap;
    scene = new T.Scene();
    world = new T.Group(); world.rotation.x = -Math.PI / 2; scene.add(world);
    cam = new T.PerspectiveCamera(50, W / H, 0.05, 600);
    sky = tex('sky'); sky.mapping = T.EquirectangularReflectionMapping;
    scene.background = sky;
    mats();
    // sun from the front left, high, so the cut face and the house front are lit; a soft fill from behind
    const sun = lights.sun = new T.DirectionalLight(new T.Color(1.0, 0.96, 0.9), o.sun ?? 2.7);
    sun.position.copy(V(-14, -26, 27)); sun.target.position.copy(V(0, 4, 0)); scene.add(sun, sun.target);
    sun.castShadow = true; sun.shadow.mapSize.set(o.shadowSize ?? 1024, o.shadowSize ?? 1024);
    Object.assign(sun.shadow.camera, { left: -26, right: 26, top: 26, bottom: -26, near: 1, far: 120 });
    sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.03;
    const fill = lights.fill = new T.DirectionalLight(new T.Color(1.0, 0.9, 0.78), o.fill ?? 0.9);
    fill.position.copy(V(7, 34, 18)); scene.add(fill);
    scene.add(lights.hemi = new T.HemisphereLight(new T.Color(0.75, 0.85, 1.0), new T.Color(0.35, 0.3, 0.22), o.ambient ?? 0.5));
    capEl = o.caption || null;
    YK.three = { renderer, scene, world, camera: cam };
    return YK;
  };
  function ensureEnv() {
    if (envDone) return;
    const img = document.getElementById('tx_sky');
    if (!(img.complete && img.naturalWidth)) return;
    const pm = new T.PMREMGenerator(renderer);
    scene.environment = pm.fromEquirectangular(sky).texture; pm.dispose(); envDone = true;
  }
  YK.finish = function () { flush(); };
  // run every per-frame update at these times without drawing: returns the errors a scene would throw mid-render
  YK.probe = function (times) {
    const errs = [];
    for (const t of times) {
      try { updatePits(t); for (const fn of updaters) fn(t); placeCamera(t); placeCaption(t); }
      catch (e) { errs.push(`at ${t.toFixed(1)} s: ${(e && e.message) || e}`); if (errs.length >= 4) break; }
    }
    return errs;
  };
  YK.renderAt = function (ms) {
    const t = ms / 1000;
    ensureEnv();
    updatePits(t);
    for (const fn of updaters) fn(t);
    placeCamera(t); placeCaption(t);
    renderer.render(scene, cam);
  };
  window.YK = YK;
})();
