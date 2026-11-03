"""Finite chart-local palette acceptance through public source/rebuild cycles and native PowerPoint PDF."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def prepare(root: Path) -> None:
    from opendoc_model import document_from_json, document_to_json

    from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document
    from tests.readers.test_pptx_chart_themes import CASES, own_chart_theme

    root.mkdir(parents=True, exist_ok=False)
    files = []
    for case, _, colors in CASES:
        folder = root/case
        folder.mkdir()
        source = own_chart_theme(folder, case)
        files.append({'file': source.relative_to(root).as_posix(), 'case': case, 'route': 'original',
                      'expected_background': '#FFFFFF', 'expected_chart_colors': colors})
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
    (root/'manifest.json').write_text(json.dumps({'files': files}, indent=2)+'\n', encoding='utf-8')


def check(root: Path, output: Path) -> None:
    import pymupdf

    from tools.pptx_background_acceptance import compare

    controls = []
    for item in json.loads((root/'manifest.json').read_text(encoding='utf-8'))['files']:
        if item['route'] != 'original':
            continue
        with pymupdf.open((root/item['file']).with_suffix('.pdf')) as document:
            data = document[0].get_pixmap(alpha=False).samples
            counts = Counter(zip(data[::3], data[1::3], data[2::3]))
            for color in item['expected_chart_colors']:
                rgb = bytes.fromhex(color[1:])
                amount = sum(count for value, count in counts.items() if max(abs(value[i]-rgb[i]) for i in range(3)) <= 1)
                assert amount > 100, 'Native chart color differs: '+item['case']
                controls.append({'case': item['case'], 'expected_rgb': color, 'matching_pixels': amount,
                                 'maximum_channel_rounding': 1})
    compare(root, output, scope='Chart-local themeOverride and clrMapOvr with consumer inheritance and isolated chart contexts',
            limitations=['Finite series-fill palette profile, not complete chart compatibility',
                         'Font/effect/style overrides, malformed mappings and complete shared-theme edits remain unaccepted'])
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
