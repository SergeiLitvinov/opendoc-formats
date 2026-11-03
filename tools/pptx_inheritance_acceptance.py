"""Prepare own PPTX fixtures and compare native PDFs with MuPDF and Poppler at 108 dpi."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from importlib.metadata import version
from pathlib import Path


def prepare(root: Path, reference: Path | None = None) -> None:
    import opendoc_model as od

    from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document
    from opendoc_formats.readers.pptx_inheritance import KEY
    from tests.readers.test_pptx_inheritance import own_master_group, own_master_picture, own_pptx

    root.mkdir(parents=True, exist_ok=False)
    cases = [('visible', {}), ('slide-hide', {'slide_flag': '0'}), ('layout-hide', {'layout_flag': 'false'}),
             ('explicit-visible', {'slide_flag': '1', 'layout_flag': 'true'}), ('hidden-shape', {'hidden': '1'}),
             ('shared-text', {'master_text': 'Own shared master'}), ('master-group', {}), ('master-picture', {})]
    if reference is not None:
        cases.append(('independent-master', {}))
    files = []
    for name, options in cases:
        folder = root/name
        folder.mkdir()
        source = folder/'own-inheritance.pptx'
        if name == 'independent-master':
            source.write_bytes(reference.read_bytes())
        else:
            source = own_pptx(folder, **options)
            if name == 'master-group':
                own_master_group(source)
            elif name == 'master-picture':
                own_master_picture(source)
        files.append({'file': source.relative_to(root).as_posix(), 'case': name, 'route': 'original', 'cycle': 0})
        result = read_document(source)
        assert result.success, result.issues
        for mode in ['source', 'rebuild']:
            model = result.document
            for cycle in [1, 2]:
                model = od.document_from_json(od.document_to_json(model))
                target = folder/f'{mode}-{cycle}.pptx'
                report = write_document(model, target, options=ExportOptions(pptx_profile=PptxProfile(layout=mode)))
                assert report.success, report.issues
                files.append({'file': target.relative_to(root).as_posix(), 'case': name, 'route': mode, 'cycle': cycle})
                reread = read_document(target)
                assert reread.success, reread.issues
                model = reread.document
        if name == 'visible':
            model = od.document_from_json(od.document_to_json(result.document))
            for section in model.sections:
                for block in section.blocks:
                    if block.properties.get(KEY, {}).get('scope') == 'master':
                        block.box.x += 10
                        block.box.width += 5
            for cycle in [1, 2]:
                target = folder/f'edited-{cycle}.pptx'
                assert write_document(model, target).success
                model = od.document_from_json(od.document_to_json(read_document(target).document))
    (root/'manifest.json').write_text(json.dumps({'files': files}, indent=2)+'\n', encoding='utf-8')


def compare(roots: list[Path], output: Path) -> None:
    import pymupdf
    from PIL import Image

    poppler = shutil.which('pdftoppm')
    if poppler is None:
        raise RuntimeError('Poppler pdftoppm is required for independent native acceptance')
    rasters = {}
    rows, originals, native = [], [], []
    for root in roots:
        manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
        native.append(json.loads((root/'native.json').read_text(encoding='utf-8-sig')))
        assert native[-1]['success'] and all(row['source_unchanged'] for row in native[-1]['files'])
        pairs = []
        for item in manifest['files']:
            if item['route'] == 'original':
                controls = []
                with pymupdf.open((root/item['file']).with_suffix('.pdf')) as source_pdf:
                    for page, native_page in enumerate(source_pdf):
                        pixmap = native_page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                        image = Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples)
                        colors = dict((color, count) for count, color in image.getcolors(pixmap.width*pixmap.height))
                        def visible_color(rgb):
                            return sum(count for color, count in colors.items()
                                       if max(abs(color[i]-rgb[i]) for i in range(3)) <= 1) > 100
                        purple = visible_color((122, 62, 157))
                        expected = (item['case'] not in {'layout-hide', 'hidden-shape'}
                                    and not (item['case'] == 'slide-hide' and page == 0))
                        assert purple == expected and native_page.get_text().strip(), 'Original control is blank or differs'
                        if item['case'] == 'master-picture':
                            assert visible_color((18, 69, 120)), 'Original inherited image is not visible'
                        controls.append({'page': page+1, 'purple_visible': purple, 'text_nonempty': True})
                originals.append({'case': item['case'], 'controls': controls,
                                  'source_sha256': hashlib.sha256((root/item['file']).read_bytes()).hexdigest()})
            else:
                pairs.append((item, root/item['case']/'own-inheritance.pdf', (root/item['file']).with_suffix('.pdf')))
        if (root/'native-edit.json').exists():
            edited = json.loads((root/'native-edit.json').read_text(encoding='utf-8-sig'))
            assert edited['success'] and all(row['source_unchanged'] for row in edited['files'])
            native.append(edited)
            for cycle in [1, 2]:
                pairs.append(({'case': 'visible-native-edit', 'route': 'rebuild-edit', 'cycle': cycle},
                              root/'visible/native-edit.pdf', root/f'visible/edited-{cycle}.pdf'))

        def raster(pdf: Path) -> list[Path]:
            if pdf not in rasters:
                folder = root/'poppler'
                folder.mkdir(exist_ok=True)
                prefix = folder/f'pdf-{len(rasters):03}'
                subprocess.run([poppler, '-r', '108', '-png', str(pdf), str(prefix)], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                rasters[pdf] = sorted(folder.glob(prefix.name+'-*.png'), key=lambda p: int(p.stem.rsplit('-', 1)[1]))
            return rasters[pdf]

        for item, expected, actual in pairs:
            a_poppler, b_poppler = raster(expected), raster(actual)
            with pymupdf.open(expected) as a, pymupdf.open(actual) as b:
                assert len(a) == len(b) == len(a_poppler) == len(b_poppler)
                for page in range(len(a)):
                    x = a[page].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                    y = b[page].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                    with Image.open(a_poppler[page]) as a_image, Image.open(b_poppler[page]) as b_image:
                        a_bytes, b_bytes = a_image.convert('RGB').tobytes(), b_image.convert('RGB').tobytes()
                        poppler_exact = a_image.size == b_image.size and a_bytes == b_bytes
                    rows.append({**item, 'page': page+1, 'mupdf_exact': x.samples == y.samples,
                                 'poppler_exact': poppler_exact, 'text_equal': a[page].get_text() == b[page].get_text(),
                                 'mupdf_expected_sha256': hashlib.sha256(x.samples).hexdigest(),
                                 'mupdf_actual_sha256': hashlib.sha256(y.samples).hexdigest(),
                                 'poppler_expected_sha256': hashlib.sha256(a_bytes).hexdigest(),
                                 'poppler_actual_sha256': hashlib.sha256(b_bytes).hexdigest()})
    evidence = {'scope': 'Own finite inherited master/layout profile; full native pages, no masks or pixel tolerances',
                'versions': {'opendoc-model': version('opendoc-model'), 'pymupdf': pymupdf.VersionBind},
                'source_color_control': {'maximum_channel_rounding': 1, 'minimum_pixels': 100},
                'full_page_comparison_tolerance': 0,
                'native': native, 'originals': originals, 'comparisons': rows,
                'summary': {'pages': len(rows), 'mupdf_exact': sum(r['mupdf_exact'] for r in rows),
                            'poppler_exact': sum(r['poppler_exact'] for r in rows)},
                'limitations': ['Not arbitrary PPTX compatibility', 'Group hierarchy flattened',
                                'Shared master source edits require an explicit all-consumer policy',
                                'Unaccepted features retain located diagnostics; no complete lossless claim']}
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(evidence['summary'])
    assert all(row['mupdf_exact'] and row['poppler_exact'] and row['text_equal'] for row in rows), 'Native acceptance differs'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_parser = commands.add_parser('prepare')
    prepare_parser.add_argument('root', type=Path)
    prepare_parser.add_argument('--reference', type=Path)
    check_parser = commands.add_parser('check')
    check_parser.add_argument('roots', type=Path, nargs='+')
    check_parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.root, args.reference)
    else:
        compare(args.roots, args.output)


if __name__ == '__main__':
    main()
