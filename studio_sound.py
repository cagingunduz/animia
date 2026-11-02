"""Style Studio sound: the voice on top, the style's foley (made in code from the kit's own events), a music bed
ducked under the voice, the film's extra effects, brought to -14 LUFS (stereo 48 kHz).

Foley ported from the MIT-licensed github.com/lemomo-ai/lemo-opuscar (styles/whiteboard/demo/mix.py: every marker
stroke makes its own sound shaped by the hand-speed curve, panned to where it is drawn).
"""

import json
import re
import subprocess

import math

import numpy as np

SR = 48000


def _decode(path: str) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype(np.float64) / 32768


class _Synth:
    def __init__(self, seed=11):
        self.rng = np.random.default_rng(seed)
        self._band = {}

    def tt(self, d):
        return np.arange(int(d * SR)) / SR

    def bp(self, x, lo, hi):
        f = np.fft.rfft(x); fr = np.fft.rfftfreq(len(x), 1 / SR)
        f[(fr < lo) | (fr > hi)] = 0
        return np.fft.irfft(f, len(x))

    def band(self, n, lo, hi):
        k = (round(lo), round(hi))
        if k not in self._band:
            b = self.bp(self.rng.standard_normal(SR * 8), lo, hi); self._band[k] = b / (np.abs(b).max() + 1e-9) * 2.2
        b = self._band[k]; i = int(self.rng.integers(0, len(b) - n - 1)); return b[i:i + n]

    def ring(self, fs, taus, amps, d):
        x = np.zeros(int(d * SR)); t = self.tt(d)
        for f, ta, am in zip(fs, taus, amps):
            x += np.sin(2 * np.pi * f * t + self.rng.uniform(0, 6)) * np.exp(-t / ta) * am
        return x

    # ── whiteboard
    def marker(self, dur, length, kind, pen, z=1.0):
        d = max(.03, dur); n = int(d * SR); u = np.linspace(0, 1, n)
        v = 1 - .8 * np.cos(2 * np.pi * u)
        if kind == 'dash':
            v = np.ones(n) * 1.2
        a = (v / 1.8) ** .8 * np.minimum(1, u * d / .006) * np.minimum(1, (1 - u) * d / .012)
        br = {'black': 1.0, 'orange': 1.12, 'blue': .92}.get(pen, 1.0)
        hiss = self.band(n, 2200 * br, 7500 * br) * (.55 + .45 * v / 1.8)
        body = self.band(n, 500 * br, 1500 * br) * .45
        x = (hiss + body) * a
        if kind != 'dash' and length > 140 and self.rng.random() < .28:      # the dry-erase squeak
            s0 = self.rng.uniform(.15, .55) * d; sd = min(d - s0, self.rng.uniform(.06, .16))
            if sd > .03:
                m = int(sd * SR); ts = np.arange(m) / SR; f0 = self.rng.uniform(1500, 2600) * br
                f = f0 * (1 + .03 * np.sin(2 * np.pi * self.rng.uniform(7, 13) * ts))
                sq = (np.sin(2 * np.pi * np.cumsum(f) / SR) + .3 * np.sin(4 * np.pi * np.cumsum(f) / SR)) * np.sin(np.pi * ts / sd) ** 1.5 * .35
                i0 = int(s0 * SR); x[i0:i0 + m] += sq[:len(x) - i0]
        k = int(.004 * SR); x[:k] += self.bp(self.rng.standard_normal(k), 2500, 6500) * np.linspace(1, 0, k) * 1.4
        return x * .32 * min(1.3, z ** .5)

    def tap(self, z=1.0):
        n = int(.03 * SR); return self.bp(self.rng.standard_normal(n), 1800, 6000) * np.exp(-self.tt(.03) / .004) * 1.2 * .3 * min(1.3, z ** .5)

    def magnet(self, big=0):
        d = .5; x = np.zeros(int(d * SR)); k = int(.005 * SR)
        x[:k] += self.bp(self.rng.standard_normal(k), 2000, 9000) * np.linspace(1, 0, k) * 1.5
        x += self.ring([830, 1370, 2210, 3120], [.07, .05, .035, .02], [.35, .25, .15, .08], d)
        x += self.ring([140 + 30 * big], [.09 + .06 * big], [.9 + .6 * big], d) * .9
        return x * (.55 + .35 * big)

    def eraser(self, d, rewind=False):
        n = int(d * SR); t = self.tt(d)
        base = self.bp(self.rng.standard_normal(n), 250, 2600) * .6 + self.bp(self.rng.standard_normal(n), 2500, 6000) * .15
        mod = .75 + .25 * np.sin(2 * np.pi * 9 * t) if rewind else .45 + .55 * np.abs(np.sin(np.pi * t / d * 7))
        return base * mod * np.minimum(1, t / .04) * np.minimum(1, (d - t) / .06) * .5

    def whoosh(self, d, v=1.0):
        n = int(d * SR); t = self.tt(d)
        return self.bp(self.rng.standard_normal(n), 300, 2400) * np.sin(np.pi * t / d) ** 2 * .35 * v

    # ── cartoon (sci-fi sitcom): short synthetic hits, after the lemo-opuscar demo's code-made effects
    def sweep(self, f0, f1, d, shape="sin", curve=1.0):
        t = self.tt(d); u = (t / d) ** curve; f = f0 * (f1 / f0) ** u
        ph = 2 * np.pi * np.cumsum(f) / SR
        return np.sin(ph) if shape == "sin" else np.sign(np.sin(ph)) * .5 + np.sin(ph) * .5

    def toon(self, ty, d=None):
        t = lambda dd: self.tt(dd)
        env = lambda dd, a=.005, r=None: np.minimum(1, t(dd) / a) * np.exp(-t(dd) / (r or dd / 3))
        if ty == "pop":
            return self.sweep(300, 900, .07) * env(.07, .002, .025) * .6
        if ty == "boing":
            dd = .45; f = 180 * (1 + .35 * np.sin(2 * np.pi * 9 * t(dd)) * np.exp(-t(dd) / .2))
            return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(dd, .004, .15) * .55
        if ty == "suck":
            dd = .55; return (self.bp(self.rng.standard_normal(int(dd * SR)), 400, 3000) * .4 + self.sweep(900, 120, dd) * .25) * np.sin(np.pi * t(dd) / dd) ** 2
        if ty == "whoosh":
            return self.whoosh(d or .45, 1.3)
        if ty == "portalOpen":
            dd = 1.1; wob = 1 + .08 * np.sin(2 * np.pi * 7 * t(dd))
            x = self.sweep(80, 420, dd, curve=.5) * wob * .35 + self.bp(self.rng.standard_normal(int(dd * SR)), 200, 1800) * .25
            return x * np.minimum(1, t(dd) / .05) * np.exp(-t(dd) / .6)
        if ty == "portalClose":
            dd = .6; return (self.sweep(500, 70, dd) * .4 + self.bp(self.rng.standard_normal(int(dd * SR)), 200, 1500) * .2) * np.exp(-t(dd) / .25) * np.minimum(1, t(dd) / .01)
        if ty == "click":
            n = int(.025 * SR); return self.bp(self.rng.standard_normal(n), 2000, 7000) * np.exp(-self.tt(.025) / .003) * .7
        if ty == "slam":
            dd = .5; return (self.ring([70, 110], [.15, .08], [1, .5], dd) + self.bp(self.rng.standard_normal(int(dd * SR)), 100, 2000) * np.exp(-t(dd) / .05)) * .6
        if ty == "thud":
            dd = .3; return self.ring([90, 140], [.07, .04], [1, .4], dd) * .7
        if ty == "squish":
            dd = .3; return self.bp(self.rng.standard_normal(int(dd * SR)), 300, 1500) * (1 + np.sin(2 * np.pi * 30 * t(dd))) * env(dd, .01, .1) * .5
        if ty == "blip":
            return self.sweep(900, 1500, .09) * env(.09, .003, .04) * .35
        if ty == "gulp":
            dd = .22; return self.sweep(160, 380, dd) * np.sin(np.pi * t(dd) / dd) ** 2 * .5
        if ty == "step":
            dd = .08; return self.bp(self.rng.standard_normal(int(dd * SR)), 150, 1200) * np.exp(-t(dd) / .02) * .4
        return None


