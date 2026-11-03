"""Isolated public-API acceptance of the frozen C-BACKGROUND-GRADIENT-01 candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from dataclasses import replace
from importlib.metadata import distributions
from pathlib import Path
from zipfile import ZipFile

import opendoc_model as od

WHEEL_SHA256 = 'cf33977cddd155ad3ef9fc7fa5c93be71c0f7d3d7e127384d36edac5d56de034'


def paint():
    colors = [od.ColorValue.from_hex('#204060', alpha=.25), None,
              od.ColorValue.from_hex('#CC8844', alpha=0),
              od.ColorValue(od.ColorSpace.CMYK, (.1, .2, .3, .4), .8, 'opaque-profile-id', 'multiply')]
    stops = tuple(od.GradientStop(position, color, extra={'future-stop': [index]})
                  for index, (position, color) in enumerate(zip((.1, .5, .5, .9), colors, strict=True)))
    return od.BackgroundPaint('gradient', gradient=od.GradientPaint(
        stops, linear=od.LinearGradient('relative', od.Point2D(-.2, 0), od.Point2D(1.2, 1)),
        opacity=.7, spread='reflect', interpolation='linear-srgb', extra={'future-gradient': [2]}),
        extra={'future-background': [3]})


def fixture():
    section = od.Section([od.Paragraph([od.TextRun('Visible body')])])
    od.set_section_background(section, paint())
    section.properties[od.BACKGROUND_PROPERTY]['future-envelope'] = [4]
    section.properties['opendoc_formats.pptx_background_gradient'] = {'version': 999, 'xml': '<never-execute/>'}
    page = od.with_page_background(od.DocumentPage('page', 600, 800), replace(paint(), gradient=replace(
        paint().gradient, linear=None, radial=od.RadialGradient('points', od.Point2D(30, 40), 120))))
    document = od.DocumentModel([section])
    od.set_integration(document, od.IntegrationModel(pages=(page,)))
    return document


def cycles(document):
    before = od.document_to_dict(document)
    for _ in range(2):
        document = od.document_from_json(od.document_to_json(document))
        assert od.document_to_dict(document) == before
    assert not document.validate(), document.validate()
    return document


def rejected(action, match=None):
    try:
        action()
    except ValueError as error:
        assert not isinstance(error, od.ArtifactLimitError), 'Invalid data misclassified as quota failure'
        assert match is None or match in str(error), str(error)
        return str(error)
    raise AssertionError('Invalid background accepted')


def checks():
    results, failures = [], []
    original = fixture()
    document = cycles(original)
    section = document.sections[0]
    background = od.get_section_background(section)
    gradient = background.gradient
    assert [stop.position for stop in gradient.stops] == [.1, .5, .5, .9]
    assert gradient.stops[1].color is None and gradient.stops[2].color.alpha == 0
    assert gradient.stops[0].color.alpha == .25 and gradient.opacity == .7
    assert gradient.stops[-1].color.space is od.ColorSpace.CMYK
    assert gradient.stops[-1].color.icc_profile == 'opaque-profile-id' and gradient.stops[-1].color.blend_mode == 'multiply'
    assert gradient.linear.start.x == -.2 and gradient.spread == 'reflect' and gradient.interpolation == 'linear-srgb'
    assert od.get_page_background(od.get_integration(document).pages[0]).gradient.radial.radius == 120
    assert od.extract_text(document) == 'Visible body'
    assert od.BackgroundPaint.from_dict(background.to_dict()) == background
    for value in (gradient, *gradient.stops, gradient.linear,
                  od.get_page_background(od.get_integration(document).pages[0]).gradient.radial):
        assert type(value).from_dict(value.to_dict()) == value
    results.append('two document cycles and all DTO codecs retain coincident interior stops, alpha, unknown color and geometry')

    background.extra['future-background'].append(8)
    gradient.stops[0].extra['future-stop'].append(8)
    assert od.get_section_background(section) == paint()
    raw = paint().to_dict()
    decoded = od.BackgroundPaint.from_dict(raw)
    raw['future-background'].append(8)
    assert decoded.extra['future-background'] == [3]
    value = od.get_section_background(section)
    edited = replace(value, gradient=replace(value.gradient, stops=(
        replace(value.gradient.stops[0], color=od.ColorValue.from_hex('#22AA66')),
        replace(value.gradient.stops[-1], position=.8))))
    od.set_section_background(section, edited)
    assert od.get_section_background(cycles(document).sections[0]) == edited
    assert section.properties[od.BACKGROUND_PROPERTY]['future-envelope'] == [4]
    assert od.get_section_background(original.sections[0]) == paint()
    for role in (od.BackgroundPaint('none'), od.BackgroundPaint('unknown'),
                 od.BackgroundPaint('solid', solid=od.Paint(od.ColorValue.from_hex('#112233'), .4)),
                 od.BackgroundPaint('gradient', gradient=od.GradientPaint()), None):
        od.set_section_background(section, role)
        assert od.get_section_background(cycles(document).sections[0]) == role
    assert od.BACKGROUND_PROPERTY not in section.properties
    assert section.properties['opendoc_formats.pptx_background_gradient']['version'] == 999
    results.append('independent snapshots and authoritative edits/removals preserve unknown envelope; native hints stay inert')

    document = fixture()
    page = od.get_integration(document).pages[0]
    updated = od.with_page_background(page, None)
    assert od.get_page_background(updated) is None and od.get_page_background(page) is not None
    assert od.get_section_background(od.Section()) is None
    assert od.get_page_background(od.DocumentPage('absent', 600, 800)) is None
    locations = list(od.iter_backgrounds(document))
    assert [(item.kind, item.page_id) for item in locations] == [('section', None), ('page', 'page')]
    assert len({item.path for item in locations}) == 2
    locations[0].background.extra['future-background'].append(8)
    assert od.get_section_background(document.sections[0]) == paint()
    assert not any(type(item.node).__name__ in ('BackgroundPaint', 'GradientPaint') for item in od.walk_model(document))
    assert not list(od.iter_resource_references(document))
    results.append('section/page scopes have no inferred cascade; separate walk creates no body nodes; '
                   'CMYK/ICC/blend remain color data, not invented resources')

    before = od.document_to_json(document)
    merged = cycles(od.merge_documents([document, document], metadata_conflicts='keep_last').document)
    assert len(merged.sections) == 2 and len(list(od.iter_backgrounds(merged))) == 3
    location = next(item for item in od.walk_model(document) if isinstance(item.node, od.Section))
    extracted = cycles(od.extract_document(document, location))
    assert od.get_section_background(extracted.sections[0]) == paint()
    assert od.document_to_json(document) == before
    results.append('merge retains both section declarations and explicit metadata policy; section extraction preserves paint')

    for operation in (
        lambda: od.GradientStop(float('nan')), lambda: od.GradientStop(True), lambda: od.GradientStop(-.01),
        lambda: od.GradientPaint(stops=(od.GradientStop(.8), od.GradientStop(.2))),
        lambda: od.GradientPaint(stops=(od.GradientStop(0),)), lambda: od.GradientPaint(opacity=1.01),
        lambda: od.GradientPaint(spread='drawingml'), lambda: od.GradientPaint(interpolation='guess'),
        lambda: od.LinearGradient('relative', od.Point2D(1, 1), od.Point2D(1, 1)),
        lambda: od.RadialGradient('points', od.Point2D(1, 1), 0),
        lambda: od.BackgroundPaint('none', gradient=od.GradientPaint()),
        lambda: od.BackgroundPaint('solid'),
        lambda: od.GradientPaint(linear=paint().gradient.linear,
                                 radial=od.RadialGradient('relative', od.Point2D(.5, .5), 1)),
    ):
        failures.append(rejected(operation))
    for raw in ({'format': od.BACKGROUND_PROPERTY, 'version': 2, 'data': {}},
                {'format': od.BACKGROUND_PROPERTY, 'version': True, 'data': {}},
                {'format': od.BACKGROUND_PROPERTY, 'version': 1, 'data': {'kind': 'solid'}}):
        bad = fixture()
        bad.sections[0].properties[od.BACKGROUND_PROPERTY] = raw
        failures.append(rejected(lambda: od.document_to_json(bad), 'sections[0].properties'))
    section = od.Section(properties={od.BACKGROUND_PROPERTY: {'opaque': [1]}})
    before, mapping = deepcopy(section.properties), section.properties
    assert od.get_section_background(section) is None
    failures.append(rejected(lambda: od.set_section_background(section, paint()), 'opaque'))
    assert section.properties is mapping and section.properties == before
    section = fixture().sections[0]
    before, mapping = deepcopy(section.properties), section.properties
    cyclic = paint()
    cyclic.extra['cycle'] = cyclic.extra
    failures.append(rejected(lambda: od.set_section_background(section, cyclic), 'cyclic'))
    assert section.properties is mapping and section.properties == before
    results.append('invalid ranges, roles, geometry, versions, opaque collision and cycle refuse; failed setters are atomic')

    document = fixture()
    wire = od.document_to_json(document)
    thresholds = {}
    for quota in ('max_nodes', 'max_depth', 'max_bytes'):
        thresholds[quota] = {}
        for mode in ('transport', 'section-setter', 'page-with', 'walk'):
            def accepted(value):
                limit = replace(od.DocumentLimits(), **{quota: value})
                section = document.sections[0]
                page = od.get_integration(document).pages[0]
                mapping, before = section.properties, od.document_to_json(document)
                try:
                    if mode == 'transport':
                        od.document_to_json(document, limits=limit)
                        od.document_from_json(wire, limits=limit)
                    elif mode == 'section-setter':
                        od.set_section_background(section, paint(), limits=limit)
                    elif mode == 'page-with':
                        od.with_page_background(page, od.get_page_background(page), limits=limit)
                    else:
                        list(od.iter_backgrounds(document, limits=limit))
                except od.ArtifactLimitError:
                    assert section.properties is mapping and od.document_to_json(document) == before
                    return False
                assert od.document_to_json(document) == before
                return True

            low, high = (0, 128) if quota == 'max_depth' else (0, max(10000, len(wire.encode())*2))
            assert accepted(high)
            while low+1 < high:
                middle = (low+high)//2
                if accepted(middle):
                    high = middle
                else:
                    low = middle
            assert accepted(high) and not accepted(high-1)
            thresholds[quota][mode] = high
    results.append('exact paired transport, section setter, page copy and walk node/depth/byte boundaries; one-below is atomic')
    return results, failures, thresholds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.candidate/'provenance.json').read_text(encoding='utf-8'))
    wheel = args.candidate/'opendoc_model-0.19.0-py3-none-any.whl'
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == WHEEL_SHA256
    installed = Path(od.__file__).parent.parent
    with ZipFile(wheel) as archive:
        for relative, expected in manifest['source_files'].items():
            assert hashlib.sha256(archive.read(relative)).hexdigest() == expected
            assert hashlib.sha256((installed/relative).read_bytes()).hexdigest() == expected
        sources = {name for name in archive.namelist() if name.startswith('opendoc_model/') and name.endswith('.py')}
        assert sources == {name for name in manifest['source_files'] if name.endswith('.py')}
    packages = sorted(item.metadata['Name'] for item in distributions())
    assert packages == ['opendoc-model'], packages
    scenarios, failures, thresholds = checks()
    assert not {'opendoc_formats', 'lxml', 'docx', 'pptx', 'PIL', 'fontTools', 'pymupdf', 'pypdf', 'bs4'} & sys.modules.keys()
    args.output.write_text(json.dumps({
        'contract': 'C-BACKGROUND-GRADIENT-01', 'status': 'isolated public API passed; production adoption pending',
        'candidate_wheel_sha256': WHEEL_SHA256, 'source_file_count': len(manifest['source_files']),
        'consumer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'python': sys.version.split()[0], 'installed_distributions': packages, 'checks': scenarios,
        'located_refusals': failures, 'exact_quota_boundaries': thresholds,
        'scope': 'Neutral DTO/codec acceptance only; no native parsing, gradient projection or rendering claimed.',
    }, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'{len(scenarios)} consumer scenarios passed; {args.output}')


if __name__ == '__main__':
    main()
