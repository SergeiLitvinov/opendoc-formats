"""Isolated public-API acceptance of an unpublished C-OUTLINE-LABEL-01 wheel."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from importlib.metadata import distributions
from pathlib import Path
from zipfile import ZipFile

import opendoc_model as od

WHEEL_SHA256 = '06f4ab1202fc534b7d3f1fc808eb3c7016d427f0ed6b363002e62508c2e977c9'


def fixture(prefix='Short', body='Long visible heading'):
    heading = od.Paragraph([od.TextRun(body)])
    od.set_heading(heading, od.Heading(1))
    od.set_anchor(heading, od.Anchor('heading'))
    document = od.DocumentModel([od.Section([heading])],
        resources={'font': od.Resource('font', od.ResourceKind.FONT, 'font/ttf', (prefix + ' opaque font').encode())},
        styles={'label-style': od.TextStyle(italic=prefix == 'Short')})
    run = od.TextRun(prefix + ' ', od.TextStyle(bold=True, properties={'base_style_id': 'label-style'}),
                     provenance=od.Provenance('latex', object_id='short-title-run'))
    od.set_font_reference(run.style, od.FontReference('font', 0))
    od.set_internal_link(run, od.InternalLink('heading'))
    formula = od.Formula('x^2', od.FormulaFormat.LATEX, fallback_text='x²')
    title = prefix + ' x²'
    main = od.OutlineEntry('main', title, 0, target=od.OutlineTarget('anchor', 'heading'),
        label=od.OutlineLabel(title, (run, formula), extra={'future': {'values': [1]}}), extra={'entry-extra': [2]})
    alternate = od.OutlineEntry('alternate', 'Alternative', 1, target=od.OutlineTarget('anchor', 'heading'),
        label=od.OutlineLabel('Alternative', (od.TextRun('Alternative', od.TextStyle(underline=True)),)))
    empty = od.OutlineEntry('empty', '', 2, label=od.OutlineLabel(''))
    plain = od.OutlineEntry('plain', 'Plain', 3)
    child = od.OutlineEntry('child', 'Child', 0, parent_id='main', target=od.OutlineTarget('anchor', 'heading'))
    od.set_outline(document, od.Outline((main, alternate, empty, plain, child), extra={'outline-extra': [3]}))
    return document


def entries(document):
    return {entry.id: entry for entry in od.get_outline(document).entries}


def cycles(document):
    before = od.document_to_dict(document)
    for _ in range(2):
        document = od.document_from_json(od.document_to_json(document))
        assert od.document_to_dict(document) == before
    return document


def refusal(document, action, match=None):
    before, metadata = od.document_to_json(document), document.metadata
    try:
        action()
    except ValueError as error:
        assert not isinstance(error, od.ArtifactLimitError), 'Invalid input misclassified as quota failure'
        assert match is None or match in str(error), str(error)
        assert od.document_to_json(document) == before and document.metadata is metadata
        return str(error)
    raise AssertionError('Invalid outline unexpectedly accepted')


def checks():
    results = []
    original = fixture()
    document = cycles(original)
    main = entries(document)['main']
    assert [type(node).__name__ for node in main.label.content] == ['TextRun', 'Formula']
    assert main.label.content[0].style.bold and main.label.content[1].fallback_text == 'x²'
    assert main.label.content[0].provenance.object_id == 'short-title-run'
    assert od.get_font_reference(main.label.content[0].style) == od.FontReference('font', 0)
    assert od.get_internal_link(main.label.content[0]).target_id == 'heading'
    assert od.extract_text(document) == 'Long visible heading'
    assert [loc.node.text for loc in od.walk_model(document) if isinstance(loc.node, od.TextRun)] == ['Long visible heading']
    assert od.get_heading(document.sections[0].blocks[0]) == od.Heading(1)
    rows = list(od.iter_outline_inlines(document))
    assert [(row.entry_id, row.index) for row in rows] == [('main', 0), ('main', 1), ('alternate', 0)]
    assert all('label.content' in row.path for row in rows)
    assert any('label.content' in row.path for row in od.iter_font_references(document))
    results.append('two JSON cycles retain styled/math labels, provenance, FONT/link refs; '
                   'separate label walk never adds body text')

    rows[0].node.text = 'Edited detached node'
    main.label.extra['future']['values'].append(9)
    main.extra['entry-extra'].append(9)
    assert entries(document)['main'].label.content[0].text == 'Short '
    assert entries(document)['main'].label.extra['future']['values'] == [1]
    assert entries(document)['main'].extra['entry-extra'] == [2]
    assert entries(original)['main'].label.extra['future']['values'] == [1]
    values = entries(document)
    assert values['empty'].label.content == () and values['plain'].label is None
    assert values['child'].parent_id == 'main'
    assert values['main'].target == values['alternate'].target
    results.append('unknown fields and detached getters are independent; '
                   'empty/absent labels and multiple labels per heading stay distinct')

    document = fixture()
    entry = entries(document)['main']
    refusal(document, lambda: od.set_outline(document, od.Outline((replace(entry, title='Edited'),))), 'label.title')
    replacement = replace(entry, title='Edited', label=od.OutlineLabel('Edited',
        (od.TextRun('Edited', od.TextStyle(italic=True)),)))
    od.set_outline(document, od.Outline((replacement,)))
    assert entries(cycles(document))['main'].label.content[0].style.italic
    od.set_outline(document, od.Outline((replace(replacement, label=None),)))
    assert entries(cycles(document))['main'].label is None and od.extract_text(document) == 'Long visible heading'
    assert '"label"' not in od.document_to_json(document)
    results.append('plain-title mismatch refuses atomically; explicit rich update/removal remains authoritative '
                   'and legacy plain wire omits label')

    failures = {}
    for case in ('paragraph', 'display', 'no-fallback', 'missing-font', 'wrong-font-kind', 'missing-link',
                 'missing-target', 'missing-style', 'private-anchor', 'cycle'):
        document = fixture()
        entry = entries(document)['main']
        node = od.TextRun('Own')
        if case == 'paragraph':
            node = od.Paragraph([node])
        elif case == 'display':
            node = od.Formula('x', od.FormulaFormat.LATEX, fallback_text='x', display=True)
        elif case == 'no-fallback':
            node = od.Formula('x', od.FormulaFormat.LATEX)
        elif case == 'missing-font':
            od.set_font_reference(node.style, od.FontReference('missing'))
        elif case == 'wrong-font-kind':
            document.resources['attachment'] = od.Resource('attachment', od.ResourceKind.ATTACHMENT,
                                                          'application/octet-stream', b'Own attachment')
            od.set_font_reference(node.style, od.FontReference('attachment'))
        elif case == 'missing-link':
            od.set_internal_link(node, od.InternalLink('missing'))
        elif case == 'missing-style':
            node.style.properties['base_style_id'] = 'missing'
        elif case == 'private-anchor':
            od.set_anchor(node, od.Anchor('undeclared-label-owner'))
        elif case == 'cycle':
            node.properties['cycle'] = node.properties
        bad = replace(entry, label=od.OutlineLabel(entry.title, (node,)))
        if case == 'missing-target':
            bad = replace(entry, target=od.OutlineTarget('anchor', 'missing'))
        failures[case] = refusal(document, lambda: od.set_outline(document, od.Outline((bad,))))
    results.append('ten invalid inline/reference/cyclic profiles refuse without changing destination metadata or wire')

    first, second = fixture(), fixture('Other', 'Second visible heading')
    combined = cycles(od.merge_documents([first, second], conflicts='rename', metadata_conflicts='keep_last').document)
    entry = entries(combined)['main']
    assert od.resolve_anchor(combined, entry.target.target_id).node.plain_text == 'Second visible heading'
    assert od.get_internal_link(entry.label.content[0]).target_id == entry.target.target_id
    resource = od.get_font_reference(entry.label.content[0].style).resource_id
    assert combined.resources[resource].data == second.resources['font'].data
    style = entry.label.content[0].style.properties['base_style_id']
    assert combined.styles[style] == second.styles['label-style']
    extracted = cycles(od.extract_document(first, od.resolve_anchor(first, 'heading')))
    assert set(extracted.resources) == {'font'} and set(extracted.styles) == {'label-style'}
    assert od.get_outline(extracted) == od.get_outline(first)
    assert entries(first)['main'].target.target_id == 'heading'
    results.append('merge with explicit keep_last remaps body targets, internal label links, FONT and named styles; '
                   'extract closes label dependencies independently')

    document = fixture()
    wire = od.document_to_json(document)
    thresholds = {}
    for quota in ('max_nodes', 'max_depth', 'max_bytes', 'max_embedded_bytes'):
        thresholds[quota] = {}
        for mode in ('transport', 'setter'):
            def accepted(value):
                selected = replace(od.DocumentLimits(), **{quota: value})
                before, metadata = od.document_to_json(document), document.metadata
                try:
                    if mode == 'transport':
                        od.document_to_json(document, limits=selected)
                        od.document_from_json(wire, limits=selected)
                    else:
                        od.set_outline(document, od.get_outline(document), limits=selected)
                except od.ArtifactLimitError:
                    assert od.document_to_json(document) == before and document.metadata is metadata
                    return False
                return True

            low, high = (1, 128) if quota == 'max_depth' else (0, max(10000, len(wire.encode()) * 2))
            assert accepted(high)
            while low + 1 < high:
                middle = (low + high) // 2
                if accepted(middle):
                    high = middle
                else:
                    low = middle
            assert accepted(high) and not accepted(high - 1)
            thresholds[quota][mode] = high
    assert od.document_to_json(document) == wire
    results.append('node/depth/byte/embedded quotas: exact paired transport and setter boundaries; one-below refusal is atomic')
    return results, failures, thresholds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads((args.candidate / 'provenance.json').read_text(encoding='utf-8'))
    wheel = args.candidate / 'opendoc_model-0.19.0-py3-none-any.whl'
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == WHEEL_SHA256
    installed = Path(od.__file__).parent.parent
    with ZipFile(wheel) as archive:
        for relative, expected in manifest['source_files'].items():
            assert hashlib.sha256(archive.read(relative)).hexdigest() == expected
            assert hashlib.sha256((installed / relative).read_bytes()).hexdigest() == expected
        sources = {name for name in archive.namelist() if name.startswith('opendoc_model/') and name.endswith('.py')}
        assert sources == {name for name in manifest['source_files'] if name.endswith('.py')}
    packages = sorted(item.metadata['Name'] for item in distributions())
    assert packages == ['opendoc-model'], packages
    scenarios, failures, thresholds = checks()
    assert not {'opendoc_formats', 'docx', 'pptx', 'lxml', 'PIL', 'fontTools', 'pymupdf', 'pypdf', 'bs4'} & sys.modules.keys()
    args.output.write_text(json.dumps({
        'contract': 'C-OUTLINE-LABEL-01', 'status': 'isolated public API passed; production adoption pending',
        'candidate_wheel_sha256': WHEEL_SHA256, 'source_file_count': len(manifest['source_files']),
        'consumer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'python': sys.version.split()[0], 'installed_distributions': packages, 'checks': scenarios,
        'located_refusals': failures, 'exact_quota_boundaries': thresholds,
        'scope': ('Neutral DTO/codec/reference acceptance; FONT bytes are opaque; '
                  'no TeX parsing, rendering or native export claimed.'),
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{len(scenarios)} consumer scenarios passed; {args.output}')


if __name__ == '__main__':
    main()
