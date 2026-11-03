"""Finite source PNG declarations; no pixel decoding or color-profile precedence."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING, Any

from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import BinaryItem


def inspect_metadata(data: bytes, items: list[BinaryItem], header: dict[str, Any]) -> dict[str, Any]:
    """Inspect fixed metadata within the already bounded, CRC-verified source inventory."""
    pending: dict[str, list[tuple[int, BinaryItem]]] = {name: [] for name in ('tRNS', 'gAMA', 'sRGB', 'pHYs')}
    first_idat: int | None = None
    palette: tuple[int, int] | None = None
    for ordinal, item in enumerate(items):
        checkpoint()
        fields = dict(item.details)
        name = fields.get('chunk_type')
        if name in pending:
            pending[name].append((ordinal, item))
        elif name == 'IDAT' and first_idat is None:
            first_idat = ordinal
        elif name == 'PLTE':
            palette = ordinal, fields['data_length'] // 3
    declarations: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    def issue(item: BinaryItem, reason: str, message: str) -> None:
        findings.append({'code': 'png.metadata.' + reason, 'location': item.locator, 'message': message})

    for name, entries in pending.items():
        checkpoint()
        if len(entries) > 1:
            for _, item in entries:
                checkpoint()
                issue(item, 'duplicate', f'Multiple {name} declarations; no occurrence selected')
            continue
        if not entries:
            continue
        ordinal, item = entries[0]
        fields = dict(item.details)
        offset, length = fields['data_offset'], fields['data_length']
        if (first_idat is None or ordinal > first_idat
                or name in ('gAMA', 'sRGB') and palette is not None and ordinal > palette[0]
                or name == 'tRNS' and palette is not None and ordinal < palette[0]):
            issue(item, 'order', f'{name} is outside the accepted chunk order')
            continue
        values: dict[str, Any]
        if name == 'tRNS':
            color, depth = header['color_type'], header['bit_depth']
            if color == 3 and palette is not None and length <= palette[1]:
                values = {'palette_entries': palette[1], 'declared_alpha': tuple(data[offset:offset + length]),
                          'implicit_alpha': 255}
            elif color in (0, 2) and length == (2 if color == 0 else 6):
                raw = struct.unpack_from('>H' if color == 0 else '>HHH', data, offset)
                values = {'sample_depth': depth, 'transparent_samples_raw': raw,
                          'transparent_samples': tuple(value & ((1 << depth) - 1) for value in raw)}
            else:
                issue(item, 'profile', 'tRNS length/color/palette profile is not accepted')
                continue
        elif name == 'gAMA':
            if length != 4:
                issue(item, 'length', 'gAMA requires four data bytes')
                continue
            gamma = struct.unpack_from('>I', data, offset)[0]
            if gamma == 0:
                issue(item, 'profile', 'Zero gAMA is outside the positive gamma declaration profile')
                continue
            values = {'gamma_times_100000': gamma}
        elif name == 'sRGB':
            if length != 1 or data[offset] > 3:
                issue(item, 'profile', 'sRGB requires one accepted rendering intent byte (0..3)')
                continue
            values = {'rendering_intent': data[offset]}
        else:
            if length != 9:
                issue(item, 'length', 'pHYs requires nine data bytes')
                continue
            x, y, unit = struct.unpack_from('>IIB', data, offset)
            if unit not in (0, 1):
                issue(item, 'profile', 'pHYs unit is outside the unknown/metre profile')
                continue
            values = {'pixels_per_unit_x': x, 'pixels_per_unit_y': y, 'unit_specifier': unit}
        declarations.append({'chunk_type': name, 'location': item.locator,
                             'source_data_offset': offset, 'values': values})
    declarations.sort(key=lambda value: value['source_data_offset'])
    return {'metadata_declarations': tuple(declarations), 'metadata_findings': tuple(findings),
            'color_interpretation_assessed': False}


__all__ = ['inspect_metadata']
