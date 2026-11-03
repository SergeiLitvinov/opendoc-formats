"""Native editable gradient backgrounds: original source, public cycles and authored stop/geometry edit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def prepare(root: Path) -> None:
    from lxml import etree
    from opendoc_model import ColorValue, document_from_json, document_to_json
    from pptx import Presentation

    from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document
    from opendoc_formats.ooxml.pptx_gradient import KEY, A
    from tests.readers.test_pptx_background_gradients import CASES, P, own_gradient

    root.mkdir(parents=True, exist_ok=False)
    files = []
    for case in CASES:
        folder = root/case
        folder.mkdir()
        source = own_gradient(folder, case)
        files.append({'file': source.relative_to(root).as_posix(), 'case': case, 'route': 'original'})
        model = read_document(source).document
        for route in ('source', 'rebuild'):
            current = model
            for cycle in (1, 2):
                target = folder/f'{route}-{cycle}.pptx'
                current = document_from_json(document_to_json(current))
                report = write_document(current, target, options=ExportOptions(pptx_profile=PptxProfile(layout=route)))
                assert report.success, report.issues
                files.append({'file': target.relative_to(root).as_posix(), 'case': case, 'route': route, 'cycle': cycle})
                current = read_document(target).document
        if case == 'linear':
            reference = folder/'authored-edit.pptx'
            presentation = Presentation(source)
            gradient = presentation.slides[0]._element.find(P+'cSld/'+P+'bg/'+P+'bgPr/'+A+'gradFill')
            values = gradient.find(A+'gsLst')
            values.remove(values[1])
            values[0][0].set('val', '22AA66')
            values[1].set('pos', '60000')
            gradient.find(A+'lin').set('ang', '5400000')
            presentation.save(reference)
            files.append({'file': reference.relative_to(root).as_posix(), 'case': case, 'route': 'edit-reference'})
            current = document_from_json(document_to_json(model))
            properties = current.sections[0].properties
            stops = properties['background_gradient_colors']
            stops.pop(1)
            stops[0]['color'] = ColorValue.from_hex('#22AA66').to_dict()
            stops[1]['position'] = .6
            native = etree.fromstring(properties[KEY]['xml'].encode())
            native.find(A+'lin').set('ang', '5400000')
            properties[KEY]['xml'] = etree.tostring(native, encoding='unicode')
            for cycle in (1, 2):
                target = folder/f'edited-{cycle}.pptx'
                report = write_document(current, target, options=ExportOptions(pptx_profile=PptxProfile(layout='rebuild')))
                assert report.success, report.issues
                files.append({'file': target.relative_to(root).as_posix(), 'case': case, 'route': 'rebuild-edit', 'cycle': cycle})
                current = document_from_json(document_to_json(read_document(target).document))
    (root/'manifest.json').write_text(json.dumps({'files': files}, indent=2)+'\n', encoding='utf-8')


def check(root: Path, output: Path) -> None:
    import pymupdf

    from tools.pptx_background_acceptance import compare

    controls = []
    for item in json.loads((root/'manifest.json').read_text(encoding='utf-8'))['files']:
        if item['route'] not in ('original', 'edit-reference'):
            continue
        with pymupdf.open((root/item['file']).with_suffix('.pdf')) as document:
            pixmap = document[0].get_pixmap(alpha=False)
            samples = [pixmap.pixel(pixmap.width*x//8, pixmap.height*y//8)[:3] for x in range(1, 8) for y in range(3, 8)]
            variation = max(max(rgb[channel] for rgb in samples)-min(rgb[channel] for rgb in samples) for channel in range(3))
            assert variation > 32, 'Native control lacks a visible gradient: '+item['file']
            controls.append({'file': item['file'], 'sample_channel_range': variation})
    compare(root, output, scope='Finite editable DrawingML background gradients and authoritative stop/geometry edits',
            limitations=['Native format hint, not a neutral cross-format gradient API',
                         'Unsupported geometry/effects and arbitrary gradient precision remain unaccepted'])
    report = json.loads(output.read_text(encoding='utf-8'))
    report['gradient_controls'] = controls
    output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'check'))
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.root)
    elif args.output:
        check(args.root, args.output)
    else:
        parser.error('check requires --output')


if __name__ == '__main__':
    main()
