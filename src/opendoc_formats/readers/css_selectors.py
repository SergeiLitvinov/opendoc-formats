"""Shared bounded selectors for static HTML and EPUB CSS."""

import re
from collections.abc import Callable
from typing import Any

from opendoc_formats.support.cancellation import check_cancelled

_ATTRIBUTE_SOURCE = r"""\[([A-Za-z_][A-Za-z0-9_-]*)(?:=([A-Za-z_][A-Za-z0-9_-]*|"[A-Za-z0-9_-]*"|'[A-Za-z0-9_-]*'))?\]"""
_ATTRIBUTE = re.compile(_ATTRIBUTE_SOURCE)
_CHILD_PSEUDO_SOURCE = r':(?ai:first-child|last-child|only-child)'
_CHILD_PSEUDO = re.compile(_CHILD_PSEUDO_SOURCE)
SELECTOR = re.compile(rf"(?:[a-zA-Z][\w-]*|\*)?(?:[.#][\w-]+|{_ATTRIBUTE_SOURCE}|{_CHILD_PSEUDO_SOURCE})*")
_SIMPLE_NAME = r'(?:-?[^\W\d]|--)[\w-]*'
SIMPLE_SELECTOR = re.compile(
    rf'(?:[a-zA-Z][\w-]*|\*)?(?:[.#]{_SIMPLE_NAME}|{_ATTRIBUTE_SOURCE}|{_CHILD_PSEUDO_SOURCE})*'
)
_COMBINATOR = re.compile(r'([ \t\r\n\f]*[>+~][ \t\r\n\f]*|[ \t\r\n\f]+)')

Selector = tuple[tuple[str, ...], tuple[str, ...]]
Specificity = tuple[int, int, int]


def parse_selector(selector: str, *, compound: re.Pattern[str] = SIMPLE_SELECTOR) -> tuple[Selector, Specificity] | None:
    parts = _COMBINATOR.split(selector)
    compounds = tuple(parts[::2])
    if len(compounds) > 32 or any(not part or not compound.fullmatch(part) for part in compounds):
        return None
    attributes = list(_ATTRIBUTE.finditer(selector))
    if any(attr[2] is not None and not attr[1].lower().startswith('data-') for attr in attributes):
        return None
    relations = tuple(relation.strip() for relation in parts[1::2])
    specificity = (selector.count('#'), selector.count('.')+selector.count(':')+len(attributes),
                   sum(part[0].isalpha() for part in compounds))
    return (compounds, relations), specificity


def matches_selector(node: Any, selector: Selector, cancelled: Callable[[], bool] | None) -> bool:
    compounds, relations = selector
    if not _matches_compound(cancelled, node, compounds[-1]):
        return False
    if not relations:
        return True
    candidates = [node]
    for part, relation in zip(reversed(compounds[:-1]), reversed(relations), strict=True):
        matches = []
        seen = set()
        sibling = relation in {'+', '~'}
        direct = relation in {'+', '>'}
        for candidate in candidates:
            relatives = candidate.previous_siblings if sibling else candidate.parents
            for relative in relatives:
                check_cancelled(cancelled, 'HTML CSS selector relation')
                if id(relative) in seen:
                    break
                seen.add(id(relative))
                if getattr(relative, "name", None) in {None, "[document]"}:
                    continue
                if _matches_compound(cancelled, relative, part):
                    matches.append(relative)
                if direct:
                    break
        if not matches:
            return False
        candidates = matches
    return True

def _matches_compound(cancelled: Callable[[], bool] | None, node: Any, selector: str) -> bool:
    tag = re.match(r"^[\w-]+|^\*", selector)
    if tag and tag[0] != "*" and tag[0].lower() != node.name:
        return False
    for attribute in _ATTRIBUTE.finditer(selector):
        name = attribute[1].lower()
        value = attribute[2]
        if not node.has_attr(name) or (value is not None and node.get(name) != value.strip("\"'")):
            return False
    pseudos = {item.lower() for item in _CHILD_PSEUDO.findall(selector)}
    if pseudos and node.name == '[document]':
        return False
    if pseudos & {':first-child', ':only-child'} and _has_element(cancelled, node.previous_siblings):
        return False
    if pseudos & {':last-child', ':only-child'} and _has_element(cancelled, node.next_siblings):
        return False
    return all(
        node.get("id") == name if marker == "#" else name in node.get("class", [])
        for marker, name in re.findall(r"([.#])([\w-]+)", selector)
    )


def _has_element(cancelled: Callable[[], bool] | None, siblings: Any) -> bool:
    for sibling in siblings:
        check_cancelled(cancelled, 'HTML CSS structural pseudo-class')
        if getattr(sibling, 'name', None) is not None:
            return True
    return False
