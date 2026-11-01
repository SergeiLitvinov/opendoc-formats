"""Independent XML/ZIP page-geometry originals; native inspection never edits them."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from tests.binary_fixtures import PR, W, zip_bytes

LETTER = '<w:pgSz w:w="12240" w:h="15840"/>'
A4 = '<w:pgSz w:w="11906" w:h="16838"/>'
MARGINS = '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>'


def cases():
    return {
        'missing-size': [MARGINS],
        'empty-size': ['<w:pgSz/>'+MARGINS],
        'width-only': ['<w:pgSz w:w="11200"/>'+MARGINS],
        'height-only': ['<w:pgSz w:h="14400"/>'+MARGINS],
        'landscape-only': ['<w:pgSz w:orient="landscape"/>'+MARGINS],
        'explicit-landscape': ['<w:pgSz w:w="15840" w:h="12240" w:orient="landscape"/>'+MARGINS],
        'empty-section': [''],
        'missing-margins': [LETTER],
        'empty-margins': [LETTER+'<w:pgMar/>'],
        'partial-margins': [LETTER+'<w:pgMar w:left="1440"/>'],
        'explicit-a4': [A4+MARGINS],
        'missing-section': [None],
        'a4-then-missing': [A4+MARGINS, MARGINS],
        'missing-then-a4': [MARGINS, A4+MARGINS],
        'a4-then-implicit': [A4+MARGINS, None],
    }


def edit_cases():
    return {
        'edited-width': {'source': [MARGINS], 'expected': ['<w:pgSz w:w="14000"/>'+MARGINS], 'changes': {'width': 700}},
        'edited-height': {'source': ['<w:pgSz w:w="11200"/>'+MARGINS],
                          'expected': ['<w:pgSz w:w="11200" w:h="14400"/>'+MARGINS], 'changes': {'height': 720}},
        'edited-left': {'source': [LETTER], 'expected': [LETTER+'<w:pgMar w:left="1200"/>'],
                        'changes': {'margin_left': 60}},
        'materialized-size': {'source': [None], 'expected': ['<w:pgSz w:w="12000" w:h="16000"/>'],
                              'changes': {'width': 600, 'height': 800}},
    }


def original(sections):
    paragraphs = []
    for index, settings in enumerate(sections):
        text = f'Section {index+1}. '+('Page geometry: size and margins determine line wrapping. '*18)
        section = '' if settings is None else '<w:sectPr>'+settings+'</w:sectPr>'
        ppr = '<w:pPr>'+section+'</w:pPr>' if index < len(sections)-1 else ''
        paragraphs.append('<w:p>'+ppr+'<w:r><w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/>'
                          '<w:sz w:val="24"/></w:rPr><w:t>'+text+'</w:t></w:r></w:p>')
        if index == len(sections)-1:
            paragraphs.append(section)
    document = f'<w:document xmlns:w="{W}"><w:body>'+''.join(paragraphs)+'</w:body></w:document>'
    types = ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Override PartName="/word/document.xml" '
             'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '</Types>')
    return zip_bytes([('[Content_Types].xml', types),
                      ('_rels/.rels', f'<Relationships xmlns="{PR}"><Relationship Id="rId1" '
                       'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                       'Target="word/document.xml"/></Relationships>'), ('word/document.xml', document)])


def verify_native(root, *, edits=False):
    from importlib.metadata import version

    import pymupdf
    from PIL import Image, ImageChops

    renderer = shutil.which('pdftoppm')
    if renderer is None:
        raise RuntimeError('Optional native visual inspection requires Poppler pdftoppm')
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    data = json.loads((root/'native-pdfa/observations.json').read_text(encoding='utf-8-sig'))
    profiles = {name: spec['expected'] for name, spec in edit_cases().items()} if edits else cases()
    expected = {suffix for name in profiles for suffix in (name, name+'-cycle-1', name+'-cycle-2')}
    by_name = {row['name']: row for row in data['observations']}
    if (len(manifest) != len(expected) or {row['name'] for row in manifest} != expected
            or len(by_name) != len(data['observations']) or set(by_name) != expected):
        raise ValueError('Native verification requires every original and both cycles exactly once')
    if data['pdf_profile'] != 'Word PDF/A-1 export' or not data['distinct_owned_process']:
        raise ValueError('Expected an independent Word PDF/A observation set')
    for entry in manifest:
        row = by_name[entry['name']]
        assert row['file'] == entry['file']
        assert hashlib.sha256((root/row['file']).read_bytes()).hexdigest().upper() == row['sha256']
        assert row['page_geometry']
    for name, settings in profiles.items():
        assert (root/(name+'.docx')).read_bytes() == original(settings)
    if edits:
        data['model_edits'] = {}
        for name, spec in edit_cases().items():
            path = root/(name+'-input.docx')
            assert path.read_bytes() == original(spec['source'])
            data['model_edits'][name] = {'input_file': path.name, 'page_edits_pt': spec['changes'],
                                         'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    raster = root/'poppler-pdfa'
    raster.mkdir(exist_ok=False)
    comparisons = []
    for name, row in by_name.items():
        if '-cycle-' not in name:
            continue
        source_name = name.split('-cycle-')[0]
        source = by_name[source_name]
        result = {'name': name, 'text_equal': row['text'] == source['text'],
                  'pages_equal': row['pages'] == source['pages'],
                  'geometry_equal': row['page_geometry'] == source['page_geometry']}
        for engine in ('MuPDF', 'Poppler'):
            pages = []
            for entry in (source_name, name):
                path = root/'native-pdfa'/(entry+'.pdf')
                pictures = []
                with pymupdf.open(path) as pdf:
                    assert len(pdf) == by_name[entry]['pages'] and len(pdf) <= 32
                    for page_index, page in enumerate(pdf):
                        assert page.rect.width*page.rect.height*2.25 < 16000000
                        if engine == 'MuPDF':
                            pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                            picture = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                        else:
                            stem = raster/f'{entry}-{page_index+1}'
                            if not stem.with_suffix('.png').exists():
                                subprocess.run([renderer, '-r', '108', '-f', str(page_index+1), '-l', str(page_index+1),
                                                '-singlefile', '-png', str(path), str(stem)], check=True,
                                               capture_output=True, timeout=45)
                            with Image.open(stem.with_suffix('.png')) as png:
                                picture = png.convert('RGB')
                        pictures.append(picture)
                pages.append(pictures)
            differences = []
            for source_page, target_page in zip(*pages):
                differences.append(ImageChops.difference(source_page, target_page).getbbox()
                                   if source_page.size == target_page.size else 'different-size')
            result[engine] = {'identical': len(pages[0]) == len(pages[1]) and all(x is None for x in differences),
                              'difference_bboxes': differences}
        comparisons.append(result)
    data['semantic_accepted'] = all(x['text_equal'] and x['pages_equal'] and x['geometry_equal'] for x in comparisons)
    data['visual_accepted'] = all(x['MuPDF']['identical'] and x['Poppler']['identical'] for x in comparisons)
    data['quality_gate_complete'] = data['semantic_accepted'] and data['visual_accepted']
    data['scope'] = 'page-geometry-model-edits-v1' if edits else 'page-geometry-source-omissions-v1'
    data['visual'] = {'dpi': 108, 'mask': None, 'comparisons': comparisons}
    data['runtime'] = {name: version(name) for name in ('opendoc-formats', 'opendoc-model', 'pymupdf', 'pillow')}
    data['runtime']['poppler'] = subprocess.run([renderer, '-v'], capture_output=True, check=True,
                                              text=True, timeout=10).stderr.splitlines()[0]
    (root/'evidence.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'native_documents': len(by_name), 'comparisons': len(comparisons),
                      'semantic_accepted': data['semantic_accepted'], 'visual_accepted': data['visual_accepted']}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--roundtrips', action='store_true')
    parser.add_argument('--verify-native', action='store_true')
    parser.add_argument('--edits', action='store_true', help='Compare explicit Model edits against independent XML references')
    args = parser.parse_args()
    if args.verify_native:
        verify_native(args.output, edits=args.edits)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = []
    profiles = {name: spec['expected'] for name, spec in edit_cases().items()} if args.edits else cases()
    for name, sections in profiles.items():
        path = args.output/(name+'.docx')
        path.write_bytes(original(sections))
        manifest.append({'name': name, 'file': path.name})
        if args.roundtrips:
            from opendoc_formats import read_document, write_document

            imported = read_document(path)
            if args.edits:
                from opendoc_model import Length

                spec = edit_cases()[name]
                input_path = args.output/(name+'-input.docx')
                input_path.write_bytes(original(spec['source']))
                imported = read_document(input_path)
                assert imported.success, imported.issues
                for field, points in spec['changes'].items():
                    setattr(imported.document.sections[0].page, field, Length(points))
            assert imported.success, imported.issues
            for cycle in (1, 2):
                path = args.output/f'{name}-cycle-{cycle}.json'
                assert write_document(imported.document, path).success
                imported = read_document(path)
                assert imported.success, imported.issues
                path = args.output/f'{name}-cycle-{cycle}.docx'
                report = write_document(imported.document, path)
                assert report.success, report.issues
                imported = read_document(path)
                assert imported.success, imported.issues
                manifest.append({'name': path.stem, 'file': path.name})
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    print('Prepared', len(manifest), 'independent page originals/roundtrips')


if __name__ == '__main__':
    main()
