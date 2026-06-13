import os
import anthropic
import json

STYLE_PROMPTS = {
    "western_cartoon": "2D western cartoon illustration, bold thick black outlines, flat cel-shaded colors, limited color palette, clean vector-like art style, inspired by Archer FX animated series, no photorealism, no 3D, no blur",
    "anime":           "2D anime illustration, clean linework, vibrant colors, expressive eyes, detailed hair, cel-shaded, sharp edges, no photorealism",
    "pixar":           "3D Pixar-style illustration, soft rounded shapes, warm lighting, expressive cartoon faces, smooth textures, inspired by Pixar movies, high quality 3D render",
    "comic":           "Marvel/DC comic book style, bold black ink outlines, dynamic poses, halftone shading, vivid primary colors, dramatic lighting, speech bubble ready",
    "chibi":           "Cute chibi cartoon style, oversized head, tiny body, big expressive eyes, pastel colors, simple clean lines, kawaii aesthetic",
    "retro":           "Classic retro cartoon style, inspired by 1940s-1960s animation, limited color palette, simple geometric shapes, rubber hose animation style, Tom and Jerry aesthetic",
    "custom":          "High quality digital illustration, expressive character design, clean linework, professional animation style"
}

DURATION_SCENE_MAP = {
    1:  10,
    2:  18,
    3:  26,
    5:  40,
    10: 80,
}
 
THEME_CONTEXT = {
    "true_crime":  "true crime documentary, dark and investigative tone, real-world crime reconstruction",
    "history":     "historical documentary, epic and educational tone, factual historical events",
    "drama":       "emotional drama, intense human stories, psychological depth",
    "motivation":  "motivational and inspirational, uplifting tone, success and perseverance stories",
    "fairy_tale":  "fantasy fairy tale, magical and whimsical, enchanted worlds and characters",
    "mystery":     "mystery and thriller, suspenseful and atmospheric, secrets and revelations",
    "action":      "action and adventure, high-energy, intense sequences and conflict",
    "horror":      "horror and suspense, dark atmosphere, fear and dread",
}


def get_style_prompt(style: str) -> str:
    return STYLE_PROMPTS.get(style, STYLE_PROMPTS["western_cartoon"])


def get_scene_count(duration_minutes: int) -> int:
    # Find closest duration
    closest = min(DURATION_SCENE_MAP.keys(), key=lambda x: abs(x - duration_minutes))
    return DURATION_SCENE_MAP[closest]


