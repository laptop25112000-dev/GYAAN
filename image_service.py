import os
import random
import re
import urllib.parse
from typing import List, Tuple

QUESTION_EXCLUSIONS = re.compile(
    r"^(?:how\s+to|what\s+is|why\s+do|where\s+is|when\s+did|explain\s+how|tutorial\s+on)\b",
    re.IGNORECASE
)

TRIGGER_PATTERNS = [
    r"\b(?:generate|create|make|draw|paint|render|sketch|produce)\s+(?:me\s+)?(?:an?\s+|the\s+)?(?:image|picture|photo|illustration|drawing|render|wallpaper)s?\b",
    r"\b(?:show\s+me|give\s+me)\s+(?:an?\s+|the\s+)?(?:image|picture|photo|illustration|drawing|wallpaper)s?\b",
    r"\b(?:an?\s+|the\s+)?(?:image|picture|photo|illustration|drawing|wallpaper)s?\s+(?:of|showing|depicting|with)\b",
    r"^(?:draw|paint|sketch|illustrate)\s+(?:me\s+)?(?:an?\s+|the\s+)?\b",
    r"^(?:image|picture|photo|illustration|drawing)\s*:\s*",
    r"^/image\b",
    r"\b(?:image|photo|picture|illustration|wallpaper)s?\s*$",
]

CLEANUP_PREFIX = re.compile(
    r"^(?:please\s+)?(?:can\s+you\s+)?(?:could\s+you\s+)?\b(?:generate|create|make|draw|paint|render|sketch|show\s+me|give\s+me)\b\s*(?:me\s+)?\s*(?:an?\s+|the\s+)?\b(?:image|picture|photo|illustration|drawing|wallpaper)?s?\b\s*(?:of|showing|depicting|with)?\s*",
    re.IGNORECASE
)

CLEANUP_STANDALONE_IMAGE = re.compile(
    r"^(?:an?\s+|the\s+)?\b(?:image|picture|photo|illustration|drawing|wallpaper)s?\b\s+(?:of|showing|depicting|with)\s*",
    re.IGNORECASE
)

CLEANUP_SUFFIX = re.compile(
    r"\s+\b(?:image|picture|photo|illustration|wallpaper)s?$",
    re.IGNORECASE
)

COUNT_RE = re.compile(r"\b([1-4])\s*(?:images?|pictures?|photos?|variants?)\b", re.IGNORECASE)


def detect_image_request(text: str, mode: str = "hybrid") -> Tuple[bool, str, int]:
    """
    Checks if the user prompt is requesting image generation.
    Returns: (is_image_req, cleaned_prompt, count)
    Default count is 1 image.
    """
    t = text.strip()
    if not t:
        return False, "", 0

    # If the user explicitly switched to Image mode
    if mode in ("image", "image_generation"):
        cleaned = t
        if cleaned.lower().startswith("/image"):
            cleaned = cleaned[6:].strip()
        cleaned = CLEANUP_PREFIX.sub("", cleaned).strip()
        cleaned = CLEANUP_STANDALONE_IMAGE.sub("", cleaned).strip()
        cleaned = CLEANUP_SUFFIX.sub("", cleaned).strip()
        return True, (cleaned or t), 1

    # Don't hijack informational questions
    if QUESTION_EXCLUSIONS.search(t):
        return False, t, 0

    matched = any(re.search(pat, t, re.IGNORECASE) for pat in TRIGGER_PATTERNS)
    if not matched:
        return False, t, 0

    count = 1
    cm = COUNT_RE.search(t)
    if cm:
        try:
            count = max(1, min(4, int(cm.group(1))))
        except Exception:
            count = 1

    cleaned = t
    if cleaned.lower().startswith("/image"):
        cleaned = cleaned[6:].strip()
    cleaned = COUNT_RE.sub("", cleaned).strip()
    cleaned = CLEANUP_PREFIX.sub("", cleaned).strip()
    cleaned = CLEANUP_STANDALONE_IMAGE.sub("", cleaned).strip()
    cleaned = CLEANUP_SUFFIX.sub("", cleaned).strip()

    return True, (cleaned or t), count


def generate_images(prompt: str, count: int = 1) -> List[str]:
    """
    Generates image URLs using Pollinations.ai Flux engine.
    Produces single or requested variants using randomized seeds.
    """
    encoded_prompt = urllib.parse.quote(prompt.strip())
    urls = []
    for _ in range(count):
        seed = random.randint(100000, 9999999)
        # Using free Pollinations Flux model
        url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?seed={seed}&width=1024&height=1024&model=flux&nologo=true"
        )
        urls.append(url)
    return urls
