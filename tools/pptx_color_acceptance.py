"""Native PowerPoint control of text, shape and chart DrawingML tint/shade materialization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

EXPECTED = {'shade': '#0C1E30', 'tint': '#E1E2E4', 'shade-tint': '#BCBEC0', 'tint-shade': '#8A8C90'}


def controls(root: Path, expected: dict[str, str] | None = None) -> list[dict]:
    from collections import Counter

    import pymupdf

    results = []
    for name, color in (EXPECTED if expected is None else expected).items():
        rgb = bytes.fromhex(color[1:])
        for kind in ('shape', 'chart'):
            case = name+'-'+kind
            with pymupdf.open(root/case/'original.pdf') as document:
                samples = document[0].get_pixmap(alpha=False).samples
                counts = Counter(zip(samples[::3], samples[1::3], samples[2::3]))
                count = sum(amount for value, amount in counts.items() if max(abs(value[i]-rgb[i]) for i in range(3)) <= 1)
                assert count > 100, 'Native original lacks its color control: '+case
                results.append({'case': case, 'expected_rgb': color, 'matching_pixels': count,
                                'maximum_channel_rounding': 1})
    return results


def prepare(root: Path, cases: list[tuple[str, list[tuple[str, int]]]] | None = None) -> None:
    from opendoc_model import document_from_json, document_to_json

    from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document
    from tests.readers.test_pptx_color_modifiers import CASES, own_colors

    root.mkdir(parents=True, exist_ok=False)
    files = []
    for name, modifiers in (CASES if cases is None else cases):
        for chart in (False, True):
            case = name + ('-chart' if chart else '-shape')
            folder = root / case
            folder.mkdir()
            source = own_colors(folder, modifiers, chart=chart)
            files.append({'file': source.relative_to(root).as_posix(), 'case': case, 'route': 'original',
                          'expected_background': '#FFFFFF'})
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
    (root / 'manifest.json').write_text(json.dumps({'files': files}, indent=2)+'\n', encoding='utf-8')


def main() -> None:
    from tools.pptx_background_acceptance import compare

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'check'))
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.root)
    elif args.output:
        color_controls = controls(args.root)
        compare(args.root, args.output, scope='DrawingML tint/shade on text, shapes and chart series, two JSON cycles',
                limitations=['Finite color profile, not full chart/theme/shaping compatibility',
                             'Luminance is outside this corpus; see separate luminance acceptance',
                             'Other unaccepted transforms require separate native QA'])
        evidence = json.loads(args.output.read_text(encoding='utf-8'))
        evidence['source_color_controls'] = color_controls
        args.output.write_text(json.dumps(evidence, indent=2)+'\n', encoding='utf-8')
    else:
        parser.error('check requires --output')


if __name__ == '__main__':
    main()
