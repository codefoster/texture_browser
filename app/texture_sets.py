from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from PySide6.QtGui import QImageReader

from app.models import MediaItem


ROLE_ALIASES = {
    "basecolor": {
        "albedo",
        "base",
        "basecolor",
        "basecolour",
        "col",
        "color",
        "colour",
        "diff",
        "diffuse",
    },
    "normal": {"n", "nor", "norm", "normal", "nrm"},
    "roughness": {"rgh", "rough", "roughness"},
    "metallic": {"met", "metal", "metallic", "metalness", "mtl"},
    "ao": {"ambient", "ambientocclusion", "ao", "occ", "occl", "occlusion"},
    "height": {"bump", "disp", "displacement", "height"},
    "gloss": {"gloss", "glossiness"},
    "specular": {"refl", "reflect", "reflection", "reflectivity", "spec", "specular"},
    "emissive": {"emission", "emissive", "emit"},
    "opacity": {"alpha", "opacity", "trans", "transparency"},
    "packed": {"arm", "mra", "mro", "orm", "packed", "rma"},
    "mask": {"cavity", "curvature", "mask"},
}

ROLE_SORT_ORDER = [
    "basecolor",
    "normal",
    "roughness",
    "metallic",
    "ao",
    "packed",
    "height",
    "gloss",
    "specular",
    "emissive",
    "opacity",
    "mask",
]

NOISE_TERMS = {
    "1k",
    "2k",
    "4k",
    "8k",
    "16k",
    "directx",
    "dx",
    "gl",
    "map",
    "mat",
    "material",
    "opengl",
    "preview",
    "surface",
    "t",
    "tex",
    "texture",
    "tx",
    "unity",
    "unreal",
}


@dataclass(slots=True)
class TextureSet:
    seed: MediaItem
    items: list[MediaItem]
    identity_tokens: tuple[str, ...]
    roles: dict[str, list[MediaItem]]

    @property
    def title(self) -> str:
        if self.identity_tokens:
            return " ".join(self.identity_tokens)
        return self.seed.preview_path.stem


@dataclass(slots=True)
class TextureValidationIssue:
    severity: str
    message: str


def texture_set_for_item(seed: MediaItem, candidates: list[MediaItem]) -> TextureSet:
    if seed.is_video or seed.is_model:
        return TextureSet(seed, [seed], tuple(identity_tokens(seed)), {})

    folder_candidates = [
        candidate
        for candidate in candidates
        if not candidate.is_video and not candidate.is_model and candidate.folder == seed.folder
    ]
    seed_identity = _best_shared_identity(seed, folder_candidates)
    if not seed_identity:
        seed_identity = identity_tokens(seed)

    matches: dict[tuple[Path, str], MediaItem] = {}
    for candidate in folder_candidates:
        if texture_identity_matches(seed_identity, candidate):
            matches[(candidate.preview_path, candidate.display_name)] = candidate

    matches[(seed.preview_path, seed.display_name)] = seed
    items = sorted(
        matches.values(),
        key=lambda item: (role_sort_index(detect_role(item)), item.display_name.lower()),
    )
    return TextureSet(seed, items, tuple(seed_identity), roles_for_items(items))


def _best_shared_identity(seed: MediaItem, candidates: list[MediaItem]) -> list[str]:
    best_tokens: list[str] = []
    best_score = 0
    for candidate in candidates:
        if candidate.preview_path == seed.preview_path and candidate.display_name == seed.display_name:
            continue
        shared_tokens = _shared_identity_tokens(seed, candidate)
        if not shared_tokens:
            continue
        role_bonus = 4 if detect_role(candidate) is not None else 0
        score = sum(_identity_token_weight(token) for token in shared_tokens) + role_bonus
        if score > best_score:
            best_score = score
            best_tokens = shared_tokens
    return best_tokens


def _shared_identity_tokens(left: MediaItem, right: MediaItem) -> list[str]:
    left_tokens = identity_tokens(left)
    right_tokens = identity_tokens(right)
    shared: list[str] = []
    for left_token in left_tokens:
        if any(_identity_token_matches(left_token, right_token) for right_token in right_tokens):
            shared.append(left_token)
    return shared


def _identity_token_weight(token: str) -> int:
    if token.isdigit():
        return 8
    if token in {"frame", "sheet", "sheets", "panel", "wall", "floor"}:
        return 5
    return max(6, min(18, len(token) * 2))


def roles_for_items(items: list[MediaItem]) -> dict[str, list[MediaItem]]:
    roles: dict[str, list[MediaItem]] = {}
    for item in items:
        role = detect_role(item)
        if role is None:
            continue
        roles.setdefault(role, []).append(item)
    return roles


