"""Own style-matrix backgrounds, two public cycles and native full-page comparison."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def prepare(root: Path) -> None:
    import opendoc_model as od
    from pptx import Presentation
    from pptx.dml.color import RGBColor

    from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document
    from tests.readers.test_pptx_background_styles import own_background

    root.mkdir(parents=True, exist_ok=False)
    cases = [('master-matrix', {'owner': 'master'}, '#226688'),
             ('layout-placeholder', {'owner': 'layout', 'index': 1002}, '#A06020'),
             ('slide-fill-list', {'owner': 'slide', 'index': 2}, '#A06020'),
             ('layout-color-map', {'index': 1002, 'mapped': True}, '#4060A0'),
             ('composed-shade', {'index': 1002, 'shade': True}, '#54300C'),
             ('explicit-none', {'owner': 'slide', 'index': 1000}, '#FFFFFF')]
    files = []
    for name, options, expected in cases:
        folder = root / name
        folder.mkdir()
        source = own_background(folder, **options)
        files.append({'file': source.relative_to(root).as_posix(), 'case': name, 'route': 'original',
                      'expected_background': expected})
        original = source.read_bytes()
        model = read_document(source).document
        for route in ('source', 'rebuild'):
            current = model
            for cycle in (1, 2):
                current = od.document_from_json(od.document_to_json(current))
                target = folder / f'{route}-{cycle}.pptx'
                report = write_document(current, target, options=ExportOptions(pptx_profile=PptxProfile(layout=route)))
                assert report.success, report.issues
                files.append({'file': target.relative_to(root).as_posix(), 'case': name, 'route': route, 'cycle': cycle})
                current = read_document(target).document
        if name == 'master-matrix':
            reference = folder / 'authored-edit.pptx'
            presentation = Presentation(source)
            presentation.slides[0].background.fill.solid()
            presentation.slides[0].background.fill.fore_color.rgb = RGBColor.from_string('8844AA')
            presentation.save(reference)
            files.append({'file': reference.relative_to(root).as_posix(), 'case': name, 'route': 'edit-reference',
                          'expected_background': '#8844AA'})
            current = od.document_from_json(od.document_to_json(model))
            current.sections[0].properties['background_fill'] = '#8844AA'
            current.sections[0].properties['background_color'] = od.ColorValue.from_hex('#8844AA').to_dict()
            for cycle in (1, 2):
                target = folder / f'edit-{cycle}.pptx'
                report = write_document(current, target, options=ExportOptions(pptx_profile=PptxProfile(layout='rebuild')))
                assert report.success, report.issues
                files.append({'file': target.relative_to(root).as_posix(), 'case': name, 'route': 'rebuild-edit', 'cycle': cycle})
                current = od.document_from_json(od.document_to_json(read_document(target).document))
        assert source.read_bytes() == original
    (root / 'manifest.json').write_text(json.dumps({'files': files}, indent=2)+'\n', encoding='utf-8')


def compare(root: Path, output: Path, *, scope: str =
            'Finite solid style-matrix background projection, source/rebuild cycles and authored edit',
            limitations: list[str] | None = None) -> None:
    import pymupdf

    poppler = shutil.which('pdftoppm')
    if poppler is None:
        raise RuntimeError('Independent Poppler renderer is required')
    native = json.loads((root / 'native.json').read_text(encoding='utf-8-sig'))
    assert native['success'] and all(item['source_unchanged'] for item in native['files'])
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    images, sources, rows = {}, [], []
    for item in manifest['files']:
        path = root / item['file']
        with pymupdf.open(path.with_suffix('.pdf')) as document:
            assert len(document) == 1 and 'Own background control' in document[0].get_text()
            page = document[0]
            image = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
            mupdf = (image.width, image.height, image.samples)
        prefix = path.with_suffix('')
        subprocess.run([poppler, '-singlefile', '-r', '108', '-png', str(path.with_suffix('.pdf')), str(prefix)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        image = pymupdf.Pixmap(str(prefix.with_suffix('.png')))
        raster = (image.width, image.height, image.samples)
        images[item['file']] = (mupdf, raster)
        if item['route'] in ('original', 'edit-reference'):
            if item.get('expected_background') is not None:
                color = bytes.fromhex(item['expected_background'].lstrip('#'))
                from collections import Counter

                samples = mupdf[2]
                counts = Counter(zip(samples[::3], samples[1::3], samples[2::3]))
                count = sum(amount for rgb, amount in counts.items() if max(abs(rgb[i]-color[i]) for i in range(3)) <= 1)
                assert count > mupdf[0]*mupdf[1]//2, 'Background control is missing: '+item['file']
            sources.append({**item, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    for item in manifest['files']:
        if item['route'] in ('original', 'edit-reference'):
            continue
        reference = item['case'] + ('/authored-edit.pptx' if item['route'] == 'rebuild-edit' else '/original.pptx')
        observed, expected = images[item['file']], images[reference]
        rows.append({**item, 'sha256': hashlib.sha256((root / item['file']).read_bytes()).hexdigest(),
                     'mupdf_exact': observed[0] == expected[0], 'poppler_exact': observed[1] == expected[1]})
    report = {'scope': scope,
              'dpi': 108, 'masks': None, 'pixel_tolerance': 0, 'source_color_control_maximum_channel_rounding': 1,
              'native': native, 'sources': sources, 'comparisons': rows,
              'limitations': (limitations if limitations is not None else
                              ['Not full theme/master hierarchy or gradients/effects/bitmap background acceptance'])}
    output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    assert all(row['mupdf_exact'] and row['poppler_exact'] for row in rows), 'Native pages differ'
    print(f'{len(rows)} exact full-page comparisons in each renderer')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'check'))
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.root)
    elif args.output:
        compare(args.root, args.output)
    else:
        parser.error('check requires --output')


if __name__ == '__main__':
    main()
