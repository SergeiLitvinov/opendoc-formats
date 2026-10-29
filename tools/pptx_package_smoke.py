"""Installed PPTX-only profile: original opaque bytes, graph and two JSON cycles."""

import hashlib
import importlib.util
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import opendoc_model as od
from pptx import Presentation
from pptx.util import Inches

import opendoc_formats
from opendoc_formats import ExportOptions, PptxProfile, read_document, write_document


def main():
    for module in (od, opendoc_formats):
        assert 'site-packages' in Path(module.__file__).parts
    for name in ('fontTools', 'docx', 'pymupdf', 'pypdf', 'bs4'):
        assert importlib.util.find_spec(name) is None, name
    with TemporaryDirectory(prefix='opendoc_pptx_package_') as directory:
        source = Path(directory)/'own.pptx'
        deck = Presentation()
        slide = deck.slides.add_slide(deck.slide_layouts[6])
        slide.shapes.add_textbox(0, 0, Inches(2), Inches(1)).text = 'Own editable text'
        table = slide.shapes.add_table(1, 2, 0, Inches(2), Inches(4), Inches(1)).table
        table.cell(0, 0).text = 'Own cell'
        deck.save(source)
        buffer = io.BytesIO()
        with ZipFile(source) as original, ZipFile(buffer, 'w', ZIP_DEFLATED) as output:
            for item in original.infolist():
                output.writestr(item, original.read(item))
            output.writestr('own/unknown.bin', b'own inert payload\x00\xff')
            output.writestr('own/_rels/unknown.bin.rels', (
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rIdLink" Type="urn:own:external" TargetMode="External" '
                'Target="https://example.invalid/never-fetch"/></Relationships>'
            ))
        source.write_bytes(buffer.getvalue())
        digest = hashlib.sha256(source.read_bytes()).digest()
        result = read_document(source)
        assert result.success and not result.lossless, result.issues
        model = result.document
        expected = od.document_to_json(model)
        for _ in range(2):
            model = od.document_from_json(od.document_to_json(model))
            assert model.validate() == [] and od.document_to_json(model) == expected
            assert model.package.format == 'pptx'
            with ZipFile(source) as archive:
                assert set(model.package.parts) == {'/'+name for name in archive.namelist()}
                for name, part in model.package.parts.items():
                    assert part.data == archive.read(name[1:])
            assert any(edge.source == '/own/unknown.bin' and edge.external
                       and edge.target == 'https://example.invalid/never-fetch' for edge in model.package.relationships)
            records = od.get_integration(model).preservation
            assert {r.provenance.package_part for r in records if r.issue.code == 'pptx.package-part'} == set(model.package.parts)
            assert 'Own editable text' in str(model)
        assert hashlib.sha256(source.read_bytes()).digest() == digest
        model.sections[0].blocks[0].content[0].text = 'Own native edit'
        model.sections[0].blocks[0].box.x += 10
        model.sections[0].blocks[0].box.width += 12
        model.sections[0].blocks[0].box.rotation += 5
        model.sections[0].blocks[1].rows[0].cells[0].blocks[0].content[0].text = 'Own cell edit'
        model.sections[0].blocks[1].rows[0].cells[1].blocks[0].content.append(od.TextRun('Own empty cell edit'))
        output = Path(directory)/'edited.pptx'
        report = write_document(model, output, options=ExportOptions(pptx_profile=PptxProfile(layout='source')))
        assert report.success, report.issues
        assert report.metrics['geometry_edits'] == 1
        assert report.metrics['cell_text_edits'] == 2
        with ZipFile(source) as old, ZipFile(output) as new:
            assert set(old.namelist()) == set(new.namelist())
            assert [name for name in old.namelist() if old.read(name) != new.read(name)] == ['ppt/slides/slide1.xml']
        assert 'Own native edit' in str(read_document(output).document)
    print('Installed PPTX-only profile: physical parts, inert external edge and two JSON cycles passed')


if __name__ == '__main__':
    main()
