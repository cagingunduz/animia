// Animave render service — turns Claude-written HyperFrames HTML into MP4 / PNG frames.
//
// Runs as its own Railway service with NO secrets in its environment: the code it
// executes is model-written, so it gets a scratch directory, a stripped env and a
// hard timeout. The main backend talks to it over Railway private networking.
//
//   GET  /health
//   POST /lint      { files, binary_files? }                       -> { ok, findings }
//   POST /render    { files, binary_files?, quality?, fps? }        -> video/mp4  (422 JSON on failure)
//   POST /snapshot  { files, binary_files?, at: [seconds] }         -> { frames: [{ at, png }] }
//
// `files` maps project-relative paths to text (index.html, compositions/*.html, …);
// `binary_files` maps paths to base64 (logos, reference stills).

import http from 'node:http';
import { spawn } from 'node:child_process';
import { mkdtemp, mkdir, writeFile, readFile, readdir, rm, copyFile, realpath } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PORT = Number(process.env.PORT || 8080);
const TOKEN = process.env.RENDER_TOKEN || '';
const MAX_CONCURRENT = Number(process.env.MAX_CONCURRENT_RENDERS || 2);
const TIMEOUT_MS = Number(process.env.RENDER_TIMEOUT_MS || 10 * 60 * 1000);
const MAX_BODY = 40 * 1024 * 1024;
const HF_BIN = path.join(HERE, 'node_modules', '.bin', 'hyperframes');
const ANIME_JS = path.join(HERE, 'node_modules', 'animejs', 'dist', 'bundles', 'anime.umd.min.js');

// The child process only ever sees these variables.
const CHILD_ENV = {
  PATH: process.env.PATH,
  HOME: '/tmp/hf-home',
  DO_NOT_TRACK: '1',
  CI: '1',
  CONTAINER: 'true',
  ...(process.env.HYPERFRAMES_CHROME_PATH ? { HYPERFRAMES_CHROME_PATH: process.env.HYPERFRAMES_CHROME_PATH } : {}),
  ...(process.env.PRODUCER_HEADLESS_SHELL_PATH ? { PRODUCER_HEADLESS_SHELL_PATH: process.env.PRODUCER_HEADLESS_SHELL_PATH } : {}),
  PUPPETEER_SKIP_CHROMIUM_DOWNLOAD: 'true',
  PRODUCER_LOW_MEMORY_MODE: process.env.PRODUCER_LOW_MEMORY_MODE || 'false',
};

// ─── tiny semaphore so Chrome doesn't eat the box ───
let active = 0;
const waiters = [];
async function acquire() {
  if (active < MAX_CONCURRENT) { active++; return; }
  await new Promise(r => waiters.push(r));
  active++;
}
function release() {
  active--;
  const next = waiters.shift();
  if (next) next();
}

function run(args, cwd) {
  return new Promise(resolve => {
    const child = spawn(HF_BIN, args, { cwd, env: CHILD_ENV });
    let out = '';
    const keep = d => { out += d.toString(); if (out.length > 200_000) out = out.slice(-200_000); };
    child.stdout.on('data', keep);
    child.stderr.on('data', keep);
    const timer = setTimeout(() => { out += '\n[render-service] timeout, killed'; child.kill('SIGKILL'); }, TIMEOUT_MS);
    child.on('close', code => { clearTimeout(timer); resolve({ code, out }); });
    child.on('error', err => { clearTimeout(timer); resolve({ code: -1, out: String(err) }); });
  });
}

function safeRel(p) {
  const norm = path.posix.normalize(String(p).replace(/\\/g, '/'));
  if (!norm || norm.startsWith('/') || norm.startsWith('..') || norm.includes('/../') || norm.startsWith('.hyperframes')) {
    throw new Error(`bad path: ${p}`);
  }
  return norm;
}

async function writeProject(body) {
  const files = body.files || {};
  if (!files['index.html']) throw new Error('files["index.html"] is required');
  const dir = await realpath(await mkdtemp(path.join(tmpdir(), 'hf-')));
  for (const [rel, content] of Object.entries(files)) {
    const dest = path.join(dir, safeRel(rel));
    await mkdir(path.dirname(dest), { recursive: true });
    await writeFile(dest, String(content));
  }
  for (const [rel, b64] of Object.entries(body.binary_files || {})) {
    const dest = path.join(dir, safeRel(rel));
    await mkdir(path.dirname(dest), { recursive: true });
    await writeFile(dest, Buffer.from(String(b64), 'base64'));
  }
  // Compositions load anime.js and the Animave motion kit from here, never from a CDN.
  await mkdir(path.join(dir, 'lib'), { recursive: true });
  await copyFile(ANIME_JS, path.join(dir, 'lib', 'anime.umd.min.js'));
  await copyFile(path.join(HERE, 'kit.js'), path.join(dir, 'lib', 'kit.js'));
  await copyFile(path.join(HERE, 'kit.css'), path.join(dir, 'lib', 'kit.css'));
  return dir;
}