def foley(kind: str, events: list[dict], total: float) -> np.ndarray:
    """The style's foley as a stereo buffer (N, 2)."""
    N = int(total * SR); out = np.zeros((N, 2))
    if kind not in ("marker", "toon") or not events:
        return out
    S = _Synth()

    def put(x, t, g=1.0, pan=0.0):
        s = int(t * SR)
        if s < 0 or s >= N:
            return
        x = np.asarray(x)[:N - s] * g
        out[s:s + len(x), 0] += x * np.sqrt(.5 * (1 - pan)); out[s:s + len(x), 1] += x * np.sqrt(.5 * (1 + pan))

    num = lambda v, d: float(v) if isinstance(v, (int, float)) and math.isfinite(v) else d
    for e in events[:4000]:
        if not isinstance(e, dict) or num(e.get("t"), None) is None:
            continue
        e = {k: v for k, v in e.items() if v is not None}
        ty, t = e.get("type"), num(e.get("t"), 0); pan = num(e.get("pan"), 0); z = num(e.get("z"), 1)
        off = 10 ** (-9 / 20) if e.get("on", 1) == 0 else 1.0
        if ty in ("stroke", "write", "dash"):
            put(S.marker(float(e.get("dur", .1)), float(e.get("len", 50)), ty, e.get("pen"), z), t, off * (.8 if ty == "write" else 1.0), pan)
        elif ty == "tap":
            put(S.tap(z), t, off, pan)
        elif ty == "magnet":
            put(S.magnet(e.get("big", 0)), t, 1.1, -.05)
        elif ty == "erase":
            put(S.eraser(float(e.get("dur", .5))), t, 1.1, .1)
        elif ty == "rewind":
            put(S.eraser(float(e.get("dur", .5)), True), t, .8, -.2)
        elif ty == "whoosh" and kind == "marker":
            put(S.whoosh(float(e.get("dur", .5))), t, 1.0, 0)
        elif kind == "toon":
            x = S.toon(str(ty), num(e.get("d"), None))
            if x is not None:
                put(x, t, num(e.get("v"), 1.0), pan)
    return out


