"""Finite GSUB ligature evidence for generated ToUnicode maps; never a shaping engine."""

from __future__ import annotations

import struct

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.fonts.sfnt_cmap import read_unicode_mapping
from opendoc_formats.native.sfnt import inspect_sfnt, read_face_metrics
from opendoc_formats.support.cancellation import cancellation_requested, checkpoint


def read_ligature_mapping(data: bytes) -> dict[int, str]:
    """Match the existing unambiguous policy for static post-1/2/3/4 standalone TrueType."""
    inventory = inspect_sfnt(data, cancelled=cancellation_requested)
    tables = {table.tag: table for table in inventory.tables}
    if 'GSUB' not in tables:
        return {}
    if inventory.sfnt_version != '00010000' or any(tag in tables for tag in ('CFF ', 'CFF2')):
        raise UnsupportedDocumentError('sfnt:GSUB: native glyph identity requires standalone TrueType')
    read_face_metrics(data, cancelled=cancellation_requested)  # Excludes variations and unknown face profiles.
    if struct.unpack_from('>I', data, tables['post'].offset)[0] not in (0x10000, 0x20000, 0x30000, 0x40000):
        raise UnsupportedDocumentError('sfnt:GSUB: native glyph identity requires post version 1/2/3/4')
    glyphs = struct.unpack_from('>H', data, tables['maxp'].offset+4)[0]
    table = tables['GSUB']
    if table.length > 8*1024*1024:
        raise ResourceLimitError('sfnt:GSUB: native table-byte budget exceeded')
    encoded: dict[int, set[str]] = {}
    for code, glyph in read_unicode_mapping(data).items():
        checkpoint()
        if glyph >= glyphs:
            raise UnsupportedDocumentError('sfnt:GSUB: cmap glyph outside declared maxp')
        if 0 <= code <= 0x10ffff and not 0xd800 <= code <= 0xdfff:
            encoded.setdefault(glyph, set()).add(chr(code))
    return _Gsub(memoryview(data)[table.offset:table.offset+table.length], glyphs, encoded).read()