function tail(s, n = 6000) { return s.length > n ? s.slice(-n) : s; }

async function lint(dir) {
  const { code, out } = await run(['lint', '.', '--json'], dir);
  let parsed = null;
  try { parsed = JSON.parse(out.slice(out.indexOf('{'))); } catch { /* not json */ }
  const findings = (parsed?.findings || []).map(f => ({
    code: f.code, severity: f.severity, message: f.message, fixHint: f.fixHint,
    file: f.file ? path.relative(dir, f.file) : undefined,
  }));
  const ok = parsed ? parsed.ok === true : code === 0;
  return { ok, findings, raw: parsed ? undefined : tail(out) };
}

async function handleLint(body) {
  const dir = await writeProject(body);
  try { return { status: 200, json: await lint(dir) }; }
  finally { rm(dir, { recursive: true, force: true }).catch(() => {}); }
}

async function handleRender(body) {
  const dir = await writeProject(body);
  try {
    const l = await lint(dir);
    if (!l.ok) return { status: 422, json: { error: 'lint failed', stage: 'lint', findings: l.findings, log: l.raw } };
    const out = path.join(dir, 'out.mp4');
    const quality = ['draft', 'standard', 'high'].includes(body.quality) ? body.quality : 'standard';
    const args = ['render', '.', '--output', out, '--quality', quality, '--workers', '1'];
    if (body.fps) args.push('--fps', String(Math.max(1, Math.min(60, Number(body.fps) || 30))));
    const r = await run(args, dir);
    let video = null;
    try { video = await readFile(out); } catch { /* missing */ }
    if (r.code !== 0 || !video) return { status: 422, json: { error: 'render failed', stage: 'render', log: tail(r.out) } };
    return { status: 200, binary: video, type: 'video/mp4' };
  } finally { rm(dir, { recursive: true, force: true }).catch(() => {}); }
}

async function handleSnapshot(body) {
  const at = (Array.isArray(body.at) ? body.at : []).map(Number).filter(n => Number.isFinite(n) && n >= 0).slice(0, 24);
  if (!at.length) return { status: 400, json: { error: 'at: [seconds] required' } };
  const dir = await writeProject(body);
  try {
    const outDir = path.join(dir, 'snaps');
    const r = await run(['snapshot', '.', '--at', at.join(','), '--no-end', '--output', outDir, '--describe', 'false'], dir);
    let names = [];
    try { names = (await readdir(outDir)).filter(n => n.endsWith('.png') && n.startsWith('frame-')).sort(); } catch { /* none */ }
    if (!names.length) return { status: 422, json: { error: 'snapshot failed', stage: 'snapshot', log: tail(r.out) } };
    const frames = [];
    for (let i = 0; i < names.length; i++) {
      frames.push({ at: at[i] ?? null, png: (await readFile(path.join(outDir, names[i]))).toString('base64') });
    }
    return { status: 200, json: { frames } };
  } finally { rm(dir, { recursive: true, force: true }).catch(() => {}); }
}

const ROUTES = { '/lint': handleLint, '/render': handleRender, '/snapshot': handleSnapshot };

function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', c => {
      size += c.length;
      if (size > MAX_BODY) { reject(new Error('body too large')); req.destroy(); return; }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

function send(res, status, json) {
  res.writeHead(status, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(json));
}

http.createServer(async (req, res) => {
  if (req.method === 'GET' && (req.url === '/health' || req.url === '/')) {
    return send(res, 200, { ok: true, active, queued: waiters.length });
  }
  const handler = req.method === 'POST' ? ROUTES[req.url] : null;
  if (!handler) return send(res, 404, { error: 'not found' });
  if (TOKEN && req.headers['x-render-token'] !== TOKEN) return send(res, 401, { error: 'unauthorized' });

  let body;
  try { body = JSON.parse(await readBody(req)); }
  catch (e) { return send(res, 400, { error: `bad request: ${e.message}` }); }

  await acquire();
  try {
    const r = await handler(body);
    if (r.binary) {
      res.writeHead(r.status, { 'Content-Type': r.type, 'Content-Length': r.binary.length });
      res.end(r.binary);
    } else send(res, r.status, r.json);
  } catch (e) {
    send(res, 500, { error: String(e?.message || e) });
  } finally {
    release();
  }
}).listen(PORT, '::', () => console.log(`[render-service] listening on ${PORT}`));