def mix(voice_wav: str, timing: dict, total: float, out_wav: str, *, foley_kind: str = "", foley_events: list | None = None,
        bed: str | None = None, bed_db: float = -14.0, spec: dict | None = None, lib: dict | None = None) -> dict:
    """voice + foley + bed + extra effects -> out_wav (48 kHz stereo, -14 LUFS). bed_db = the bed under the voice."""
    N = int(total * SR); lib = lib or {}; spec = spec or {}; skipped = []
    v = _decode(voice_wav); voice = np.zeros(N); voice[:min(N, len(v))] = v[:N]

    def when(at):
        if isinstance(at, (int, float)):
            return float(at)
        m = re.match(r"^\s*([^@+]+)@(\d+)\s*([+-]\s*[\d.]+)?\s*$", str(at))
        if not m:
            return float(at)
        word, li, off = m.group(1).strip().lower(), int(m.group(2)), float((m.group(3) or "0").replace(" ", ""))
        L = timing["lines"][li]
        for w in L["words"]:
            if re.sub(r"[^\w']", "", w["w"].lower()) == re.sub(r"[^\w']", "", word):
                return w["s"] + off
        return L["start"] + off

    fol = foley(foley_kind, foley_events or [], total)
    # music bed: looped, ducked under the voice (about 6 dB while a line plays), faded at both ends
    music = np.zeros(N)
    if bed and bed in lib:
        try:
            b = _decode(lib[bed])
            if len(b) > SR:
                xf = int(0.5 * SR); loop = b.copy()
                reps = int(np.ceil(N / (len(loop) - xf))) + 1
                music = np.zeros(reps * (len(loop) - xf) + xf)
                for k in range(reps):
                    s = k * (len(loop) - xf); seg = loop.copy()
                    if k: seg[:xf] *= np.linspace(0, 1, xf)
                    seg[-xf:] *= np.linspace(1, 0, xf)
                    music[s:s + len(seg)] += seg
                music = music[:N]
        except Exception as e:
            skipped.append(f"bed: {e!r}")
    t = np.arange(N) / SR
    vslow = np.convolve(np.abs(voice), np.ones(SR // 5) / (SR // 5), mode="same")
    talking = vslow > 0.01
    if np.abs(music).max() > 0:
        music *= 1 - 0.5 * np.clip(vslow / 0.03, 0, 1)
        music *= np.clip(t / 0.8, 0, 1) * np.clip((total - t) / 1.2, 0, 1)
        vr = np.sqrt(np.mean(voice[talking] ** 2)) if talking.any() else 0.1
        mr = np.sqrt(np.mean(music[talking] ** 2)) + 1e-9 if talking.any() else 1.0
        music *= vr * 10 ** (bed_db / 20) / mr
    # extra effects from the film (the generated library)
    fx = np.zeros(N)
    for c in (spec.get("sfx") or [])[:40]:
        kind = str(c.get("type", ""))
        if kind not in lib:
            skipped.append(f"no sound {kind}"); continue
        try:
            s = int(when(c["at"]) * SR); x = _decode(lib[kind])[:int(3 * SR)]
        except Exception as e:
            skipped.append(f"{c}: {e!r}"); continue
        if 0 <= s < N:
            x = x / (np.abs(x).max() + 1e-9); e = min(N, s + len(x)); fx[s:e] += float(c.get("vol", 0.6)) * x[:e - s]
    # foley sits about 11 dB under the voice
    if np.abs(fol).max() > 0:
        vr = np.sqrt(np.mean(voice[talking] ** 2)) if talking.any() else 0.1
        fr = np.sqrt(np.mean(fol[np.abs(fol).max(1) > 1e-4] ** 2)) + 1e-9
        fol *= vr * 10 ** (-11 / 20) / fr
    mono = voice + music + 0.4 * fx
    st = np.stack([mono, mono], 1) + fol
    st /= max(1.0, np.abs(st).max() / 0.98)
    raw = out_wav[:-4] + "_raw.wav"
    import soundfile as sf
    sf.write(raw, st.astype(np.float32), SR)

    def measure(path):
        m = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
        return float(json.loads(m[m.rindex("{"):m.rindex("}") + 1])["input_i"])

    gain = -14 - measure(raw)
    for k in range(2):
        if k:
            gain += -14 - measure(out_wav)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", f"volume={gain:.2f}dB,alimiter=limit=0.84:level=false",
                        "-ar", str(SR), "-ac", "2", out_wav], check=True)
    return {"lufs": round(measure(out_wav), 1), "skipped": skipped[:10]}
