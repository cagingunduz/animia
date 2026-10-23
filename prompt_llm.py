"""
Prompt and planning calls (scripts, scene plans, image/video prompts): Claude Sonnet 5.5 at medium effort.
Motion Graphics' animator — the call that writes the animation code — stays on Opus (motion_pipeline.py).

`create()` takes the same keyword arguments as `client.messages.create()` (any `model` is replaced) and
returns an object whose `.content[0].text` is the reply text, so existing callers keep their parsing.
Current models always think and thinking counts toward max_tokens, so headroom is added on top.
"""

import os
from types import SimpleNamespace

import anthropic

PROMPT_MODEL = os.environ.get("PROMPT_MODEL", "claude-sonnet-5-5")
PROMPT_EFFORT = os.environ.get("PROMPT_EFFORT", "medium")
THINK_ROOM = 8000

_client = None


def _anthropic():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    return _client


def create(max_tokens: int, messages: list, **kw):
    kw.pop("model", None)
    with _anthropic().messages.stream(
        model=PROMPT_MODEL, max_tokens=max_tokens + THINK_ROOM,
        output_config={"effort": PROMPT_EFFORT}, messages=messages, **kw,
    ) as stream:
        msg = stream.get_final_message()
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)],
                           stop_reason=msg.stop_reason, usage=msg.usage, model=msg.model)
