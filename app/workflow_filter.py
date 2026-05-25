from __future__ import annotations

import re

from app.models import MediaItem


def workflow_filter_predicate(workflow_text: str):
    groups = workflow_token_groups(workflow_text)
    if not groups:
        return None

    def predicate(item: MediaItem) -> bool:
        return item_matches_workflow(item, groups)

    return predicate


def workflow_token_groups(workflow_text: str) -> list[list[str]]:
    groups: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for term in workflow_text.split(","):
        tokens = tuple(_name_tokens(term))
        if not tokens or tokens in seen:
            continue
        seen.add(tokens)
        groups.append(list(tokens))
    return groups


def item_matches_workflow(item: MediaItem, groups: list[list[str]]) -> bool:
    filename = item.preview_path.stem
    tokens = _name_tokens(filename)
    compact_name = _compact(filename)
    for group in groups:
        if _find_token_span(tokens, group)[0] >= 0:
            return True
        compact_group = "".join(_compact(token) for token in group)
        if compact_group and compact_group in compact_name:
            return True
    return False


def _name_tokens(text: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    spaced = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", spaced)
    return _unique_terms(re.findall(r"[a-z0-9]+", spaced.lower()))


def _find_token_span(tokens: list[str], pattern: list[str]) -> tuple[int, int]:
    if not tokens or not pattern:
        return (-1, 0)

    joined_pattern = "".join(_compact(token) for token in pattern)
    max_span = min(len(pattern), len(tokens))
    for start_index in range(len(tokens)):
        for span_length in range(max_span, 0, -1):
            end_index = start_index + span_length
            if end_index > len(tokens):
                continue
            joined_tokens = "".join(_compact(token) for token in tokens[start_index:end_index])
            if joined_tokens == joined_pattern:
                return (start_index, span_length)
    return (-1, 0)


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _unique_terms(terms) -> list[str]:
    unique = []
    seen = set()
    for term in terms:
        if not term or term in seen:
            continue
        seen.add(term)
        unique.append(term)
    return unique