def validate_texture_set(texture_set: TextureSet) -> list[TextureValidationIssue]:
    issues: list[TextureValidationIssue] = []
    roles = texture_set.roles

    if len(texture_set.items) <= 1:
        issues.append(TextureValidationIssue("Warning", "Only one texture was found for this material set."))

    for role, items in sorted(roles.items()):
        if len(items) > 1 and role not in {"mask"}:
            names = ", ".join(item.display_name for item in items[:4])
            extra = "" if len(items) <= 4 else f" and {len(items) - 4} more"
            issues.append(TextureValidationIssue("Warning", f"Duplicate {role} maps: {names}{extra}."))

    if "basecolor" not in roles:
        issues.append(TextureValidationIssue("Warning", "No basecolor/albedo/diffuse map was detected."))
    if "normal" not in roles:
        issues.append(TextureValidationIssue("Warning", "No normal map was detected."))
    if "roughness" not in roles and "packed" not in roles and "gloss" not in roles:
        issues.append(TextureValidationIssue("Warning", "No roughness, glossiness, or packed MRO/ORM map was detected."))

    dimensions_by_value: dict[tuple[int, int], list[str]] = {}
    unreadable: list[str] = []
    for item in texture_set.items:
        dimensions = image_dimensions(item)
        if dimensions is None:
            unreadable.append(item.display_name)
            continue
        dimensions_by_value.setdefault(dimensions, []).append(item.display_name)
        if not _is_power_of_two(dimensions[0]) or not _is_power_of_two(dimensions[1]):
            issues.append(
                TextureValidationIssue(
                    "Info",
                    f"{item.display_name} is {dimensions[0]} x {dimensions[1]} px, not power-of-two.",
                )
            )

    if unreadable:
        names = ", ".join(unreadable[:4])
        extra = "" if len(unreadable) <= 4 else f" and {len(unreadable) - 4} more"
        issues.append(TextureValidationIssue("Warning", f"Could not read dimensions for {names}{extra}."))

    if len(dimensions_by_value) > 1:
        labels = [
            f"{width} x {height}: {len(names)} file(s)"
            for (width, height), names in sorted(dimensions_by_value.items())
        ]
        issues.append(TextureValidationIssue("Warning", "Mixed resolutions: " + "; ".join(labels) + "."))

    extensions = sorted({item.extension.lower() for item in texture_set.items if item.extension})
    if len(extensions) > 1:
        issues.append(TextureValidationIssue("Info", "Mixed file extensions: " + ", ".join(extensions) + "."))

    if not issues:
        issues.append(TextureValidationIssue("OK", "No obvious texture-set issues were found."))
    return issues


def detect_role(item: MediaItem) -> str | None:
    tokens = name_tokens(item.preview_path.stem)
    normalized_tokens = [_normalize_token(token) for token in tokens]
    joined_tokens = "".join(normalized_tokens)

    for role, aliases in ROLE_ALIASES.items():
        for alias in aliases:
            normalized_alias = _normalize_token(alias)
            if normalized_alias in normalized_tokens:
                return role
            if len(normalized_alias) >= 4 and normalized_alias in joined_tokens:
                return role
    return None


def identity_tokens(item: MediaItem) -> list[str]:
    role_terms = {term for aliases in ROLE_ALIASES.values() for term in aliases}
    raw_tokens = name_tokens(item.preview_path.stem)
    tokens: list[str] = []
    skip_next = False
    for index, token in enumerate(raw_tokens):
        if skip_next:
            skip_next = False
            continue
        if token.isdigit() and index + 1 < len(raw_tokens) and raw_tokens[index + 1] == "k":
            skip_next = True
            continue
        normalized = _normalize_token(token)
        if normalized in role_terms or normalized in NOISE_TERMS:
            continue
        tokens.append(normalized)
    return _unique_terms(tokens)


def name_tokens(stem: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", stem)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return _unique_terms(re.findall(r"[a-z0-9]+", spaced.lower()))


def texture_identity_matches(seed_identity: list[str], candidate: MediaItem) -> bool:
    if not seed_identity:
        return candidate.preview_path == candidate.path

    candidate_identity = identity_tokens(candidate)
    if not candidate_identity:
        return False

    for seed_token in seed_identity:
        if not any(_identity_token_matches(seed_token, candidate_token) for candidate_token in candidate_identity):
            return False
    return True


def role_sort_index(role: str | None) -> int:
    if role is None:
        return len(ROLE_SORT_ORDER) + 1
    try:
        return ROLE_SORT_ORDER.index(role)
    except ValueError:
        return len(ROLE_SORT_ORDER)


def image_dimensions(item: MediaItem) -> tuple[int, int] | None:
    cached = item.metadata.get("dimensions")
    if isinstance(cached, str) and "x" in cached:
        try:
            width_text, height_text = cached.split("x", 1)
            return (int(width_text), int(height_text))
        except ValueError:
            pass

    reader = QImageReader(str(item.preview_path))
    size = reader.size()
    if not size.isValid():
        return None
    dimensions = (size.width(), size.height())
    item.metadata["dimensions"] = f"{dimensions[0]}x{dimensions[1]}"
    return dimensions


def _identity_token_matches(left: str, right: str) -> bool:
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    return len(shorter) >= 6 and longer.startswith(shorter)


def _normalize_token(token: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", token.lower())
    stripped = re.sub(r"\d+$", "", normalized)
    return stripped or normalized


def _unique_terms(terms) -> list[str]:
    unique = []
    seen = set()
    for term in terms:
        if not term or term in seen:
            continue
        seen.add(term)
        unique.append(term)
    return unique


def _is_power_of_two(value: int) -> bool:
    return value > 0 and value & (value - 1) == 0
