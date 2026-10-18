"""Validate adapter-owned native PDF paint evidence before a target projection."""

from __future__ import annotations

import math
from typing import Any


def finite_number(value: Any) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or abs(value) > 1_000_000:
        raise ValueError('Invalid native PDF graphics coordinate')
    return float(value)


def paint_clips(evidence: dict, sequence: int, kinds: set[str]) -> tuple[dict, list[dict]]:
    if not isinstance(evidence, dict) or evidence.get('version') != 1 or evidence.get('unknown'):
        raise ValueError('Unknown native PDF graphics evidence')
    paints = evidence.get('paints')
    if type(sequence) is not int or not isinstance(paints, list) or not 0 <= sequence < len(paints):
        raise ValueError('Missing native PDF paint occurrence')
    paint = paints[sequence]
    if not isinstance(paint, dict) or paint.get('unknown') or paint.get('kind') not in kinds:
        raise ValueError('Unsupported native PDF paint operation or mask')
    bounds = paint.get('bbox')
    if not isinstance(bounds, list) or len(bounds) != 4:
        raise ValueError('Missing native PDF paint bounds')
    x0, y0, x1, y1 = map(finite_number, bounds)
    if x1 < x0 or y1 < y0 or not 0 <= finite_number(paint.get('alpha')) <= 1:
        raise ValueError('Invalid native PDF paint bounds or opacity')
    result = []
    for key in ('clips', 'groups'):
        identifiers, records = paint.get(key), evidence.get(key)
        if not isinstance(identifiers, list) or len(identifiers) > 64 or not isinstance(records, list):
            raise ValueError('Invalid native PDF graphics stack')
        for identifier in identifiers:
            if type(identifier) is not int or not 0 <= identifier < len(records):
                raise ValueError('Invalid native PDF graphics scope reference')
            record = records[identifier]
            if not isinstance(record, dict):
                raise ValueError('Invalid native PDF graphics scope')
            if key == 'groups':
                if (type(record.get('isolated')) is not bool or record.get('knockout') is not False
                        or type(record.get('blendmode')) is not int or record['blendmode'] != 0
                        or finite_number(record.get('opacity')) != 1
                        or record.get('colorspace') not in (None, 'DeviceRGB', 'DeviceGray')):
                    raise ValueError('PDF compositing group requires an explicit group representation')
                continue
            commands = record.get('commands')
            if (record.get('unknown') or type(record.get('even_odd')) is not bool
                    or not isinstance(commands, list) or not commands or len(commands) > 50_000):
                raise ValueError('Unsupported native PDF clipping path')
            for command in commands:
                if (not isinstance(command, list) or not command
                        or len(command) != {'M': 3, 'L': 3, 'C': 7, 'Z': 1}.get(command[0])):
                    raise ValueError('Invalid native PDF clipping command')
                for value in command[1:]:
                    finite_number(value)
            if commands[0][0] != 'M':
                raise ValueError('Native PDF clip must begin with a subpath')
            result.append(record)
    return paint, result


def rectangle_points(clip: dict) -> list[tuple[float, float]] | None:
    commands = clip['commands']
    if len(commands) == 6 and commands[-2] == ['L', *commands[0][1:]]:
        commands = commands[:-2] + [commands[-1]]
    if len(commands) != 5 or [item[0] for item in commands] != ['M', 'L', 'L', 'L', 'Z']:
        return None
    return [(item[1], item[2]) for item in commands[:-1]]


def axis_rectangle(points: list[tuple[float, float]], *, tolerance: float = .0001) -> list[float] | None:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    bounds = [min(xs), min(ys), max(xs), max(ys)]
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        return None
    corners = {(0, 0), (0, 1), (1, 0), (1, 1)}
    seen = set()
    for x, y in points:
        ix = 0 if abs(x-bounds[0]) <= tolerance else 1 if abs(x-bounds[2]) <= tolerance else None
        iy = 0 if abs(y-bounds[1]) <= tolerance else 1 if abs(y-bounds[3]) <= tolerance else None
        if ix is None or iy is None:
            return None
        seen.add((ix, iy))
    if seen != corners or any(abs(a[0]-b[0]) > tolerance and abs(a[1]-b[1]) > tolerance
                              for a, b in zip(points, points[1:] + points[:1])):
        return None
    return bounds


def contains(bounds: list[float], inner: list[float]) -> bool:
    return (inner[0] >= bounds[0] - .0001 and inner[1] >= bounds[1] - .0001
            and inner[2] <= bounds[2] + .0001 and inner[3] <= bounds[3] + .0001)
