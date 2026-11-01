"""Survival Story: the HyperFrames page around a model-written film(SV, T, stage) function (render_service/survival)."""

import json

END_CARD = 3.5      # seconds after the last spoken word: the choice card


def compose(code: str, timing: dict, w: int, h: int, start: float = 0.0, duration: float | None = None,
            probe: bool = False, draw_h: int | None = None) -> str:
    """The page for one film: a w x h canvas (the overlay is drawn at that size in 1080x1920 coordinates, so captions
    and cards stay sharp) with the 3D drawn at draw_h tall (default: h) and scaled onto it.
    start/duration render one chunk of the video (the film still sees absolute time)."""
    dh = draw_h or h
    dw = round(dh * w / h / 2) * 2
    total = round(timing["voice_end"] + END_CARD, 3)
    dur = round(duration if duration is not None else total, 4)
    probe_js = ""
    if probe:
        times = [round(x * 0.5, 2) for x in range(int(total * 2) + 1)]
        probe_js = f"""
  for (const t of {json.dumps(times)}) {{
    try {{ c.setTransform({w} / 1080, 0, 0, {w} / 1080, 0, 0); F.seek(t, c); }} catch (e) {{ window.__kCues.push({{ t: 0, kind: 'error', msg: 'at ' + t.toFixed(1) + ' s: ' + String((e && e.message) || e).slice(0, 400) }}); break; }}
  }}"""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
@font-face{{font-family:Oswald;src:url(survival/fonts/Oswald-700.woff2) format('woff2');font-weight:700}}
@font-face{{font-family:"JetBrains Mono";src:url(survival/fonts/JetBrainsMono-700.woff2) format('woff2');font-weight:700}}
html,body{{margin:0;background:#000}}
#root{{width:{w}px;height:{h}px;position:relative;overflow:hidden;background:#000}}
#film{{position:absolute;inset:0;width:{w}px;height:{h}px}}
.fl{{position:absolute;left:-999px;font:700 20px Oswald}}.fm{{position:absolute;left:-999px;font:700 20px "JetBrains Mono"}}
</style></head><body>
<div id="root" data-composition-id="survival" data-no-timeline data-start="0" data-duration="{dur}" data-width="{w}" data-height="{h}">
<canvas id="film" width="{w}" height="{h}"></canvas><span class="fl">A</span><span class="fm">A</span></div>
<script src="lib/anime.umd.min.js"></script><script src="lib/kit.js"></script>
<script src="survival/stage.three.js"></script>
<script>window.TIMING = {json.dumps(timing)}; window.TOTAL = {total};</script>
<script>
{code}
</script>
<script>
(function () {{
  const tl = K.timeline(), OFFSET = {round(start, 4)};
  window.__kCues = window.__kCues || [];
  const canvas = document.getElementById('film'), c = canvas.getContext('2d');
  const stage = SV.createStage(canvas, {{ width: {dw}, height: {dh} }});
  let F = null;
  try {{
    if (typeof film !== 'function') throw new Error('film(SV, T, stage) is not defined');
    F = film(SV, window.TIMING, stage);
    if (!F || typeof F.seek !== 'function') throw new Error('film() must return {{ seek(t, c), sfx }}');
    window.__kCues.push({{ t: 0, kind: 'spec', spec: F.sfx || {{}} }});
    window.CHUNKS = window.CHUNKS || [];
  }} catch (e) {{ window.__kCues.push({{ t: 0, kind: 'error', msg: String((e && e.stack) || e).slice(0, 900) }}); F = null; }}
  {probe_js if probe else ""}
  const draw = t => {{ if (!F) return; c.setTransform({w} / 1080, 0, 0, {w} / 1080, 0, 0); c.globalAlpha = 1; F.seek(Math.min(t, window.TOTAL - 0.001), c); }};
  let last = -1;   // the timeline calls its hooks on render AND update: draw each time once
  tl._kHooks.push(ms => {{ if (ms === last) return; last = ms; draw(ms / 1000 + OFFSET); }});
  tl.add({{ k: 0 }}, {{ k: 1, duration: {round(dur * 1000)}, ease: 'linear' }}, 0);
  draw(OFFSET);
}})();
</script></body></html>"""