class _Gsub:
    def __init__(self, data: memoryview, glyphs: int, encoded: dict[int, set[str]]) -> None:
        self.data, self.glyphs, self.encoded = data, glyphs, encoded
        self.work = self.ligatures = 0
        self.candidates: dict[int, set[str]] = {}
        self.uncertain: set[int] = set()

    def need(self, position: int, size: int) -> None:
        if position < 0 or position+size > len(self.data):
            raise InvalidDocumentError('sfnt:GSUB: range outside table')

    def spend(self, count: int = 1) -> None:
        checkpoint()
        self.work += count
        if self.work > 262144:
            raise ResourceLimitError('sfnt:GSUB: native word/coverage work budget exceeded')

    def word(self, position: int) -> int:
        self.spend()
        self.need(position, 2)
        return int(struct.unpack_from('>H', self.data, position)[0])

    def pointer(self, base: int, offset: int, minimum: int) -> int:
        if offset < minimum:
            raise InvalidDocumentError('sfnt:GSUB: offset points into parent header')
        self.need(base+offset, 2)
        return base+offset

    def glyph(self, position: int) -> int:
        glyph = self.word(position)
        if glyph >= self.glyphs:
            raise InvalidDocumentError('sfnt:GSUB: glyph outside declared maxp')
        return glyph

    def records(self, base: int) -> list[int]:
        count = self.word(base)
        self.need(base+2, 6*count)
        result, tags = [], set()
        for index in range(count):
            position = base+2+6*index
            tag = bytes(self.data[position:position+4])
            if tag in tags or any(byte < 32 or byte > 126 for byte in tag):
                raise UnsupportedDocumentError('sfnt:GSUB: ambiguous/nonprintable record tag')
            tags.add(tag)
            result.append(self.pointer(base, self.word(position+4), 2+6*count))
        return result

    def langsys(self, base: int, features: int) -> None:
        if self.word(base):
            raise UnsupportedDocumentError('sfnt:GSUB: nonzero LangSys lookup order')
        required, count = self.word(base+2), self.word(base+4)
        if required != 0xffff and required >= features:
            raise InvalidDocumentError('sfnt:GSUB: required feature outside FeatureList')
        self.need(base+6, 2*count)
        for index in range(count):
            if self.word(base+6+2*index) >= features:
                raise InvalidDocumentError('sfnt:GSUB: language feature outside FeatureList')

    def metadata(self, scripts: int, features: int, lookups: int) -> None:
        for feature in self.records(features):
            if self.word(feature):
                raise UnsupportedDocumentError('sfnt:GSUB: feature parameters outside native profile')
            count = self.word(feature+2)
            self.need(feature+4, 2*count)
            for index in range(count):
                if self.word(feature+4+2*index) >= lookups:
                    raise InvalidDocumentError('sfnt:GSUB: feature lookup outside LookupList')
        feature_count = self.word(features)
        for script in self.records(scripts):
            default, count = self.word(script), self.word(script+2)
            self.need(script+4, 6*count)
            if default:
                self.langsys(self.pointer(script, default, 4+6*count), feature_count)
            tags = set()
            for index in range(count):
                position = script+4+6*index
                tag = bytes(self.data[position:position+4])
                if tag in tags or any(byte < 32 or byte > 126 for byte in tag):
                    raise UnsupportedDocumentError('sfnt:GSUB: ambiguous language record tag')
                tags.add(tag)
                self.langsys(self.pointer(script, self.word(position+4), 4+6*count), feature_count)

    def coverage(self, base: int, expected: int | None) -> list[int]:
        kind, count = self.word(base), self.word(base+2)
        maximum = self.glyphs if expected is None else expected
        result: list[int] = []
        if kind == 1:
            if (expected is not None and count != expected) or count > maximum:
                raise InvalidDocumentError('sfnt:GSUB: coverage and ligature-set counts differ')
            self.need(base+4, 2*count)
            result = [self.glyph(base+4+2*index) for index in range(count)]
        elif kind == 2:
            self.need(base+4, 6*count)
            for index in range(count):
                start, end = self.glyph(base+4+6*index), self.glyph(base+6+6*index)
                if start > end or self.word(base+8+6*index) != len(result) or len(result)+end-start+1 > maximum:
                    raise InvalidDocumentError('sfnt:GSUB: invalid coverage range/index')
                for glyph in range(start, end+1):
                    self.spend()
                    result.append(glyph)
        else:
            raise UnsupportedDocumentError('sfnt:GSUB: coverage format outside native profile')
        if (expected is not None and len(result) != expected) or any(a >= b for a, b in zip(result, result[1:])):
            raise InvalidDocumentError('sfnt:GSUB: unordered or incomplete coverage')
        return result

    def single_table(self, base: int) -> None:
        """Validate adjacent single substitutions; never infer Unicode or run shaping."""
        kind, offset, value = self.word(base), self.word(base+2), self.word(base+4)
        if kind == 1:
            covered = self.coverage(self.pointer(base, offset, 6), None)
            for glyph in covered:
                self.spend()
                if (glyph+value) % 65536 >= self.glyphs:
                    raise InvalidDocumentError('sfnt:GSUB: single substitution outside declared maxp')
        elif kind == 2:
            self.need(base+6, 2*value)
            self.coverage(self.pointer(base, offset, 6+2*value), value)
            for index in range(value):
                self.glyph(base+6+2*index)
        else:
            raise UnsupportedDocumentError('sfnt:GSUB: single substitution format outside native profile')

    def sequence_table(self, base: int, kind: int) -> None:
        """Validate adjacent Multiple/AlternateSubst; leave shaping and Unicode policy alone."""
        if self.word(base) != 1:
            raise UnsupportedDocumentError('sfnt:GSUB: sequence substitution format outside native profile')
        count = self.word(base+4)
        self.need(base+6, 2*count)
        self.coverage(self.pointer(base, self.word(base+2), 6+2*count), count)
        for index in range(count):
            sequence = self.pointer(base, self.word(base+6+2*index), 6+2*count)
            size = self.word(sequence)
            if kind == 2 and not size:
                raise UnsupportedDocumentError('sfnt:GSUB: deletion outside native multiple substitution profile')
            self.need(sequence+2, 2*size)
            for number in range(size):
                self.glyph(sequence+2+2*number)

    def context_table(self, base: int, kind: int, lookups: int) -> None:
        """Validate coverage contexts and references; never execute nested lookups."""
        if self.word(base) == 1:
            self.context_rules(base, kind, lookups)
            return
        if self.word(base) == 2:
            self.context_classes(base, kind, lookups)
            return
        if self.word(base) != 3:
            raise UnsupportedDocumentError('sfnt:GSUB: context substitution requires native format 1/2/3')
        offsets: list[int] = []
        if kind == 5:
            inputs, actions = self.word(base+2), self.word(base+4)
            position = base+6
            self.need(position, 2*inputs)
            offsets.extend(self.word(position+2*index) for index in range(inputs))
            position += 2*inputs
        else:
            position, inputs = base+2, 0
            for group in range(3):  # Backtrack, input and lookahead.
                count = self.word(position)
                position += 2
                self.need(position, 2*count)
                offsets.extend(self.word(position+2*index) for index in range(count))
                position += 2*count
                if group == 1:
                    inputs = count
            actions = self.word(position)
            position += 2
        if not inputs:
            raise UnsupportedDocumentError('sfnt:GSUB: empty input context outside native profile')
        self.need(position, 4*actions)
        minimum = position+4*actions-base
        for offset in offsets:
            self.coverage(self.pointer(base, offset, minimum), None)
        self.context_actions(position, actions, inputs, lookups)

    def context_actions(self, position: int, actions: int, inputs: int, lookups: int) -> None:
        self.need(position, 4*actions)
        for index in range(actions):
            sequence, lookup = self.word(position+4*index), self.word(position+4*index+2)
            if sequence >= inputs:
                # Earlier actions may expand the sequence. Leave that profile to the engine.
                raise UnsupportedDocumentError('sfnt:GSUB: changed input context requires engine interpretation')
            if lookup >= lookups:
                raise InvalidDocumentError('sfnt:GSUB: context lookup outside LookupList')

    def glyph_array(self, position: int, count: int, classes: bool = False) -> int:
        self.need(position, 2*count)
        for index in range(count):
            if classes:
                self.word(position+2*index)  # Class labels are uint16, not glyph IDs.
            else:
                self.glyph(position+2*index)
        return position+2*count

    def context_rule(self, base: int, kind: int, lookups: int, classes: bool = False) -> None:
        if kind == 5:
            inputs, actions = self.word(base), self.word(base+2)
            if not inputs:
                raise UnsupportedDocumentError('sfnt:GSUB: empty input context outside native profile')
            position = self.glyph_array(base+4, inputs-1, classes)
        else:
            backtrack = self.word(base)
            position = self.glyph_array(base+2, backtrack, classes)
            inputs = self.word(position)
            if not inputs:
                raise UnsupportedDocumentError('sfnt:GSUB: empty input context outside native profile')
            position = self.glyph_array(position+2, inputs-1, classes)
            ahead = self.word(position)
            position = self.glyph_array(position+2, ahead, classes)
            actions = self.word(position)
            position += 2
        self.context_actions(position, actions, inputs, lookups)

    def context_rules(self, base: int, kind: int, lookups: int) -> None:
        count = self.word(base+4)
        self.need(base+6, 2*count)
        self.coverage(self.pointer(base, self.word(base+2), 6+2*count), count)
        for index in range(count):
            offset = self.word(base+6+2*index)
            if not offset:  # Explicit NULL rule set has no rules for this covered glyph.
                continue
            group = self.pointer(base, offset, 6+2*count)
            size = self.word(group)
            self.need(group+2, 2*size)
            for number in range(size):
                rule = self.pointer(group, self.word(group+2+2*number), 2+2*size)
                self.context_rule(rule, kind, lookups)

    def class_definition(self, base: int) -> dict[int, int]:
        kind = self.word(base)
        result: dict[int, int] = {}
        if kind == 1:
            first, count = self.word(base+2), self.word(base+4)
            if first+count > self.glyphs:
                raise InvalidDocumentError('sfnt:GSUB: class definition outside declared maxp')
            self.need(base+6, 2*count)
            for index in range(count):
                result[first+index] = self.word(base+6+2*index)
        elif kind == 2:
            count, previous = self.word(base+2), -1
            self.need(base+4, 6*count)
            for index in range(count):
                position = base+4+6*index
                start, end, label = self.glyph(position), self.glyph(position+2), self.word(position+4)
                if start > end or start <= previous:
                    raise InvalidDocumentError('sfnt:GSUB: unordered/overlapping class ranges')
                previous = end
                for glyph in range(start, end+1):
                    self.spend()
                    result[glyph] = label
        else:
            raise UnsupportedDocumentError('sfnt:GSUB: class definition requires native format 1/2')
        return result

    def context_classes(self, base: int, kind: int, lookups: int) -> None:
        header = 8 if kind == 5 else 12
        count = self.word(base+header-2)
        self.need(base+header, 2*count)
        minimum = header+2*count
        coverage = self.coverage(self.pointer(base, self.word(base+2), minimum), None)
        input_classes: dict[int, int] = {}
        for position in ((4,) if kind == 5 else (4, 6, 8)):
            classes = self.class_definition(self.pointer(base, self.word(base+position), minimum))
            if position == (4 if kind == 5 else 6):
                input_classes = classes
        for glyph in coverage:
            self.spend()
            if input_classes.get(glyph, 0) >= count:
                raise UnsupportedDocumentError('sfnt:GSUB: covered input class outside RuleSet array')
        for index in range(count):
            offset = self.word(base+header+2*index)
            if not offset:
                continue
            group = self.pointer(base, offset, minimum)
            size = self.word(group)
            self.need(group+2, 2*size)
            for number in range(size):
                rule = self.pointer(group, self.word(group+2+2*number), 2+2*size)
                self.context_rule(rule, kind, lookups, classes=True)

    def reverse_table(self, base: int) -> None:
        """Validate type 8 contexts, without applying substitutions or inferring Unicode."""
        if self.word(base) != 1:
            raise UnsupportedDocumentError('sfnt:GSUB: reverse substitution format outside native profile')
        offsets = [self.word(base+2)]
        position = base+4
        for _ in range(2):  # Backtrack and lookahead coverage arrays.
            count = self.word(position)
            position += 2
            self.need(position, 2*count)
            for index in range(count):
                offsets.append(self.word(position+2*index))
            position += 2*count
        count = self.word(position)
        position += 2
        self.need(position, 2*count)
        minimum = position+2*count-base
        for index, offset in enumerate(offsets):
            self.coverage(self.pointer(base, offset, minimum), count if index == 0 else None)
        for index in range(count):
            self.glyph(position+2*index)

    def ligature_table(self, base: int) -> None:
        if self.word(base) != 1:
            raise UnsupportedDocumentError('sfnt:GSUB: ligature format outside native profile')
        count = self.word(base+4)
        self.need(base+6, 2*count)
        coverage = self.coverage(self.pointer(base, self.word(base+2), 6+2*count), count)
        for index, first in enumerate(coverage):
            group = self.pointer(base, self.word(base+6+2*index), 6+2*count)
            size = self.word(group)
            self.need(group+2, 2*size)
            for number in range(size):
                self.ligatures += 1
                if self.ligatures > 100000:
                    raise ResourceLimitError('sfnt:GSUB: native ligature-count budget exceeded')
                record = self.pointer(group, self.word(group+2+2*number), 2+2*size)
                target, components = self.glyph(record), self.word(record+2)
                if not 2 <= components <= 32:
                    raise UnsupportedDocumentError('sfnt:GSUB: component count outside native profile')
                self.need(record+4, 2*(components-1))
                glyphs = [first, *(self.glyph(record+4+2*i) for i in range(components-1))]
                if not all(len(self.encoded.get(glyph, ())) == 1 for glyph in glyphs):
                    self.uncertain.add(target)
                else:
                    text = ''.join(next(iter(self.encoded[glyph])) for glyph in glyphs)
                    self.candidates.setdefault(target, set()).add(text)

    def read(self) -> dict[int, str]:
        major, minor = self.word(0), self.word(2)
        if major != 1 or minor not in (0, 1):
            raise UnsupportedDocumentError('sfnt:GSUB: native profile requires version 1.0/1.1')
        header = 14 if minor == 1 else 10
        self.need(0, header)
        if minor == 1:
            self.spend(2)
            if struct.unpack_from('>I', self.data, 10)[0]:
                raise UnsupportedDocumentError('sfnt:GSUB: feature variations outside native ligature profile')
        scripts, features, lookups = (self.pointer(0, self.word(position), header) for position in (4, 6, 8))
        count = self.word(lookups)
        if count > 1000:
            raise ResourceLimitError('sfnt:GSUB: native lookup-count budget exceeded')
        self.need(lookups+2, 2*count)
        self.metadata(scripts, features, count)
        for index in range(count):
            lookup = self.pointer(lookups, self.word(lookups+2+2*index), 2+2*count)
            kind, flags, size = self.word(lookup), self.word(lookup+2), self.word(lookup+4)
            if kind not in (1, 2, 3, 4, 5, 6, 7, 8) or flags:
                raise UnsupportedDocumentError('sfnt:GSUB: lookup type/flags outside native ligature profile')
            self.need(lookup+6, 2*size)
            extension_kind: int | None = None
            for number in range(size):
                table = self.pointer(lookup, self.word(lookup+6+2*number), 6+2*size)
                effective = kind
                if kind == 7:
                    effective = self.word(table+2)
                    if self.word(table) != 1 or effective not in (1, 2, 3, 4, 5, 6, 8):
                        raise UnsupportedDocumentError('sfnt:GSUB: extension outside native ligature profile')
                    if extension_kind is not None and effective != extension_kind:
                        raise InvalidDocumentError('sfnt:GSUB: inconsistent extension lookup types')
                    extension_kind = effective
                    self.need(table+4, 4)
                    self.spend(2)
                    offset = struct.unpack_from('>I', self.data, table+4)[0]
                    table = self.pointer(table, offset, 8)
                if effective == 1:
                    self.single_table(table)
                elif effective in (2, 3):
                    self.sequence_table(table, effective)
                elif effective in (5, 6):
                    self.context_table(table, effective, count)
                elif effective == 8:
                    self.reverse_table(table)
                else:
                    self.ligature_table(table)
        checkpoint()
        return {glyph: next(iter(texts)) for glyph, texts in self.candidates.items()
                if glyph not in self.encoded and glyph not in self.uncertain and len(texts) == 1}
