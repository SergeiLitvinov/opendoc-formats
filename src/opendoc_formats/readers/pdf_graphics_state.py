"""Bounded native PDF paint states, including Form XObject clip/group scopes.

This is adapter-owned extraction evidence, not a replacement Model scene graph.
The native engine interprets PDF streams, matrices, resource scopes and nesting.
"""

from __future__ import annotations

import math
from typing import Any, Callable

from opendoc_model import ArtifactLimitError, DocumentLimits


def native_paint_states(page: Any, *, limits: DocumentLimits | None = None) -> dict:
    import pymupdf

    mupdf = pymupdf.mupdf
    budget = limits or DocumentLimits()
    clips: list[dict] = []
    groups: list[dict] = []
    paints: list[dict] = []
    max_operations = min(100_000, budget.max_nodes)
    max_depth = min(64, budget.max_depth)
    commands = 0

    def guard(count: int, maximum: int, quota: str) -> None:
        if count > maximum:
            raise ArtifactLimitError('PDF graphics evidence exceeds selected budget',
                                     path='$.sections.pdf_graphics', quota=quota, maximum=maximum)

    class PathWalker(mupdf.FzPathWalker2):
        def __init__(self, matrix: Any) -> None:
            super().__init__()
            self.matrix = mupdf.FzMatrix(matrix)
            self.items = []
            self.error = None
            for name in ('moveto', 'lineto', 'curveto', 'closepath'):
                getattr(self, 'use_virtual_' + name)()

        def add(self, operator: str, *coordinates: float) -> None:
            nonlocal commands
            if self.error is not None:
                return
            commands += 1
            try:
                guard(commands, min(50_000, budget.max_nodes), 'nodes')
                points = []
                for x, y in zip(coordinates[::2], coordinates[1::2], strict=True):
                    point = mupdf.fz_transform_point(mupdf.FzPoint(x, y), self.matrix)
                    points.extend((point.x, point.y))
                if any(not math.isfinite(v) or abs(v) > 1_000_000 for v in points):
                    raise ValueError('Invalid native clip coordinates')
                self.items.append([operator, *points])
            except (ArtifactLimitError, ValueError) as error:
                self.error = error

        def moveto(self, ctx: Any, x: float, y: float) -> None:
            self.add('M', x, y)

        def lineto(self, ctx: Any, x: float, y: float) -> None:
            self.add('L', x, y)

        def curveto(self, ctx: Any, x1: float, y1: float, x2: float, y2: float, x3: float, y3: float) -> None:
            self.add('C', x1, y1, x2, y2, x3, y3)

        def closepath(self, ctx: Any) -> None:
            self.add('Z')

    def paint_callback(kind: str) -> Callable[..., None]:
        def callback(device: Any, *args: Any) -> None:
            device.paint(kind, 1.0 if kind == 'ignore-text' else float(args[-2]))
        return callback

    class StateDevice(mupdf.FzDevice2):
        def __init__(self) -> None:
            super().__init__()
            self.clip_stack = []
            self.group_stack = []
            self.error = None
            self.mask_depth = 0
            self.tile_depth = 0
            self.image_masks = {}
            for name in ('fill_path', 'stroke_path', 'fill_text', 'stroke_text', 'ignore_text',
                         'fill_image', 'fill_image_mask', 'fill_shade', 'clip_path', 'clip_stroke_path',
                         'clip_text', 'clip_stroke_text', 'clip_image_mask', 'pop_clip', 'begin_group',
                         'end_group', 'begin_mask', 'end_mask', 'begin_tile', 'end_tile'):
                getattr(self, 'use_virtual_' + name)()

        def paint(self, kind: str, alpha: float) -> None:
            if self.error is not None:
                return
            try:
                guard(len(paints) + 1, max_operations, 'nodes')
                paints.append({'kind': kind, 'clips': list(self.clip_stack), 'groups': list(self.group_stack),
                               'unknown': bool(self.mask_depth or self.tile_depth), 'alpha': alpha})
            except ArtifactLimitError as error:
                self.error = error

        fill_path = paint_callback('fill-path')
        stroke_path = paint_callback('stroke-path')
        fill_text = paint_callback('fill-text')
        stroke_text = paint_callback('stroke-text')
        ignore_text = paint_callback('ignore-text')
        fill_shade = paint_callback('fill-shade')

        def fill_image_mask(self, *args: Any) -> None:
            self.paint('fill-image', float(args[-2]))
            if self.error is None:
                paints[-1]['unknown'] = True  # A painted stencil is not an intrinsic alpha plane.

        def push_clip(self, record: dict) -> None:
            if self.error is not None:
                return
            try:
                guard(len(self.clip_stack) + len(self.group_stack) + 1, max_depth, 'depth')
                guard(len(clips) + len(groups) + len(paints) + 1, max_operations, 'nodes')
                self.clip_stack.append(len(clips))
                clips.append(record)
            except ArtifactLimitError as error:
                self.error = error

        def clip_path(self, ctx: Any, path: Any, even_odd: int, matrix: Any, scissor: Any) -> None:
            walker = PathWalker(matrix)
            # Both pointers are borrowed for this callback; no owning wrappers.
            mupdf.ll_fz_walk_path(path, walker.m_internal, walker.m_internal)
            if walker.error is not None:
                self.error = walker.error
            self.push_clip({'commands': walker.items, 'even_odd': bool(even_odd)})

        def unknown_clip(self, *args: Any) -> None:
            self.push_clip({'unknown': True})

        clip_stroke_path = unknown_clip
        clip_text = unknown_clip
        clip_stroke_text = unknown_clip

        def clip_image_mask(self, ctx: Any, image: Any, matrix: Any, scissor: Any) -> None:
            self.push_clip({'unknown': True})
            if self.error is None:
                self.image_masks[self.clip_stack[-1]] = (
                    int(image.this), tuple(getattr(matrix, key) for key in 'abcdef'))

        def fill_image(self, ctx: Any, image: Any, matrix: Any, alpha: float, params: Any) -> None:
            self.paint('fill-image', float(alpha))
            if self.error is None and image.use_colorkey:
                # Includes /SMask /Matte: stored RGB is preblended and cannot
                # be combined with alpha as if it were straight RGB samples.
                paints[-1]['unknown'] = True
            if self.error is not None or not self.clip_stack or not image.mask:
                return
            # MuPDF clips an image to its own intrinsic alpha before painting it.
            # The extractor already retains exactly that mask in the PNG samples.
            identity = (int(image.mask.this), tuple(getattr(matrix, key) for key in 'abcdef'))
            if self.image_masks.get(self.clip_stack[-1]) == identity:
                paints[-1]['clips'].pop()

        def pop_clip(self, ctx: Any) -> None:
            if self.error is not None:
                return
            if not self.clip_stack:
                self.error = ValueError('Unbalanced native PDF clip scope')
            else:
                self.clip_stack.pop()

        def begin_group(self, ctx: Any, area: Any, colorspace: Any, isolated: int,
                        knockout: int, blendmode: int, alpha: float) -> None:
            if self.error is not None:
                return
            try:
                guard(len(self.clip_stack) + len(self.group_stack) + 1, max_depth, 'depth')
                guard(len(clips) + len(groups) + len(paints) + 1, max_operations, 'nodes')
                self.group_stack.append(len(groups))
                groups.append({'bbox': [area.x0, area.y0, area.x1, area.y1], 'isolated': bool(isolated),
                               'knockout': bool(knockout), 'blendmode': int(blendmode), 'opacity': float(alpha),
                               'colorspace': mupdf.ll_fz_colorspace_name(colorspace) if colorspace else None})
            except ArtifactLimitError as error:
                self.error = error

        def end_group(self, ctx: Any) -> None:
            if self.error is not None:
                return
            if not self.group_stack:
                self.error = ValueError('Unbalanced native PDF group scope')
            else:
                self.group_stack.pop()

        def begin_mask(self, *args: Any) -> None:
            self.mask_depth += 1

        def end_mask(self, *args: Any) -> None:
            self.mask_depth -= 1
            self.push_clip({'unknown': True})

        def begin_tile(self, *args: Any) -> int:
            self.tile_depth += 1
            return 0

        def end_tile(self, *args: Any) -> None:
            self.tile_depth -= 1

    rotation = page.rotation
    try:
        page.set_rotation(0)
        device = StateDevice()
        mupdf.fz_run_page_contents(page.this, device, mupdf.FzMatrix(), mupdf.FzCookie())
        mupdf.fz_close_device(device)
        if device.error is not None:
            raise device.error
        if device.clip_stack or device.group_stack or device.mask_depth or device.tile_depth:
            raise ValueError('Unbalanced native PDF graphics state')
        native_bounds = page.get_bboxlog()
        if len(native_bounds) != len(paints) or any(item['kind'] != box[0] for item, box in zip(paints, native_bounds)):
            raise ValueError('Native PDF paint sequence could not be verified')
        for item, (_, bounds) in zip(paints, native_bounds, strict=True):
            item['bbox'] = list(bounds)
        evidence = {'version': 1, 'clips': clips, 'groups': groups, 'paints': paints}
        from opendoc_formats.readers.pdf_scopes import needs_scene

        if needs_scene(evidence):
            from opendoc_formats.readers.pdf_composition_policy import unsupported_policy

            policy = unsupported_policy(page.parent, budget)
            if policy:
                evidence['unsupported_compositing'] = policy
        return evidence
    except ArtifactLimitError:
        raise
    except (AttributeError, TypeError, RuntimeError, ValueError) as error:
        return {'version': 1, 'unknown': str(error)}
    finally:
        page.set_rotation(rotation)
