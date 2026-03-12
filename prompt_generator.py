import os
import anthropic

STYLE_PROMPTS = {
    "western_cartoon": "2D western cartoon illustration, bold thick black outlines, flat cel-shaded colors, limited color palette, clean vector-like art style, inspired by Archer FX animated series, no photorealism, no 3D, no blur",
    "anime":           "2D anime illustration, clean linework, vibrant colors, expressive eyes, detailed hair, inspired by modern anime series like Attack on Titan and Demon Slayer, cel-shaded, sharp edges, no photorealism",
    "pixar":           "3D Pixar-style illustration, soft rounded shapes, warm lighting, expressive cartoon faces, smooth textures, inspired by Pixar movies, high quality 3D render",
    "comic":           "Marvel/DC comic book style, bold black ink outlines, dynamic poses, halftone shading, vivid primary colors, dramatic lighting, speech bubble ready",
    "chibi":           "Cute chibi cartoon style, oversized head, tiny body, big expressive eyes, pastel colors, simple clean lines, kawaii aesthetic",
    "retro":           "Classic retro cartoon style, inspired by 1940s-1960s animation, limited color palette, simple geometric shapes, rubber hose animation style, Tom and Jerry aesthetic",
    "custom":          "High quality digital illustration, expressive character design, clean linework, professional animation style"
}


def get_style_prompt(style: str) -> str:
    return STYLE_PROMPTS.get(style, STYLE_PROMPTS["western_cartoon"])


async def generate_scene_prompts(
    scene_text: str,
    characters: list,           # List of {id, description, style, role, framing}
    aspect_ratio: str,
    pre_dialogue_action: str = None
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

    # Build character descriptions for Claude
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
   - Reference each character's exact appearance for consistency
   - Speaking characters: active, mouth open, gesturing
   - Silent characters: background/side positions, neutral
   - Include environment/background details
   - Apply the dominant style of the scene

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

    for line in lines:
        if line.startswith("CHARACTER_PROMPT_"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                char_id = parts[0].replace("CHARACTER_PROMPT_", "").strip()
                character_prompts[char_id] = parts[1].strip()
        elif line.startswith("SCENE_PROMPT:"):
            scene_prompt = line.replace("SCENE_PROMPT:", "").strip()
        elif line.startswith("MOVEMENT_DURATION:"):
            try:
                movement_duration = int(line.replace("MOVEMENT_DURATION:", "").strip())
            except:
                movement_duration = 0

    return {
        "character_prompts": character_prompts,
        "scene_prompt": scene_prompt,
        "movement_duration": movement_duration
    }
