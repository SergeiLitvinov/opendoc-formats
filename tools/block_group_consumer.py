"""Independent public-API consumer of an unpublished C-BLOCK-GROUP-01 wheel.

Run only in a separate environment; this is not production adoption or EPUB QA.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from dataclasses import replace
from importlib.metadata import distributions
from pathlib import Path
from zipfile import ZipFile

import opendoc_model as od


def paragraph(text, anchor=None, item=None):
    value = od.Paragraph([od.TextRun(text)])
    if anchor:
        od.set_anchor(value, od.Anchor(anchor))
    if item:
        od.set_list_item(value, item)
    return value


def fixture():
    """Model counterpart of one quoted compound item; no format code in SDK."""
    owner = paragraph('Start α', 'item', od.ListItem('outer', start=4))
    cell = paragraph('Editable cell', 'cell')
    table = od.Table([od.TableRow([od.TableCell([cell])])])
    tail = paragraph('End β', 'tail', od.ListItem('outer', start=4, continuation_of='item'))
    nested = paragraph('Nested', 'nested', od.ListItem('inner', parent_id='item', restart=8))
    inner = od.BlockGroup([nested], list_owner=od.BlockGroupListOwner('nested'))
    item = od.BlockGroup([owner, table, tail, inner], list_owner=od.BlockGroupListOwner('item'))
    od.set_anchor(item, od.Anchor('compound'))
    quote = od.BlockGroup([item], role='quotation', properties={'consumer': {'scopes': [1]}})
    od.set_anchor(quote, od.Anchor('quote'))
    quote.provenance = od.Provenance('epub', package_part='OPS/chapter.xhtml', object_id='quote')
    quote.extensions['future-scope'] = {'values': [2]}
    item.list_owner.extensions['future-link'] = [3]
    link = paragraph('Go to quote')
    od.set_internal_link(link.content[0], od.InternalLink('quote'))
    following = paragraph('Next', 'next', od.ListItem('outer', start=4))
    return od.DocumentModel([od.Section([quote, following, link])])


def cycles(document):
    wire = od.document_to_dict(document)
    for _ in range(2):
        document = od.document_from_json(od.document_to_json(document))
        assert od.document_to_dict(document) == wire
    return document


def refusal(document, action, match):
    before = copy.deepcopy(document)
    try:
        action()
    except ValueError as error:
        assert match in str(error), str(error)
        assert document == before, 'Rejected operation changed input'
        return str(error)
    raise AssertionError(f'Expected refusal: {match}')


def checks():
    results = []
    original = fixture()
    document = cycles(original)
    quote = document.sections[0].blocks[0]
    group = quote.children[0]
    assert [type(child).__name__ for child in group.children] == ['Paragraph', 'Table', 'Paragraph', 'BlockGroup']
    assert od.extract_text(document) == 'Start α\nEditable cell\nEnd β\nNested\nNext\nGo to quote'
    assert [entry.number for entry in od.iter_list_numbers(document)] == [4, None, 8, 5]
    for identifier in ('quote', 'compound', 'item', 'cell', 'tail', 'nested', 'next'):
        assert od.get_anchor(od.resolve_anchor(document, identifier).node).id == identifier
    assert od.resolve_anchor(document, 'quote').node is quote
    assert od.get_internal_link(document.sections[0].blocks[2].content[0]).target_id == 'quote'
    assert od.resolve_anchor(document, 'cell').path.endswith('.children[1].rows[0].cells[0].blocks[0]')
    results.append('two JSON cycles: ordered table/paragraph/group scopes, independent anchors, one list number')

    quote.properties['consumer']['scopes'].append(9)
    quote.extensions['future-scope']['values'].append(9)
    group.list_owner.extensions['future-link'].append(9)
    old = original.sections[0].blocks[0]
    assert old.properties['consumer']['scopes'] == [1]
    assert old.extensions['future-scope']['values'] == [2]
    assert old.children[0].list_owner.extensions['future-link'] == [3]
    results.append('unknown group and owner fields survive codec without mutable aliasing')

    document = cycles(original)
    cell = od.resolve_anchor(document, 'cell').node
    cell.content[0].text = 'Edited γ'
    edited = cycles(document)
    assert od.resolve_anchor(edited, 'cell').node.plain_text == 'Edited γ'
    assert od.resolve_anchor(original, 'cell').node.plain_text == 'Editable cell'
    assert [entry.number for entry in od.iter_list_numbers(edited)] == [4, None, 8, 5]
    results.append('cell edit preserves outer quotation, list continuation and nested numbering')

    for target in ('missing', 'quote', 'tail', 'next', 'cell', 'nested'):
        bad = fixture()
        bad.sections[0].blocks[0].children[0].list_owner = od.BlockGroupListOwner(target)
        refusal(bad, lambda: od.document_to_json(bad), 'list_owner.paragraph_id')
    document = fixture()
    refusal(document, lambda: od.remove_node(document, od.resolve_anchor(document, 'item')), 'list_owner')
    od.remove_node(document, od.resolve_anchor(document, 'compound'))
    assert [entry.number for entry in od.iter_list_numbers(cycles(document))] == [4]
    results.append('six invalid owner bindings and dangling-owner removal refuse atomically; whole-item removal works')

    for field, value in (('role', 'html'), ('children', [od.TextRun('inline')]), ('list_owner', 'item')):
        bad = fixture()
        setattr(bad.sections[0].blocks[0], field, value)
        refusal(bad, lambda: od.document_to_json(bad), field)
    bad = fixture()
    bad.sections[0].blocks[0].children.append(bad.sections[0].blocks[0])
    # Cyclic dataclass equality is unsuitable for the generic atomicity check.
    try:
        od.document_to_json(bad)
    except ValueError as error:
        assert 'cyclic' in str(error)
    else:
        raise AssertionError('Cycle accepted')
    results.append('invalid role, inline child, untyped binding and actual cycle refuse explicitly')

    empty = od.BlockGroup()
    reused = od.BlockGroup([paragraph('Repeated')], role='quotation')
    wrapper = od.BlockGroup([reused, empty, reused])
    document = od.DocumentModel([od.Section([od.Table([od.TableRow([od.TableCell([wrapper])])])])])
    paths = [location.path for location in od.walk_model(document) if location.node is reused]
    assert len(paths) == 2 and paths[0] != paths[1]
    assert od.extract_text(cycles(document)) == 'Repeated\n\nRepeated'
    results.append('nested cell groups, empty scope and repeated occurrences retain order and separate paths')

    merged = cycles(od.merge_documents([original, original], conflicts='rename').document)
    second = merged.sections[1].blocks[0]
    assert od.get_anchor(second).id == 'quote~2'
    assert second.children[0].list_owner.paragraph_id == 'item~2'
    assert second.children[0].children[3].list_owner.paragraph_id == 'nested~2'
    assert od.get_internal_link(merged.sections[1].blocks[2].content[0]).target_id == 'quote~2'
    assert od.get_anchor(original.sections[0].blocks[0]).id == 'quote'
    extracted = cycles(od.extract_document(original, od.resolve_anchor(original, 'cell')))
    assert not extracted.validate()
    assert od.resolve_anchor(extracted, 'item').node.plain_text == 'Start α'
    results.append('merge remaps compound owners and anchors; cell extraction closes owner dependencies')

    baseline = od.document_to_json(original)
    quotas = {}
    for quota in ('max_nodes', 'max_depth', 'max_bytes'):
        def accepted(maximum):
            limit = replace(od.DocumentLimits(), **{quota: maximum})
            try:
                od.document_to_json(original, limits=limit)
                od.document_from_json(baseline, limits=limit)
            except od.ArtifactLimitError:
                return False
            return True

        low, high = (1, 128) if quota == 'max_depth' else (0, max(10000, len(baseline.encode()) * 2))
        assert accepted(high)
        while low + 1 < high:
            middle = (low + high) // 2
            if accepted(middle):
                high = middle
            else:
                low = middle
        assert accepted(high) and not accepted(high - 1)
        quotas[quota] = high
    assert od.document_to_json(original) == baseline
    results.append('selected node/depth/byte quotas: exact paired encode/decode boundary and one-below refusal')
    return results, quotas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    provenance = json.loads((args.candidate / 'provenance.json').read_text(encoding='utf-8'))
    wheel = args.candidate / 'opendoc_model-0.19.0-py3-none-any.whl'
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert digest == '5fac0c362b5f343f59984f437f135cba9bb3fd907abfce823c9b8b1cecbcc1be'
    installed = Path(od.__file__).parent.parent
    with ZipFile(wheel) as archive:
        for relative, expected in provenance['source_files'].items():
            assert hashlib.sha256(archive.read(relative)).hexdigest() == expected
            assert hashlib.sha256((installed / relative).read_bytes()).hexdigest() == expected
    packages = sorted(item.metadata['Name'] for item in distributions())
    assert packages == ['opendoc-model'], packages
    results, quotas = checks()
    args.output.write_text(json.dumps({
        'contract': 'C-BLOCK-GROUP-01', 'status': 'isolated public-API consumer passed; production adoption pending',
        'candidate_wheel_sha256': digest, 'source_file_count': len(provenance['source_files']),
        'consumer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'python': sys.version.split()[0], 'installed_distributions': packages,
        'checks': results, 'paired_transport_quota_boundaries': quotas,
        'scope': 'Neutral API only; no EPUB/HTML rendering, source mapping or production support claimed.',
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'{len(results)} consumer scenarios passed; {args.output}')


if __name__ == '__main__':
    main()
