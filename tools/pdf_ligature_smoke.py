"""Exercise installed PDF resource fonts and ToUnicode without fontTools."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory

import opendoc_model
import pymupdf

import opendoc_formats
from opendoc_formats import ImportOptions, read_document, write_document
from opendoc_formats.writers.pdf_unicode import restore_ligature_unicode

FONT_SHA256 = '002ab3822db7196c8ba23fa443d5d4e7026301fdee7f89883045d6b4f70528ad'
POST2_SHA256 = 'fe20d45d0138c607e22dac6526ad414fb37d30b5b10a1185f790003100c85e1e'
POST4_SHA256 = '335485e769416135ca5e87dee7bee5b96b9be004ff2fbeb8e9e16d558aa3d31a'
OTF_SHA256 = 'e102a71e4f21274983d96af916138915772aec68f0a82c821e575b5f1f9c01f8'
MIXED_SHA256 = 'a2493afa1a04e7b420679022188ff30763f6417fb34c8a86ffe84de4a777c0f0'
REVERSE_SHA256 = 'e92a9b8819c68d89506ecac9e2bc06d3d616cd17e17ffbe94efc1f5913b76767'
CONTEXT5_SHA256 = '3b53d3b1784e022ef0340d71a1b6951f1f401b7e0ff6b41bc6bbabce32d0c609'
CONTEXT6_SHA256 = '8c25375344548742a25a68030072732ce7da3de6d4b0652f31dc814b5e4b8ac6'
RULES5_SHA256 = 'f69af538874e85d675055da4c6a50542cef1b5a88094891b980255ced0f2bb1c'
RULES6_SHA256 = 'affc8cf56a6385f1fd1afec496415012921a90fd0abc05a7394a9e648a31340a'
CLASSES5_SHA256 = '8831814d5192b76ae75afaa2613357662fa3b7548a49d9599f72246ce4714a16'
CLASSES6_SHA256 = 'a57897217bda12c1b89ee7de2c81acd5d2e99936a0d5e87d365e8f008e93a804'


def resource_fonts(directory: Path) -> None:
    from opendoc_model import (
        DocumentModel,
        FontReference,
        Length,
        Paragraph,
        Resource,
        ResourceKind,
        Section,
        TextRun,
        TextStyle,
        document_from_json,
        document_to_json,
        get_font_reference,
        get_integration,
        get_text_layout,
        set_font_reference,
        walk_model,
    )

    fixtures = Path(__file__).resolve().parents[1]/'tests/native/data'
    for filename, digest, text, media in (
        ('ligature-post3.ttf', FONT_SHA256, 'fi ti fi', 'font/ttf'),
        ('ligature-post2.ttf', POST2_SHA256, 'fi ti fi', 'font/ttf'),
        ('ligature-post4.ttf', POST4_SHA256, 'fi ti fi', 'font/ttf'),
        ('ligature-mixed.ttf', MIXED_SHA256, 'fi ti fi', 'font/ttf'),
        ('ligature-reverse.ttf', REVERSE_SHA256, 'fi ti fi', 'font/ttf'),
        ('ligature-context5.ttf', CONTEXT5_SHA256, 'fi ti fi', 'font/ttf'),
        ('ligature-context6.ttf', CONTEXT6_SHA256, 'fi ti fi', 'font/ttf'),
        ('ligature-rules5.ttf', RULES5_SHA256, 'fi ti fi', 'font/ttf'),
        ('ligature-rules6.ttf', RULES6_SHA256, 'fi ti fi', 'font/ttf'),
        ('ligature-classes5.ttf', CLASSES5_SHA256, 'fi ti fi', 'font/ttf'),
        ('ligature-classes6.ttf', CLASSES6_SHA256, 'fi ti fi', 'font/ttf'),
        ('own-cff.otf', OTF_SHA256, 'AB', 'font/otf'),
    ):
        source = (fixtures/filename).read_bytes()
        assert hashlib.sha256(source).hexdigest() == digest
        style = TextStyle(font_family='Intentionally unrelated family', font_size=Length(20))
        set_font_reference(style, FontReference('own', 0))
        document = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun(text, style)])])], resources={
            'own': Resource('own', ResourceKind.FONT, media, source),
        })
        pixels = None
        for cycle in range(2):
            document = document_from_json(document_to_json(document))
            before = document_to_json(document)
            target = directory/f'{filename}-{cycle}.pdf'
            report = write_document(document, target)
            assert report.success, report.issues
            assert report.metrics['font_resolution']['substitution_count'] == 0
            assert report.metrics['font_embedding']['verified_program_sha256'] == [digest]
            assert document_to_json(document) == before
            with pymupdf.open(target) as pdf:
                assert ''.join(pdf[0].get_text().split()) == ''.join(text.split())
                assert any(pdf.extract_font(f[0])[3] == source for f in pdf[0].get_fonts(full=True))
                image = pdf[0].get_pixmap().samples
                assert pixels is None or image == pixels
                pixels = image
            imported = read_document(target)
            assert imported.success, imported.issues
            restored = document_from_json(document_to_json(imported.document))
            runs = [location.node for location in walk_model(restored)
                    if isinstance(location.node, TextRun) and location.node.text.strip()]
            assert runs
            for run in runs:
                reference = get_font_reference(run.style)
                assert reference is not None and restored.resources[reference.resource_id].data == source, (
                    filename, run.text, reference,
                    [(r.id, len(r.data or b''), hashlib.sha256(r.data or b'').hexdigest())
                     for r in imported.document.resources.values() if r.kind is ResourceKind.FONT],
                )
            captured = read_document(target, options=ImportOptions(pdf_text_layouts=True))
            assert captured.success, captured.issues
            captured_model = captured.document
            for _ in range(2):
                captured_model = document_from_json(document_to_json(captured_model))
            layouts = get_integration(captured_model).text_layouts
            assert layouts and all(layout.state == 'verified' and layout.clusters for layout in layouts)
            integration = get_integration(captured_model)
            ranges = {value.id: value for value in integration.ranges}
            for layout in layouts:
                assert layout.binding_version == 2 and layout.binding_sha256
                assert layout.extra['opendoc_formats.paint_state'] == 'unassessed'
                assert all(identifier in ranges for cluster in layout.clusters for identifier in cluster.range_ids)
                assert layout.fonts and layout.fonts[0].face_index == 0
                assert captured_model.resources[layout.fonts[0].resource_id].data == source
                native_source = captured_model.resources[layout.extra['opendoc_formats.pdf_source_resource_id']].data
                assert native_source == target.read_bytes()
            bound_runs = [location.node for location in walk_model(captured_model)
                          if isinstance(location.node, TextRun) and location.node.text.strip()]
            for run in bound_runs:
                run.style.bold = not run.style.bold
            assert all(get_text_layout(captured_model, layout.id).state == 'stale' for layout in layouts)
        assert (fixtures/filename).read_bytes() == source


def main() -> None:
    for module in (opendoc_formats, opendoc_model):
        assert 'site-packages' in Path(module.__file__).parts
    for name in ('fontTools', 'PIL', 'docx', 'lxml', 'bs4', 'pypdf', 'pdfplumber', 'pdf2docx'):
        assert importlib.util.find_spec(name) is None, name
    fixture = Path(__file__).resolve().parents[1]/'tests/native/data/ligature-post3.ttf'
    source = fixture.read_bytes()
    assert hashlib.sha256(source).hexdigest() == FONT_SHA256
    story = pymupdf.Story(html='<p>fi ti fi</p>', user_css=(
        '@font-face {font-family:Own;src:url(ligature-post3.ttf);} p {font-family:Own;font-size:20pt;}'
    ), archive=pymupdf.Archive(str(fixture.parent)))
    pdf = story.write_with_links(lambda *_: (
        pymupdf.Rect(0, 0, 240, 200), pymupdf.Rect(20, 20, 220, 180), pymupdf.Identity,
    ))
    try:
        pixels = pdf[0].get_pixmap().samples
        assert ''.join(pdf[0].get_text().split()) != 'fitifi'
        report = opendoc_model.ConversionReport(None)
        restore_ligature_unicode(pdf, report, 'own-page')
        assert report.success and report.metrics['pdf_ligature_unicode_mappings'] == 2
        with TemporaryDirectory(prefix='opendoc_ligatures_') as directory:
            target = Path(directory)/'own.pdf'
            pdf.save(target)
            with pymupdf.open(target) as restored:
                assert ''.join(restored[0].get_text().split()) == 'fitifi'
                assert restored[0].get_pixmap().samples == pixels
    finally:
        pdf.close()
    assert fixture.read_bytes() == source
    with TemporaryDirectory(prefix='opendoc_resource_fonts_') as directory:
        resource_fonts(Path(directory))
    print('Installed Story/ToUnicode without fontTools: fi/ti text, mappings=2, saved-file pixels unchanged')
    print('Installed public PDF post-2/post-3/post-4/mixed/reverse/context-GSUB TTF and OTF: '
          'programs, text and pixels retained through JSON')
    print('Installed PDF re-import: actual program bytes bound to text through the shared bounded placement reader')
    print('Opt-in native TextLayout: source snapshot, explicit faces and matrices survive Model JSON without fontTools')


if __name__ == '__main__':
    main()
