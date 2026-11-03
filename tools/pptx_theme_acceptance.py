"""Effective master themes and consumer overrides: public cycles and native page acceptance."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def prepare(root: Path) -> None:
    from opendoc_model import document_from_json, document_to_json

    from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document
    from tests.readers.test_pptx_theme_colors import CASES, own_theme

    root.mkdir(parents=True, exist_ok=False)
    files = []
    for name, expected in CASES:
        for chart in (False, True):
            if name == 'inherited-master' and chart:
                continue
            case = name+('-chart' if chart else '-shape')
            folder = root / case
            folder.mkdir()
            source = own_theme(folder, name, chart=chart)
            files.append({'file': source.relative_to(root).as_posix(), 'case': case, 'route': 'original',
                          'expected_background': '#FFFFFF', 'expected_object_color': expected})
            model = read_document(source).document
            for route in ('source', 'rebuild'):
                current = model
                for cycle in (1, 2):
                    target = folder / f'{route}-{cycle}.pptx'
                    current = document_from_json(document_to_json(current))
                    report = write_document(current, target, options=ExportOptions(pptx_profile=PptxProfile(layout=route)))
                    assert report.success, report.issues
                    files.append({'file': target.relative_to(root).as_posix(), 'case': case, 'route': route, 'cycle': cycle})
                    current = read_document(target).document
    (root/'manifest.json').write_text(json.dumps({'files': files}, indent=2)+'\n', encoding='utf-8')


def check(root: Path, output: Path) -> None:
    import pymupdf

    from tools.pptx_background_acceptance import compare

    controls = []
    for item in json.loads((root/'manifest.json').read_text(encoding='utf-8'))['files']:
        if item['route'] != 'original':
            continue
        rgb = bytes.fromhex(item['expected_object_color'][1:])
        with pymupdf.open((root/item['file']).with_suffix('.pdf')) as document:
            samples = document[0].get_pixmap(alpha=False).samples
            counts = Counter(zip(samples[::3], samples[1::3], samples[2::3]))
            amount = sum(count for color, count in counts.items() if max(abs(color[i]-rgb[i]) for i in range(3)) <= 1)
            assert amount > 100, 'Original theme color differs: '+item['case']
            controls.append({'case': item['case'], 'expected_rgb': item['expected_object_color'],
                             'matching_pixels': amount, 'maximum_channel_rounding': 1})
    compare(root, output, scope='Actual master themes, layout/slide theme overrides and color maps; text, shapes, series fill',
            limitations=['Finite palette projection, not editable shared theme hierarchy',
                         'Chart-local overrides are outside this corpus; see separate chart-theme acceptance',
                         'Unsupported color schemes and complete theme/style cascade remain unaccepted'])
    report = json.loads(output.read_text(encoding='utf-8'))
    report['source_color_controls'] = controls
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
