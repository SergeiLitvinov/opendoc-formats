"""Bind measured PDF paint scopes to the official mixed VectorScene contract."""

from __future__ import annotations

from opendoc_model import (
    Anchor,
    DocumentLimits,
    DocumentModel,
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


def attach_pdf_scopes(document: DocumentModel, *, limits: DocumentLimits | None) -> None:
    for index, section in enumerate(document.sections):
        evidence = section.properties.get('pdf_graphics', {})
        if not needs_scene(evidence):
            continue
        identifier = f'pdf-scopes-{index}'
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
                                                       blend_mode=BLENDS[mode] if 0 <= mode < len(BLENDS) else None)
                    children[group_id] = []
                    children[parent].append(group_id)
                parent = group_id
            occurrence_id = f'paint-{sequence}-{ordinal}'
            for offset, key in enumerate(paint['clips']):
                clip_group = f'{occurrence_id}-clip-{offset}'
                groups[clip_group] = NEUTRAL
                children[clip_group] = []
                children[parent].append(clip_group)
                parent = clip_group
            children[parent].append(occurrence_id)
            occurrences.append(SceneOccurrence(occurrence_id, anchor.id, compositing=NEUTRAL))
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
                                      extra={'pdf_blending_colorspace': native_space}))
        scene = VectorScene(identifier, section.page.width.pt, section.page.height.pt, groups=tuple(scopes),
                            occurrences=tuple(occurrences), clips=tuple(clips), roots=tuple(children[None]), scope_version=1)
        set_vector_scene(document, scene, limits=limits)
        section.properties['pdf_scene_id'] = identifier
        section.properties['pdf_scene_complete'] = len(covered) == len(evidence['paints'])
