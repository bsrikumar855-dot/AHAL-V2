from __future__ import annotations

import re
from html import unescape


_HTML_IMAGE_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"</?(?:p|div|a|br|picture|source|span|center)\b[^>]*>", re.IGNORECASE)
_ANY_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\([^)]+\)")
_MARKDOWN_LINK_IMAGE_RE = re.compile(r"\[[^\]]*(?:badge|logo|build|license|version)[^\]]*]\([^)]+\)", re.IGNORECASE)
_RAW_ATTR_RE = re.compile(r"\b(?:src|alt|width|height|align|href)\s*=\s*['\"][^'\"]*['\"]", re.IGNORECASE)
_DECORATIVE_TOKEN_RE = re.compile(
    r"(?:shields\.io|badge\.svg|github/actions/workflows|npm version|license badge|"
    r"public/branding|assets/logo|transparent\.png|logo-chatgpt-transparent|"
    r"\bbranding\b|\blogo\b|banner|\.png\b|\.svg\b)",
    re.IGNORECASE,
)


def sanitize_readme_for_identity(text: str) -> str:
    value = unescape(str(text or "")).replace("\r\n", "\n").replace("\r", "\n")
    value = _MARKDOWN_IMAGE_RE.sub("", value)
    value = _MARKDOWN_LINK_IMAGE_RE.sub("", value)
    value = _HTML_IMAGE_RE.sub("", value)
    value = _HTML_TAG_RE.sub("", value)
    value = _RAW_ATTR_RE.sub("", value)

    cleaned_lines: list[str] = []
    for raw_line in value.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            cleaned_lines.append("")
            continue
        if is_markup_noise_candidate(line):
            cleaned_lines.append("")
            continue
        line = _ANY_HTML_TAG_RE.sub("", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line and not is_markup_noise_candidate(line):
            cleaned_lines.append(line)

    compacted: list[str] = []
    previous_blank = False
    for line in cleaned_lines:
        if not line:
            if not previous_blank:
                compacted.append("")
            previous_blank = True
            continue
        compacted.append(line)
        previous_blank = False
    return "\n".join(compacted).strip()


def sanitize_text_for_display(text: str, fallback: str = "") -> str:
    value = sanitize_readme_for_identity(str(text or ""))
    value = _ANY_HTML_TAG_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value or is_markup_noise_candidate(value):
        return fallback
    return value


def is_markup_noise_candidate(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return True
    lowered = value.lower()
    if any(token in lowered for token in ("<", ">", "img src", "src=", "alt=", "width=", "height=", "align=", "href=")):
        return True
    if _DECORATIVE_TOKEN_RE.search(value):
        return True
    pathish = re.sub(r"[./\\_-]+", " ", lowered)
    words = re.findall(r"[a-z0-9]+", pathish)
    if words and len(words) <= 5 and any(token in lowered for token in ("logo", "branding", ".png", ".svg")):
        return True
    return False


def has_meaningful_identity_words(text: str, minimum: int = 8) -> bool:
    value = sanitize_text_for_display(text)
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]*", value)
    return len(words) >= minimum


def is_strong_identity_phrase(text: str) -> bool:
    value = sanitize_text_for_display(text).lower()
    if is_markup_noise_candidate(value):
        return False
    words = re.findall(r"[a-z][a-z0-9'-]*", value)
    if len(words) < 3:
        return False
    strong_terms = (
        "developer intelligence",
        "code intelligence",
        "repository intelligence",
        "claim verification",
        "fact checking",
        "diagnosis",
        "medical diagnosis",
        "research assistant",
        "whatsapp gateway",
        "study plan",
        "media player",
    )
    strong_nouns = ("backend", "frontend", "fullstack", "application", "app", "platform", "system", "service", "tool", "gateway", "assistant", "engine", "portal", "player")
    return any(term in value for term in strong_terms) or any(noun in words for noun in strong_nouns)
