"""Bind measured PDF paint scopes to the official mixed VectorScene contract."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from opendoc_model import (
    Anchor,
    DocumentLimits,
    DocumentModel,
    GroupColorSpace,
    GroupCompositing,
    Image,
    PathCommand,
    SceneOccurrence,
    TextRun,
    VectorClip,
    VectorGroup,
    VectorScene,
    get_anchor,
    set_anchor,
    set_vector_scene,
    walk_model,
)

from opendoc_formats.pdf_graphics import axis_rectangle, contains, rectangle_points

BLENDS = ('normal', 'multiply', 'screen', 'overlay', 'darken', 'lighten', 'color-dodge',
          'color-burn', 'hard-light', 'soft-light', 'difference', 'exclusion', 'hue',
          'saturation', 'color', 'luminosity')
NEUTRAL = GroupCompositing(opacity=1, isolated=False, knockout=False, blend_mode='normal')


def scope_color_spaces(evidence: dict) -> dict[int | None, GroupColorSpace]:
    """Resolve PDF inheritance in the adapter's explicit RGB device profile."""
    names = {'DeviceRGB': 'rgb', 'DeviceGray': 'gray', 'DeviceCMYK': 'cmyk'}
    spaces = {None: GroupColorSpace(names.get(evidence.get('device_color_space')))}
    for paint in evidence['paints']:
        parent = None
        for key in paint['groups']:
            native = evidence['groups'][key]['colorspace']
            value = spaces[parent] if native is None else GroupColorSpace(names.get(native), extra={'pdf_native_name': native})
            if key in spaces and spaces[key] != value:
                raise ValueError('Inconsistent native group color-space inheritance')
            spaces[key] = value
            parent = key
    return spaces


def needs_scene(evidence: dict) -> bool:
    if evidence.get('unknown'):
        return False
    if any(g['opacity'] != 1 or g['knockout'] or g['blendmode'] or g['colorspace'] not in (None, 'DeviceRGB')
           for g in evidence.get('groups', [])):
        return True
    for paint in evidence.get('paints', []):
        if paint['kind'] != 'fill-text':
            continue
        for key in paint['clips']:
            clip = evidence['clips'][key]
            if clip.get('unknown'):
                continue
            points = rectangle_points(clip)
            box = axis_rectangle(points) if points else None
            if box is None or not contains(box, paint.get('ink_bbox', paint['bbox'])):
                return True
    return False


def attach_pdf_scopes(document: DocumentModel, *, limits: DocumentLimits | None, include_neutral: bool = False,
                       cancelled: Callable[[], bool] | None = None) -> None:
    from opendoc_formats.support.cancellation import check_cancelled

    check_cancelled(cancelled, 'PDF scopes')
    for index, section in enumerate(document.sections):
        check_cancelled(cancelled, 'PDF scope section')
        evidence = section.properties.get('pdf_graphics', {})
        if 'pdf_scene_id' in section.properties:
            continue  # An explicitly removed scene is never regenerated from native evidence.
        if not needs_scene(evidence) and not (include_neutral and 'device_color_space' in evidence
                and any(not g.get('device_page_group') for g in evidence.get('groups', []))):
            continue
        identifier = f'pdf-scopes-{index}'
        color_spaces = scope_color_spaces(evidence)
        clips = []
        used_clips = {key for paint in evidence['paints'] for key in paint['clips']}
        if any(evidence['clips'][key].get('unknown') for key in used_clips):
            continue
        for key, clip in enumerate(evidence['clips']):
            if clip.get('unknown'):
                continue
            commands = tuple(PathCommand({'M': 'move', 'L': 'line', 'C': 'cubic', 'Z': 'close'}[c[0]], tuple(c[1:]))
                             for c in clip['commands'])
            clips.append(VectorClip(f'clip-{key}', commands, 'evenodd' if clip['even_odd'] else 'nonzero'))
        # Intrinsic alpha planes leave unused unknown clip entries. They are not
        # general clips and must not become a second mask in the scene.
        groups = {}
        children = {None: []}
        occurrences = []
        covered = set()
        nodes = [(ordinal, ref.node) for ordinal, ref in enumerate(walk_model(section, limits=limits))
                 if isinstance(ref.node, (Image, TextRun)) and type(ref.node.properties.get('pdf_paint_seq')) is int]
        for ordinal, node in sorted(nodes, key=lambda pair: (pair[1].properties['pdf_paint_seq'], pair[0])):
            sequence = node.properties.get('pdf_paint_seq')
            if type(sequence) is not int or not 0 <= sequence < len(evidence['paints']):
                continue
            paint = evidence['paints'][sequence]
            if paint.get('unknown'):
                continue
            anchor = get_anchor(node, limits=limits)
            if anchor is None:
                anchor = Anchor(f'{identifier}-node-{ordinal}')
                set_anchor(node, anchor, limits=limits)
            parent = None
            for key in paint['groups']:
                group_id = f'group-{key}'
                if group_id not in groups:
                    native = evidence['groups'][key]
                    mode = native['blendmode']
                    groups[group_id] = GroupCompositing(opacity=native['opacity'], isolated=native['isolated'],
                                                       knockout=native['knockout'],
                                                       blend_mode=BLENDS[mode] if 0 <= mode < len(BLENDS) else None,
                                                       color_space=color_spaces[key])
                    children[group_id] = []
                    children[parent].append(group_id)
                parent = group_id
            occurrence_id = f'paint-{sequence}-{ordinal}'
            space = color_spaces[paint['groups'][-1] if paint['groups'] else None]
            neutral = replace(NEUTRAL, color_space=space)
            for offset, key in enumerate(paint['clips']):
                clip_group = f'{occurrence_id}-clip-{offset}'
                groups[clip_group] = neutral
                children[clip_group] = []
                children[parent].append(clip_group)
                parent = clip_group
            children[parent].append(occurrence_id)
            occurrences.append(SceneOccurrence(occurrence_id, anchor.id, compositing=neutral))
            covered.add(sequence)
        scopes = []
        for key, value in groups.items():
            clip_id = None
            if '-clip-' in key:
                occurrence_id, offset = key.rsplit('-clip-', 1)
                sequence = int(occurrence_id.split('-')[1])
                clip_id = f"clip-{evidence['paints'][sequence]['clips'][int(offset)]}"
            native_space = (evidence['groups'][int(key.removeprefix('group-'))]['colorspace']
                            if key.startswith('group-') else 'DeviceRGB')
            scopes.append(VectorGroup(key, tuple(children[key]), clip_id=clip_id, compositing=value,
                                      extra={'pdf_blending_colorspace': native_space,
                                             'pdf_clip_wrapper': '-clip-' in key,
                                             'pdf_device_page_group': (evidence['groups'][int(key.removeprefix('group-'))]
                                                                      .get('device_page_group', False)
                                                                      if key.startswith('group-') else False)}))
        scene = VectorScene(identifier, section.page.width.pt, section.page.height.pt, groups=tuple(scopes),
                            occurrences=tuple(occurrences), clips=tuple(clips), roots=tuple(children[None]), scope_version=1)
        set_vector_scene(document, scene, limits=limits)
        section.properties['pdf_scene_id'] = identifier
        section.properties['pdf_scene_complete'] = len(covered) == len(evidence['paints'])
    check_cancelled(cancelled, 'PDF scopes completion')
