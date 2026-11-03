"""Audit explicit Word compatibility modes using independent own originals."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from importlib.metadata import version
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

from opendoc_formats import read_document, write_document

W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MODES = ('14', '15')


def settings(path):
    with ZipFile(path) as archive:
        return etree.tostring(etree.fromstring(archive.read('word/settings.xml')), method='c14n')


def prepare(root, references):
    from docx import Document

    root.mkdir(exist_ok=False, parents=True)
    manifest = []
    for mode in MODES:
        name = 'mode-'+mode
        source = root/(name+'.docx')
        if references:
            # Explicit own fixtures only; no directory enumeration or private corpus access.
            source.write_bytes((references/f'own-mode-{mode}.docx').read_bytes())
        else:
            native = Document()
            native.add_paragraph('Independent table position control')
            table = native.add_table(rows=2, cols=2)
            table.style = 'Table Grid'
            for row, values in zip(table.rows, [('Item', 'Amount'), ('Own entry', '7')], strict=True):
                for cell, text in zip(row.cells, values, strict=True):
                    cell.text = text
            declaration = native.settings.element.xpath('.//w:compatSetting[@w:name="compatibilityMode"]')
            assert len(declaration) == 1
            declaration[0].set(W+'val', mode)
            native.save(source)
        expected = settings(source)
        declarations = etree.fromstring(expected).findall('.//'+W+'compatSetting')
        assert [node.get(W+'val') for node in declarations if node.get(W+'name') == 'compatibilityMode'] == [mode]
        manifest.append({'name': name, 'file': source.name})
        current = source
        for cycle in (1, 2):
            imported = read_document(current)
            assert imported.success, imported.issues
            intermediate = root/f'{name}-cycle-{cycle}.json'
            report = write_document(imported.document, intermediate)
            assert report.success, report.issues
            imported = read_document(intermediate)
            assert imported.success, imported.issues
            current = root/f'{name}-cycle-{cycle}.docx'
            report = write_document(imported.document, current)
            assert report.success, report.issues
            assert settings(current) == expected
            manifest.append({'name': current.stem, 'file': current.name})
    (root/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')


def check(root, output):
    import pymupdf
    from PIL import Image

    poppler = shutil.which('pdftoppm')
    assert poppler, 'Poppler is required'
    evidence = json.loads((root/'native/observations.json').read_text(encoding='utf-8-sig'))
    expected = {f'mode-{mode}{suffix}' for mode in MODES for suffix in ('', '-cycle-1', '-cycle-2')}
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    observations = evidence['observations']
    by_name = {item['name']: item for item in observations}
    assert len(observations) == len(manifest) == len(expected)
    assert {row['name'] for row in manifest} == set(by_name) == expected
    assert evidence['distinct_owned_process'] and evidence['pdf_profile'] == 'Word standard PDF export'
    for item in manifest:
        row = by_name[item['name']]
        assert row['file'] == item['file']
        assert hashlib.sha256((root/item['file']).read_bytes()).hexdigest().upper() == row['sha256']
    rasters = root/'poppler'
    rasters.mkdir(exist_ok=False)
    rows = []
    for mode in MODES:
        source = by_name['mode-'+mode]
        assert source['compatibility_mode'] == int(mode) and source['pages'] == 1
        assert 'Own entry' in source['text'] and '7' in source['text']
        source_xml = settings(root/source['file'])
        for cycle in (1, 2):
            item = by_name[f'mode-{mode}-cycle-{cycle}']
            assert item['text'] == source['text'] and item['pages'] == source['pages']
            assert item['compatibility_mode'] == int(mode)
            assert settings(root/item['file']) == source_xml
            pixels = []
            for entry in (source, item):
                pdf = root/'native'/Path(entry['file']).with_suffix('.pdf')
                with pymupdf.open(pdf) as document:
                    assert len(document) == 1 and document[0].get_text().strip()
                    pix = document[0].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                    mupdf = (pix.width, pix.height, pix.samples)
                prefix = rasters/Path(entry['file']).stem
                png = prefix.with_suffix('.png')
                if not png.exists():
                    subprocess.run([poppler, '-r', '108', '-singlefile', '-png', str(pdf), str(prefix)],
                                   check=True, capture_output=True, timeout=45)
                with Image.open(png) as image:
                    pixels.append((mupdf, (image.size, image.convert('RGB').tobytes())))
            row = {'mode': mode, 'cycle': cycle, 'settings_equal': True, 'native_mode_equal': True,
                   'text_equal': True, 'mupdf_exact': pixels[0][0] == pixels[1][0],
                   'poppler_exact': pixels[0][1] == pixels[1][1],
                   'mupdf_source_sha256': hashlib.sha256(pixels[0][0][2]).hexdigest(),
                   'mupdf_output_sha256': hashlib.sha256(pixels[1][0][2]).hexdigest(),
                   'poppler_source_sha256': hashlib.sha256(pixels[0][1][1]).hexdigest(),
                   'poppler_output_sha256': hashlib.sha256(pixels[1][1][1]).hexdigest()}
            rows.append(row)
    repository = Path(__file__).resolve().parents[1]
    sources = ('src/opendoc_formats/readers/docx.py', 'src/opendoc_formats/ooxml/docx_defaults.py',
               'src/opendoc_formats/writers/docx_writer.py')
    evidence.update({'scope': 'Own text and standard 2x2 table; explicit Word modes 14 and 15; two JSON/DOCX cycles',
                     'dpi': 108, 'pixel_tolerance': 0, 'masks': None, 'comparisons': rows,
                     'runtime': {name: version(name) for name in ('opendoc-model', 'python-docx', 'pymupdf', 'pillow')},
                     'formats_source_sha256': {name: hashlib.sha256((repository/name).read_bytes()).hexdigest()
                                               for name in sources},
                     'limitations': ['No arbitrary table geometry or conditional style acceptance',
                                     'No causal claim about compatibility mode and private table shifts']})
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    assert all(row['mupdf_exact'] and row['poppler_exact'] for row in rows), 'Native rendering differs'
    print(f'{len(rows)} exact native comparisons in both renderers')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'check'])
    parser.add_argument('root', type=Path)
    parser.add_argument('--references', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        prepare(args.root, args.references)
    else:
        if args.output is None:
            parser.error('check requires --output')
        check(args.root, args.output)


if __name__ == '__main__':
    main()
