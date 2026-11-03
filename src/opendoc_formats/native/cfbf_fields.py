"""Finite MS-CFB directory-field audit; MUST, SHOULD and legacy compatibility stay distinct."""

from __future__ import annotations

import struct
from typing import Any

from opendoc_formats.errors import ResourceLimitError
from opendoc_formats.support.cancellation import checkpoint


def header_fields(raw: memoryview, version: int, sector_size: int) -> dict[str, Any]:
    """Audit reserved header fields within an already bounded v3/v4 sector."""
    findings: list[dict[str, Any]] = []
    fields = [('header_clsid', 8, 16), ('reserved', 34, 6)]
    if version == 4:
        fields.append(('header_padding', 512, sector_size-512))
    for field, offset, size in fields:
        checkpoint()
        if any(raw[offset:offset+size]):
            findings.append({'code': 'nonzero-'+field.replace('_', '-'), 'field': field, 'rule': 'must',
                              'location': 'cfbf:header/'+field, 'byte_range': {'offset': offset, 'length': size}})
    constraints_valid = not findings
    checkpoint()
    recommended = struct.unpack_from('<H', raw, 24)[0] == 0x003e
    if not recommended:
        findings.append({'code': 'unexpected-minor-version', 'field': 'minor_version', 'rule': 'should',
                          'location': 'cfbf:header/minor_version', 'byte_range': {'offset': 24, 'length': 2}})
    return {'header_fields_assessed': True, 'header_field_constraints_valid': constraints_valid,
            'header_field_recommendations_met': recommended, 'header_field_findings': tuple(findings)}


class DirectoryFields:
    def __init__(self, version: int, maximum: int) -> None:
        self.version, self.maximum = version, maximum
        self.findings: list[dict[str, Any]] = []
        self.constraints_valid = True
        self.recommendations_met = True

    def finding(self, code: str, index: int, offset: int, field: str, relative: int, size: int,
                *, rule: str = 'must') -> None:
        checkpoint()
        if len(self.findings) >= self.maximum:
            raise ResourceLimitError(f'cfbf:directory={index}/{field}: max_items exceeded by field findings')
        self.findings.append({'code': code, 'location': f'cfbf:directory={index}/{field}',
                              'directory_index': index, 'field': field, 'rule': rule,
                              'byte_range': {'offset': offset+relative, 'length': size}})
        if rule == 'must':
            self.constraints_valid = False
        elif rule == 'should':
            self.recommendations_met = False

    def entry(self, index: int, offset: int, raw: memoryview, kind: int, name: str | None) -> None:
        checkpoint()
        if kind == 0:
            # MS-CFB 2.6.3: unused slots are zero except for NOSTREAM links.
            fields = (('name', 0, 64), ('name_length', 64, 2), ('color', 67, 1), ('clsid', 80, 16),
                      ('state_bits', 96, 4), ('creation_time', 100, 8), ('modified_time', 108, 8),
                      ('starting_sector', 116, 4), ('stream_size', 120, 8))
            for field, relative, size in fields:
                checkpoint()
                if any(raw[relative:relative+size]):
                    self.finding('nonzero-unallocated-field', index, offset, field, relative, size)
            for field, relative in (('left_sibling', 68), ('right_sibling', 72), ('child', 76)):
                checkpoint()
                if struct.unpack_from('<I', raw, relative)[0] != 0xffffffff:
                    self.finding('unallocated-pointer-not-nostream', index, offset, field, relative, 4)
            return
        if name is not None:
            for position, char in enumerate(name):
                checkpoint()
                if char == '\0' or char in '/\\:!':
                    relative = len(name[:position].encode('utf-16-le'))
                    self.finding('embedded-name-terminator' if char == '\0' else 'illegal-name-character',
                                 index, offset, 'name', relative, 2)
            if kind == 5 and name != 'Root Entry':
                self.finding('invalid-root-name', index, offset, 'name', 0, 64)
        if kind == 2:
            for field, relative, size in (('clsid', 80, 16), ('creation_time', 100, 8), ('modified_time', 108, 8)):
                if any(raw[relative:relative+size]):
                    self.finding('nonzero-stream-field', index, offset, field, relative, size)
            if any(raw[96:100]):
                self.finding('nonzero-stream-state-bits', index, offset, 'state_bits', 96, 4, rule='should')
        elif kind == 5 and any(raw[100:108]):
            self.finding('nonzero-root-creation-time', index, offset, 'creation_time', 100, 8)
        elif kind == 1:
            for field, relative, size in (('starting_sector', 116, 4), ('stream_size', 120, 8)):
                if any(raw[relative:relative+size]):
                    self.finding('nonzero-storage-field', index, offset, field, relative, size)
        # MS-CFB 2.6.3 requires readers to accept old v3 high DWORD contents.
        if self.version == 3 and kind in (2, 5) and any(raw[124:128]):
            self.finding('legacy-v3-size-high-dword', index, offset, 'stream_size', 124, 4, rule='compatibility')

    def result(self) -> dict[str, Any]:
        checkpoint()
        return {'directory_fields_assessed': True, 'directory_field_constraints_valid': self.constraints_valid,
                'directory_field_recommendations_met': self.recommendations_met,
                'directory_field_findings': tuple(self.findings)}
