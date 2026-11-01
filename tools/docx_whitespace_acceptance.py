"""Own XML/ZIP originals for native Word whitespace inspection and conversion checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from tests.binary_fixtures import PR, W, zip_bytes


def cases():
    return [
        ('absent', {}, '  A  B  '),
        ('explicit-default', {'t': 'default'}, '  A  B  '),
        ('explicit-preserve', {'t': 'preserve'}, '  A  B  '),
        ('run-preserve', {'r': 'preserve'}, '  A  B  '),
        ('paragraph-preserve', {'p': 'preserve'}, '  A  B  '),
        ('body-preserve', {'body': 'preserve'}, '  A  B  '),
        ('document-preserve', {'document': 'preserve'}, '  A  B  '),
        ('paragraph-preserve-text-default', {'p': 'preserve', 't': 'default'}, '  A  B  '),
        ('document-preserve-paragraph-default', {'document': 'preserve', 'p': 'default'}, '  A  B  '),
        ('document-default-text-preserve', {'document': 'default', 't': 'preserve'}, '  A  B  '),
        ('document-preserve-text-default', {'document': 'preserve', 't': 'default'}, '  A  B  '),
        ('only-spaces', {}, '   '),
        ('only-spaces-preserve', {'t': 'preserve'}, '   '),
        ('unicode-spaces', {}, '\u00a0A\u2003'),
        ('literal-controls', {}, '\n A\t B\r'),
        ('literal-controls-preserve', {'t': 'preserve'}, '\n A\t B\r'),
        ('character-references', {}, '&#xA; A&#x9; B&#xD;'),
        ('character-references-preserve', {'t': 'preserve'}, '&#xA; A&#x9; B&#xD;'),
        ('hyperlink-boundary', {}, 'After '),
    ]


def original(name, attributes, text):
    r = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
    def attribute(tag):
        value = attributes.get(tag)
        return f' xml:space="{value}"' if value is not None else ''
    style = '<w:rPr><w:rFonts w:ascii="Arial" w:hAnsi="Arial"/><w:sz w:val="24"/></w:rPr>'
    content = ('<w:r>'+style+'<w:t>L[</w:t></w:r>'
               +f'<w:r{attribute("r")}>{style}<w:t{attribute("t")}>{text}</w:t></w:r>')
    if name == 'hyperlink-boundary':
        content += '<w:hyperlink w:anchor="OwnAnchor"><w:r>'+style+'<w:t>Link</w:t></w:r></w:hyperlink>'
    content += '<w:r>'+style+'<w:t>]R</w:t></w:r>'
    section = ('<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
               '<w:pgMar w:top="1440" w:bottom="1440" w:left="1440" w:right="1440"/></w:sectPr>')
    document = (f'<w:document xmlns:w="{W}" xmlns:r="{r}"{attribute("document")}>'
                +f'<w:body{attribute("body")}><w:p{attribute("p")}>{content}</w:p>{section}</w:body></w:document>')
    types = ('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Override PartName="/word/document.xml" '
             'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
             '</Types>')
    return zip_bytes([('[Content_Types].xml', types),
                      ('_rels/.rels', f'<Relationships xmlns="{PR}"><Relationship Id="rId1" Type="{r}/officeDocument" '
                       'Target="word/document.xml"/></Relationships>'),
                      ('word/document.xml', document)])


def verify_native(root, *, pdfa=False):
    import pymupdf
    from PIL import Image, ImageChops

    renderer = shutil.which('pdftoppm')
    if renderer is None:
        raise RuntimeError('Optional native visual inspection requires Poppler pdftoppm')
    native = root/('native-pdfa' if pdfa else 'native')
    evidence = json.loads((native/'observations.json').read_text(encoding='utf-8-sig'))
    by_name = {item['name']: item for item in evidence['observations']}
    raster = root/('poppler-pdfa' if pdfa else 'poppler')
    raster.mkdir(exist_ok=False)
    visual = []
    for name, item in by_name.items():
        assert hashlib.sha256((root/item['file']).read_bytes()).hexdigest().upper() == item['sha256']
        if '-cycle-' not in name:
            continue
        source_name = name.split('-cycle-')[0]
        source = by_name[source_name]
        assert item['text'] == source['text'] and item['pages'] == source['pages'] == 1
        result = {'name': name, 'text_equal': True, 'pages_equal': True}
        for engine in ('MuPDF', 'Poppler'):
            pictures = []
            for entry in (source_name, name):
                path = native/(entry+'.pdf')
                if engine == 'MuPDF':
                    with pymupdf.open(path) as document:
                        page = document[0]
                        assert page.rect.width*page.rect.height*2.25 < 16000000
                        pix = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
                        picture = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                else:
                    stem = raster/entry
                    if not stem.with_suffix('.png').exists():
                        subprocess.run([renderer, '-r', '108', '-singlefile', '-png', str(path), str(stem)],
                                       check=True, capture_output=True, timeout=45)
                    with Image.open(stem.with_suffix('.png')) as png:
                        picture = png.convert('RGB')
                pictures.append(picture)
            assert pictures[0].size == pictures[1].size
            bbox = ImageChops.difference(*pictures).getbbox()
            result[engine] = {'identical': bbox is None, 'difference_bbox': bbox}
        visual.append(result)
    evidence['semantic_accepted'] = True
    evidence['visual_accepted'] = all(row['MuPDF']['identical'] and row['Poppler']['identical'] for row in visual)
    evidence['quality_gate_complete'] = evidence['visual_accepted']
    evidence['visual'] = {'dpi': 108, 'comparisons': visual, 'mask': None}
    (root/('evidence-pdfa.json' if pdfa else 'evidence.json')).write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps({'native_documents': len(by_name), 'semantic_accepted': True,
                      'pixel_identical_comparisons': sum(row['MuPDF']['identical'] and row['Poppler']['identical']
                                                         for row in visual),
                      'visual_comparisons': len(visual), 'visual_accepted': evidence['visual_accepted']}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--roundtrips', action='store_true', help='Also prepare two public JSON/DOCX cycles per original')
    parser.add_argument('--verify-native', action='store_true',
                        help='Verify native observations and report actual pixel differences')
    parser.add_argument('--pdfa', action='store_true',
                        help='Inspect separate native-pdfa previews, retaining the standard report')
    args = parser.parse_args()
    if args.verify_native:
        verify_native(args.output, pdfa=args.pdfa)
        return
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = []
    for name, attributes, text in cases():
        filename = name+'.docx'
        (args.output/filename).write_bytes(original(name, attributes, text))
        manifest.append({'name': name, 'file': filename, 'attributes': attributes, 'source_text': text})
        if args.roundtrips:
            from opendoc_formats import read_document, write_document

            imported = read_document(args.output/filename)
            assert imported.success, imported.issues
            model = imported.document
            for cycle in (1, 2):
                json_path = args.output/f'{name}-cycle-{cycle}.json'
                report = write_document(model, json_path)
                assert report.success, report.issues
                imported = read_document(json_path)
                assert imported.success, imported.issues
                filename = f'{name}-cycle-{cycle}.docx'
                report = write_document(imported.document, args.output/filename)
                assert report.success, report.issues
                imported = read_document(args.output/filename)
                assert imported.success, imported.issues
                model = imported.document
                manifest.append({'name': f'{name}-cycle-{cycle}', 'file': filename, 'source_case': name})
    (args.output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(f'Prepared {len(manifest)} DOCX originals/roundtrips for native inspection')


if __name__ == '__main__':
    main()
