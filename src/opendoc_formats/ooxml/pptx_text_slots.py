"""Shared native text slots; breaks and field caches stay protected structural data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import opendoc_model as od

from opendoc_formats.support.cancellation import cancellable_items

A = '{http://schemas.openxmlformats.org/drawingml/2006/main}'


@dataclass
class TextSlot:
    node: Any = None
    literal: str | None = None
    line_break: bool = False


def paragraph_slots(paragraph: Any, *, breaks: bool = True, fields: bool = False) -> list[TextSlot] | None:
    slots = []
    for child in cancellable_items(paragraph):
        if child.tag in {A+'pPr', A+'endParaRPr'}:
            continue
        if child.tag == A+'br' and breaks:
            slots.append(TextSlot(literal='\n', line_break=True))
        elif child.tag == A+'fld' and fields:
            cached = ''.join(node.text or '' for node in cancellable_items(child.iter(A+'t')))
            if cached:
                slots.append(TextSlot(literal=cached))
        elif child.tag == A+'r' and len(child.findall(A+'t')) == 1:
            text = child.find(A+'t')
            if text.text or child.find(A+'rPr/'+A+'hlinkClick') is not None:
                slots.append(TextSlot(node=text))
        else:
            return None
    return slots


def matched_slots(slots: list[TextSlot], content: list[Any]) -> list[Any] | None:
    if len(slots) != len(content) or any(not isinstance(run, od.TextRun) for run in content):
        return None
    for slot, run in cancellable_items(zip(slots, content, strict=True)):
        if slot.literal is not None and (run.text != slot.literal or run.link):
            return None
        if slot.line_break and run.properties.get('pptx_break') != 'line':
            return None
    return [slot.node for slot in slots]
