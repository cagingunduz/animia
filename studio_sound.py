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

    # ── paper lightbox: paper and light
    def paper(self, ty, d=None):
        t = self.tt
        if ty == "click":
            n = int(.04 * SR); return (self.bp(self.rng.standard_normal(n), 1500, 6000) * np.exp(-t(.04) / .004) + self.ring([2400], [.01], [.3], .04)) * .5
        if ty == "shimmer":
            dd = d or 1.6; x = np.zeros(int(dd * SR))
            for f in (1568, 2093, 2637, 3136, 3951):
                x += np.sin(2 * np.pi * f * t(dd) + self.rng.uniform(0, 6)) * (.5 + .5 * np.sin(2 * np.pi * self.rng.uniform(3, 7) * t(dd)))
            return x * np.minimum(1, t(dd) / (dd * .4)) * np.exp(-np.maximum(0, t(dd) - dd * .4) / (dd * .3)) * .05
        if ty == "rustle":
            dd = d or .6; return self.bp(self.rng.standard_normal(int(dd * SR)), 1200, 8000) * (.4 + .6 * np.abs(np.sin(np.pi * t(dd) / dd * 5))) * np.sin(np.pi * t(dd) / dd) * .22
        if ty == "slide":
            dd = d or .7; return self.bp(self.rng.standard_normal(int(dd * SR)), 700, 4500) * np.sin(np.pi * t(dd) / dd) ** 1.5 * .2
        if ty == "tap":
            n = int(.06 * SR); return self.bp(self.rng.standard_normal(n), 400, 3000) * np.exp(-t(.06) / .008) * .6
        if ty == "chime":
            return self.ring([1318, 1976, 2637], [.9, .6, .4], [.25, .14, .08], 2.0)
        if ty == "whoosh":
            return self.whoosh(d or .8, .8)
        if ty == "thud":
            return self.ring([80, 130], [.12, .06], [.8, .3], .4)
        return None

    # ── teardown: the materials
    def teardown(self, ty, d=None):
        t = self.tt
        if ty == "lift":
            dd = d or .7; return self.bp(self.rng.standard_normal(int(dd * SR)), 500, 5000) * np.sin(np.pi * t(dd) / dd) ** 2 * .22
        if ty == "whoosh":
            return self.whoosh(d or .9, 1.0)
        if ty == "land":
            dd = .25; return (self.ring([620, 1340, 2310], [.03, .02, .012], [.5, .3, .15], dd) + self.bp(self.rng.standard_normal(int(dd * SR)), 800, 5000) * np.exp(-t(dd) / .01) * .6) * .6
        if ty == "clack":
            dd = .12; return (self.ring([900, 1900], [.018, .01], [.6, .3], dd) + self.bp(self.rng.standard_normal(int(dd * SR)), 1500, 7000) * np.exp(-t(dd) / .006)) * .55
        if ty == "click":
            dd = .15; return (self.bp(self.rng.standard_normal(int(dd * SR)), 2500, 8000) * np.exp(-t(dd) / .004) + self.ring([140], [.04], [.8], dd)) * .5
        if ty == "tick":
            n = int(.03 * SR); return self.ring([3200], [.006], [.25], .03)[:n]
        if ty == "hiss":
            dd = d or .6; return self.bp(self.rng.standard_normal(int(dd * SR)), 4000, 11000) * np.minimum(1, t(dd) / .05) * np.minimum(1, (dd - t(dd)) / .08) * .06
        if ty == "thud":
            return self.ring([70, 115], [.14, .06], [.9, .3], .5) * .8
        return None

    # ── caption news: graphics hits
    def news(self, ty, d=None):
        t = self.tt
        if ty == "slam":
            dd = .18; return (self.bp(self.rng.standard_normal(int(dd * SR)), 2000, 7000) * np.exp(-t(dd) / .004) * .6 + self.ring([90, 160], [.06, .03], [.9, .3], dd)) * .5
        if ty == "rattle":
            dd = d or .45; x = np.zeros(int(dd * SR))
            for k in range(int(dd / .045)):
                i = int(k * .045 * SR); n = min(int(.012 * SR), len(x) - i); x[i:i + n] += self.bp(self.rng.standard_normal(n), 3000, 8000) * np.exp(-np.arange(n) / SR / .002) * .4
            return x
        if ty == "whoosh":
            return self.whoosh(d or .35, 1.2)
        if ty == "squeak":
            dd = .35; return self.sweep(1800, 2600, dd) * np.sin(np.pi * t(dd) / dd) ** 2 * .06
        if ty == "shutter":
            dd = .2; return (self.bp(self.rng.standard_normal(int(dd * SR)), 1500, 8000) * (np.exp(-t(dd) / .006) + np.exp(-np.maximum(0, t(dd) - .08) / .006) * (t(dd) > .08))) * .5
        if ty == "stamp":
            return (self.ring([60, 110], [.18, .08], [1, .4], .5) + self.bp(self.rng.standard_normal(int(.5 * SR)), 200, 3000) * np.exp(-t(.5) / .02) * .5) * .7
        if ty == "pop":
            return self.toon("pop")
        if ty == "riser":
            dd = d or 1.5; return (self.sweep(200, 1600, dd, curve=2) * .15 + self.bp(self.rng.standard_normal(int(dd * SR)), 800, 6000) * .12) * (t(dd) / dd) ** 2
        return None

    # ── telestrator: the analysis desk
    def tele(self, ty, d=None):
        t = self.tt
        if ty == "squeak":
            dd = d or .45; f = 3200 * (1 + .06 * np.sin(2 * np.pi * 23 * t(dd)))
            return (self.bp(self.rng.standard_normal(int(dd * SR)), 2000, 5000) * .5 + np.sin(2 * np.pi * np.cumsum(f) / SR) * .08) * np.sin(np.pi * t(dd) / dd) * .25
        if ty == "tape":
            dd = d or .8; return (self.sweep(900, 300, dd) * .2 + self.bp(self.rng.standard_normal(int(dd * SR)), 500, 3000) * .12) * np.minimum(1, t(dd) / .05)
        if ty == "stopwatch":
            dd = d or 1.0; x = np.zeros(int(dd * SR))
            for k in range(int(dd / .2) + 1):
                i = int(k * .2 * SR); seg_ = self.ring([4200], [.004], [.3], .02); x[i:i + len(seg_)] += seg_[:max(0, len(x) - i)]
            return x
        if ty == "hit":
            dd = .9; return (self.ring([233, 466, 349], [.25, .18, .2], [.5, .25, .3], dd) * (1 + .3 * np.sign(np.sin(2 * np.pi * 233 * t(dd)))) * .4
                             + self.ring([65], [.3], [.9], dd) * .6)
        if ty in ("shutter", "stamp", "whoosh", "pop", "tick"):
            return {"shutter": lambda: self.news("shutter"), "stamp": lambda: self.news("stamp"), "whoosh": lambda: self.whoosh(.34, 1.2),
                    "pop": lambda: self.toon("pop"), "tick": lambda: self.teardown("tick")}[ty]()
        return None

    # ── collage documentary: paper pieces landing, a pen, torn-paper cuts, a frame hung on the wall
    def collage(self, ty, d=None):
        t = self.tt
        if ty == "paper":       # a cut-out laid down: a short rustle and a soft tap
            dd = .32; x = self.bp(self.rng.standard_normal(int(dd * SR)), 1500, 9000) * np.exp(-t(dd) / .07) * .22
            x[:int(.06 * SR)] += self.bp(self.rng.standard_normal(int(.06 * SR)), 300, 2500) * np.exp(-t(.06) / .01) * .5
            return x
        if ty == "pen":         # a felt pen drawing a mark
            return self.marker(d or .45, 120, "stroke", None, 1.0) * .8
        if ty == "word":        # a big word lands: a dry low tick
            x = self.ring([110, 220], [.05, .03], [.45, .15], .25); n = int(.03 * SR)
            x[:n] += self.bp(self.rng.standard_normal(n), 800, 5000) * np.exp(-t(.03) / .005) * .25
            return x
        if ty == "tear":        # paper torn across
            dd = d or .45; n = self.rng.standard_normal(int(dd * SR))     # a soft, smooth rip (no crackle spikes)
            return self.bp(n, 700, 5000) * np.sin(np.pi * t(dd) / dd) ** 1.2 * .18
        if ty == "frame":       # a frame knocks the wall / a photo drops
            return self.ring([70, 140, 420], [.15, .08, .03], [.9, .35, .15], .5) * .7
        if ty == "swing":
            dd = .18; return self.bp(self.rng.standard_normal(int(dd * SR)), 2000, 9000) * np.sin(np.pi * t(dd) / dd) * .1
        if ty == "riser":
            dd = d or 1.5; return self.bp(self.rng.standard_normal(int(dd * SR)), 400, 6000) * (t(dd) / dd) ** 2.5 * .18
        if ty == "hit":
            dd = 1.6; return self.ring([49, 98, 196], [.6, .3, .15], [1, .4, .2], dd) * .6
        return None

    # ── premium: clean techy UI sounds
    def tech(self, ty, d=None):
        t = self.tt
        if ty == "tick":
            return self.ring([2600, 5200], [.012, .006], [.35, .12], .05)
        if ty == "type":
            dd = d or .5; x = np.zeros(int(dd * SR)); k = 0.0
            while k < dd - .03:
                i = int(k * SR); s_ = self.ring([3000 + self.rng.uniform(-400, 400)], [.004], [.12], .02); x[i:i + len(s_)] += s_[:len(x) - i]; k += self.rng.uniform(.045, .075)
            return x
        if ty == "slide":
            dd = d or .35; return (self.bp(self.rng.standard_normal(int(dd * SR)), 1500, 9000) * .18 + self.sweep(500, 1400, dd) * .05) * np.sin(np.pi * t(dd) / dd) ** 2
        if ty == "whip":
            dd = .28; x = self.bp(self.rng.standard_normal(int(dd * SR)), 800, 8000) * np.sin(np.pi * t(dd) / dd) ** 3 * .35
            g = (np.sign(np.sin(2 * np.pi * 37 * t(dd))) > 0).astype(float); return x * (.55 + .45 * g)
        if ty == "count":
            dd = d or .8; x = np.zeros(int(dd * SR))
            for k in range(int(dd / .05)):
                i = int(k * .05 * SR); s_ = self.ring([1800 + k * 40], [.006], [.18], .03); x[i:i + len(s_)] += s_[:len(x) - i]
            return x
        if ty == "pop":
            return self.sweep(500, 1300, .06) * np.exp(-t(.06) / .02) * .4
        if ty == "riser":
            dd = d or 1.2; return (self.sweep(180, 1800, dd, curve=2) * .12 + self.bp(self.rng.standard_normal(int(dd * SR)), 2000, 10000) * .08) * (t(dd) / dd) ** 2
        if ty == "hit":
            dd = 1.2; return (self.ring([55, 110, 220], [.35, .2, .12], [1, .4, .2], dd) + self.bp(self.rng.standard_normal(int(dd * SR)), 300, 6000) * np.exp(-t(dd) / .03) * .6) * .6
        return None


def foley(kind: str, events: list[dict], total: float) -> np.ndarray:
    """The style's foley as a stereo buffer (N, 2)."""
    N = int(total * SR); out = np.zeros((N, 2))
    if kind not in ("marker", "toon", "paper", "teardown", "news", "tele", "tech", "collage") or not events:
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
        elif kind in ("toon", "paper", "teardown", "news", "tele", "tech", "collage"):
            x = getattr(S, kind)(str(ty), num(e.get("d"), None))
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
