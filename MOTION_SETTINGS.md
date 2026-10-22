# Motion Graphics — approved settings

These are the production defaults the team signed off on (2026-10-19) after the
"What is inflation?" sample. Change them only on purpose; most can be overridden with
Railway variables without a deploy.

## Flow
| Setting | Value | Where |
|---|---|---|
| Order | **Audio first**: plan → record narration → cut beats to the voice → animate to word timings | `motion_pipeline.run_motion_pipeline` |
| Opening | Explainers open with the question they answer; no permanent topic title | `motion_prompts.DIRECTOR_SYSTEM` |
| Narration | The spine of the video: 2–3 sentences per beat, every number/label on screen is spoken, visuals land on the word that names them (±150 ms) | `DIRECTOR_SYSTEM`, `ANIMATOR_SYSTEM` |
| Beat length | 0.12 s lead + recorded speech + 0.18 s tail (no silent holds) | `motion_sound.VO_LEAD / VO_TAIL` |

## Voice
| Setting | Value | Override |
|---|---|---|
| Narrator | Matilda (`XrExE9yKIg1WjnnlVkGX`) | `MOTION_DEFAULT_VOICE_ID`, or the voice picked in the UI |
| Pace | 1.0× (ElevenLabs native speed; 0.7–1.2 allowed) | request `narrator_speed` |
| Tone | `explainer`: stability 0.55, style 0.15 on `eleven_multilingual_v2` | `tts.TONE_SETTINGS`, `ELEVENLABS_EXPLAINER_MODEL` |
| Pauses inside a line | 0.24 s after `. ? ! : ;`, 0.14 s after commas (ElevenLabs leaves 0.4–0.75 s) | `motion_sound.PAUSE_SENTENCE / PAUSE_COMMA` |
| Word timings | ElevenLabs `/with-timestamps`, shifted after pause trimming | `tts.generate_speech_timed`, `motion_sound.tighten` |
| Concurrency | 2 ElevenLabs calls at a time, retry on 429/5xx | `ELEVENLABS_CONCURRENCY` |

## Sound
| Setting | Value |
|---|---|
| Effects | On by default; one per animation cue from the motion kit, thinned so the mix stays clean |
| Library | Generated once with ElevenLabs, cached in R2 `motion-sfx/v1/` (reused by every video) |
| Levels | Effects normalised to −16 dB mean, then per-kind gain; voice matched to −18 LUFS per line with a static gain |
| Ducking | Effects/music duck under the voice (sidechain) |
| Master | Measured, then ONE static gain to −16 LUFS (true peak ≤ −1.5 dBTP) — never dynamic loudnorm |
| Music | Off by default (`include_music`) |

## Quality and cost
| Setting | Value | Override |
|---|---|---|
| Models | Opus for director, animator, critic | `MOTION_MODEL`, `MOTION_*_MODEL` |
| Layout QA | Every version must pass HyperFrames layout QA (no overlaps, overflow, unknown icons) before it renders | `MOTION_DEFECT_FIXES` |
| Icons | Lucide only (`<i data-icon="…">`), never hand-drawn | — |
| Critic | Only when QA reports something suspicious | `MOTION_CRITIC_MODE` = `suspect` / `always` / `off` |
| Budget | $0.025 per second of output (≥ $0.20), re-derived from the narration-set length | `MOTION_BUDGET_PER_SECOND`, `MOTION_BUDGET_MIN` |

## Looks
| Look | What it is | Extra cost |
|---|---|---|
| `motion` (default) | Typography, Lucide icons, charts and shapes drawn in code | — |
| `cinematic3d` | One 3D-rendered still per beat (FAL Gemini Flash Image; first still = character reference for the rest), animated with `K.camera` on every shot, `K.dissolve`, `K.scan`, `K.blink`, `K.glitch`, sparse overlay labels; low `drone` bed under the mix | ≈ $0.039 per still (`MOTION_IMAGE_COST_USD`), ~8–10 stills per minute |

Cinematic effects in the library (generated once on first use): `tick`, `heartbeat`, `whoosh`, `scan`, `glitch`, `drone`.