async def generate_story_script(
    title: str,
    genre: str,
    style: str,
    theme: str,
    duration_minutes: int,
    narrator_voice_id: str = None,
    blur_faces: bool = False,
) -> list:
    """
    Generate a full story script for 2.5D/Storybook mode.
    Returns list of scene dicts with scene_number, title, scene_description, narrator_text, camera_angle, time_of_day.
    """
    scene_count = get_scene_count(duration_minutes)
    theme_context = THEME_CONTEXT.get(theme, "cinematic documentary")
    style_prompt = get_style_prompt(style)

    # Scene structure breakdown
    act1_end = max(3, scene_count // 5)
    act2_end = max(act1_end + 4, scene_count * 3 // 5)
    act3_end = max(act2_end + 3, scene_count * 4 // 5)
    act4_end = scene_count

    face_rule = (
        "All human faces must be blurred, obscured or hidden — use motion blur, silhouettes, backs of heads, or deep shadows. Never show a clear identifiable face."
        if blur_faces
        else "Characters may have visible faces, natural and realistic expressions"
    )

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=8000,
        messages=[{
            "role": "user",
            "content": f"""You are a world-class documentary scriptwriter and visual storyteller. You specialize in creating cinematic, gripping video scripts for YouTube that keep viewers watching until the very end.

STORY REQUEST:
- Title/Topic: {title}
- Genre: {genre}
- Theme: {theme_context}
- Visual Style: {style_prompt}
- Duration: {duration_minutes} minutes
- Total Scenes: {scene_count} (each scene = 8 seconds of video)

YOUR MISSION:
Create an extremely detailed, cinematic script with exactly {scene_count} scenes. This will be turned into a real video using AI image generation + Ken Burns camera movement. Every scene must be visually stunning and distinct.

CRITICAL RULES:
1. Narrator text: Maximum 28 words per scene (must fit in 7-8 seconds when spoken)
2. Scene descriptions: 60-80 words each, extremely detailed for AI image generation
3. Every scene MUST be visually different — different location, angle, lighting, time of day
4. {face_rule}
5. Photorealistic 3D rendered aesthetic, cinematic color grading, no cartoons
6. Build tension and narrative arc across all scenes
7. Vary camera angles: establish → close-up → wide → detail → medium
8. Lighting must be dramatic and cinematic throughout

SCENE STRUCTURE ({scene_count} total):
- Scenes 1-{act1_end}: HOOK & ESTABLISHMENT — grab viewer immediately, establish world and stakes
- Scenes {act1_end+1}-{act2_end}: RISING ACTION — develop story, introduce conflict, build tension
- Scenes {act2_end+1}-{act3_end}: CLIMAX — the main event, highest tension, shocking revelations
- Scenes {act3_end+1}-{act4_end}: RESOLUTION & AFTERMATH — consequences, reflection, powerful ending

IMAGE GENERATION STYLE (apply to all scene descriptions):
Photorealistic 3D rendered scene, {theme_context}, cinematic [angle] shot. [Location with extreme detail — architecture, materials, lighting sources, weather, time of day]. [Action/elements — what is happening, all faces blurred or obscured]. [Atmospheric details — fog, rain, dust, shadows]. Dramatic [color] lighting, [mood] atmosphere. Sharp focus on [key element]. No text, no watermarks. Vertical 9:16 format.

NARRATOR STYLE:
Deep, authoritative documentary voice. Short punchy sentences. Present tense for immediacy. Create suspense. End scenes on cliffhangers when possible. Think Netflix true crime meets National Geographic.

OUTPUT FORMAT — respond with a valid JSON array only, no other text:
[
  {{
    "scene_number": 1,
    "title": "Short Scene Title",
    "scene_description": "Full detailed image generation prompt 60-80 words",
    "narrator_text": "Maximum 28 words of dramatic narrator text",
    "camera_angle": "wide|medium|close-up|detail|establishing",
    "time_of_day": "dawn|morning|day|dusk|night|midnight"
  }}
]"""
        }]
    )

    text = message.content[0].text.strip()

    # Clean JSON if wrapped in markdown
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    text = text.strip()

    scenes = json.loads(text)
    return scenes


async def generate_scene_prompts(
    scene_text: str,
    characters: list,
    aspect_ratio: str,
    pre_dialogue_action: str = None,
    blur_faces: bool = False
) -> dict:
    """
    Returns:
    - character_prompts: {char_id: prompt}
    - scene_prompt: str
    - estimated_movement_duration: int (seconds)
    """

    ratio_map = {
        "16:9": "wide horizontal composition, 16:9 aspect ratio",
        "9:16": "vertical composition, 9:16 aspect ratio",
        "1:1":  "square composition, 1:1 aspect ratio"
    }
    ratio_text = ratio_map.get(aspect_ratio, ratio_map["16:9"])

    char_lines = []
    for c in characters:
        style_prompt = get_style_prompt(c.get("style", "western_cartoon"))
        role_label = "SPEAKING (mouth open, actively talking, gesturing)" if c["role"] == "speaking" else "SILENT (neutral pose, listening or standing)"
        framing = c.get("framing", "full_body")
        char_lines.append(
            f"- Character ID: {c['id']}\n"
            f"  Description: {c['description']}\n"
            f"  Style: {c.get('style', 'western_cartoon')}\n"
            f"  Role in scene: {role_label}\n"
            f"  Framing: {framing}\n"
            f"  Style prompt keywords: {style_prompt}"
        )
    chars_text = "\n".join(char_lines)

    action_text = f"\nPre-dialogue action: {pre_dialogue_action}" if pre_dialogue_action else ""

    face_rule = (
        "All human faces must be blurred, obscured or hidden — use motion blur, silhouettes, backs of heads, or deep shadows. Never show a clear identifiable face."
        if blur_faces
        else "Characters may have visible faces, natural and realistic expressions"
    )

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2000,
        messages=[{
            "role": "user",
            "content": f"""You are an expert prompt engineer for AI image and animation generation.

Scene description: {scene_text}{action_text}
Aspect ratio: {ratio_text}

Characters in this scene:
{chars_text}

Generate:

1. For each character, a CHARACTER_PROMPT for generating them alone on a clean white background.
   - Include their exact appearance, outfit, expression
   - Apply their specific style keywords
   - Speaking characters: open mouth ready to talk, expressive
   - Silent characters: neutral, natural pose

2. A SCENE_PROMPT for composing all characters together in the described scene.
   - The SCENE_PROMPT must preserve the user's requested story, action, mood and setting. Do not replace it with a generic scene.
   - Reference each character's exact appearance for consistency
   - Speaking characters: active, mouth open, gesturing
   - Silent characters: background/side positions, neutral
   - Include environment/background details
   - Apply the dominant style of the scene
   - Face rule: {face_rule}
   - No written text, captions, logos, signs, UI, watermark or subtitles inside the image
   - If the scene includes dialogue, keep the spoken words exactly as natural speech. Never spell ordinary words letter-by-letter.

3. MOVEMENT_DURATION: Estimate seconds needed for any pre-dialogue physical action (e.g. standing up, walking, slamming table). If no action, return 0.

Respond in EXACTLY this format (no extra text):
CHARACTER_PROMPT_[ID]: [prompt]
SCENE_PROMPT: [prompt]
MOVEMENT_DURATION: [number]"""
        }]
    )

    text = message.content[0].text.strip()
    lines = text.split("\n")

    character_prompts = {}
    scene_prompt = ""
    movement_duration = 0
    current_key = None

    for line in lines:
        if line.startswith("CHARACTER_PROMPT_"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                char_id = parts[0].replace("CHARACTER_PROMPT_", "").strip()
                character_prompts[char_id] = parts[1].strip()
                current_key = ("character", char_id)
        elif line.startswith("SCENE_PROMPT:"):
            scene_prompt = line.replace("SCENE_PROMPT:", "").strip()
            current_key = ("scene", None)
        elif line.startswith("MOVEMENT_DURATION:"):
            try:
                movement_duration = int(line.replace("MOVEMENT_DURATION:", "").strip())
            except:
                movement_duration = 0
            current_key = None
        elif line.strip() and current_key:
            if current_key[0] == "scene":
                scene_prompt = f"{scene_prompt} {line.strip()}".strip()
            elif current_key[0] == "character":
                cid = current_key[1]
                character_prompts[cid] = f"{character_prompts.get(cid, '')} {line.strip()}".strip()

    if not scene_prompt:
        style_hint = get_style_prompt(characters[0].get("style", "western_cartoon")) if characters else "high quality 2D animation style"
        scene_prompt = (
            f"{scene_text}. {ratio_text}. {style_hint}. "
            "Use the provided character references consistently. No written text, captions, logos, watermark or subtitles."
        )

    return {
        "character_prompts": character_prompts,
        "scene_prompt": scene_prompt,
        "movement_duration": movement_duration
    }
