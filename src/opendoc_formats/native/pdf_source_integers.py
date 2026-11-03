"""Bounded scalar observations at a container's declared xref contexts, not global object resolution."""

from __future__ import annotations

import hashlib
from typing import Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_syntax import Parser, Reference, SyntaxBudget
from opendoc_formats.native.pdf_xref_state import resolve_xrefs
from opendoc_formats.support.cancellation import checkpoint


class SourceIntegers:
    def __init__(self, data: bytes, sections: list[dict[str, Any]], part_limit: int, budget: SyntaxBudget) -> None:
        self.data, self.sections, self.part_limit, self.budget = data, sections, part_limit, budget
        self.items = 0
        self.bytes = 0
        self.indexes: dict[int, dict[int, dict[str, Any]]] = {}
        self.scalars: dict[tuple[int, int, int], dict[str, Any]] = {}
        self.parents: dict[int, set[int]] = {}
        for section in sections:
            checkpoint()
            if section['xref_stream'] is not None:
                self.parents.setdefault(section['xref_stream'], set()).add(section['offset'])
        by_offset = {section['offset']: section for section in sections}
        self.primary_contexts: set[int] = set()
        offset = sections[0]['offset'] if sections else None
        while offset is not None and offset not in self.primary_contexts:
            checkpoint()
            self.primary_contexts.add(offset)
            primary_section = by_offset.get(offset)
            offset = primary_section['prev'] if primary_section is not None else None

    def selection(self, context: int, *, item_limit: int, location: str,
                  explicit_primary: bool = False) -> tuple[int, dict[int, dict[str, Any]]]:
        checkpoint()
        parents = self.parents.get(context, set())
        if not explicit_primary and (len(parents) > 1 or (parents and context in self.primary_contexts)):
            raise UnsupportedDocumentError(location+'ambiguous hybrid primary for indirect integer')
        primary = context if explicit_primary else next(iter(parents)) if parents else context
        if primary not in self.indexes:
            selection = resolve_xrefs(self.sections, primary, item_limit-self.items, budget=self.budget)
            records = selection['effective_xref_entries']
            self.items += len(records)
            self.indexes[primary] = {record['object']: record for record in records}
        return primary, self.indexes[primary]

    def read(self, reference: Reference, contexts: set[int], *, item_limit: int,
             byte_limit: int, location: str, explicit_primary: bool = False) -> tuple[int, list[dict[str, Any]]]:
        observations = []
        for context in sorted(contexts):
            checkpoint()
            if self.items >= item_limit or self.bytes > byte_limit:
                raise ResourceLimitError(location+'max_items/max_total_bytes exceeded by scalar observations')
            # A hybrid supplement's Prev is not the primary chain. Ambiguity is explicit.
            primary, index = self.selection(context, item_limit=item_limit, location=location,
                                             explicit_primary=explicit_primary)
            entry = index.get(reference.object)
            if entry is None or entry['state'] in {'free', 'unknown-null'}:
                raise InvalidDocumentError(location+'indirect integer has no in-use xref record')
            if entry['generation'] != reference.generation:
                raise InvalidDocumentError(location+'indirect integer generation does not match selected xref record')
            if entry['state'] != 'uncompressed':
                raise UnsupportedDocumentError(location+'compressed indirect integer outside source scalar profile')
            offset = entry['offset']
            key = reference.object, reference.generation, offset
            if key not in self.scalars:
                if self.items >= item_limit:
                    raise ResourceLimitError(location+'max_items exceeded by indirect integer')
                if self.bytes >= byte_limit:
                    raise ResourceLimitError(location+'max_total_bytes exceeded by indirect integer')
                if not 0 <= offset < len(self.data):
                    raise InvalidDocumentError(location+'indirect integer offset outside source')
                remaining = byte_limit-self.bytes
                parser = Parser(self.data, offset, min(self.part_limit, remaining), self.budget,
                                window_quota='max_total_bytes' if remaining < self.part_limit else 'max_part_bytes')
                self.items += 1
                try:
                    first = parser.take('integer')
                    if (first.start != offset or first.value != reference.object
                            or parser.take('integer').value != reference.generation or parser.take().value != b'obj'):
                        raise InvalidDocumentError(location+'indirect integer header does not match xref record')
                    value = parser.value()
                    if type(value) is not int or value < 0:
                        raise UnsupportedDocumentError(location+'indirect integer body must be a nonnegative direct integer')
                    if parser.take().value != b'endobj':
                        raise InvalidDocumentError(location+'indirect integer body must end before endobj')
                    raw = memoryview(self.data)[offset:parser.pos]
                    self.scalars[key] = {'object': reference.object, 'generation': reference.generation,
                                         'offset': offset, 'end': parser.pos, 'value': value,
                                         'sha256': hashlib.sha256(raw).hexdigest(), 'ownership_proven': False}
                finally:
                    # Current-context diagnostics may retain a failed scalar
                    # attempt; its consumed bytes and token-delimiter witness
                    # still count as work even though the witness is outside
                    # the scalar's hashed object range.
                    self.bytes += parser.pos-offset+int(parser.pos < len(self.data))
            if self.items >= item_limit:
                raise ResourceLimitError(location+'max_items exceeded by scalar observation')
            self.items += 1
            observations.append({**self.scalars[key], 'context_xref': context, 'primary_xref': primary,
                                 'selected_xref': entry['xref_offset'], 'record_range': entry['record_range']})
        if not observations or len({row['value'] for row in observations}) != 1:
            raise UnsupportedDocumentError(location+'indirect integer differs across candidate xref contexts')
        return observations[0]['value'], observations
