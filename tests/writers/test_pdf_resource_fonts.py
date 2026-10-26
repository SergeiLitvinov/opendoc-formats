"""Document-owned programs have priority over family guesses in PDF export."""

import hashlib
from io import BytesIO
from pathlib import Path
from threading import Event

import pymupdf
import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTCollection, TTFont
from opendoc_model import (
    ArtifactLimitError,
    DocumentLimits,
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
    set_font_reference,
)

from opendoc_formats import ExportOptions, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.fonts.resolver import FontResolver
from opendoc_formats.pdf import PdfDocument
from opendoc_formats.writers.pdf_writer import write_pdf_model

FIXTURE = Path(__file__).resolve().parents[1]/'native/data/ligature-post3.ttf'


def model(font=None, *, binding='direct', face=0, text='fi ti fi', media='font/ttf'):
    style = TextStyle(font_family='Declared label', font_size=Length(20))
    set_font_reference(style, FontReference('font', face, extra={'own': 'retained'}))
    paragraph = Paragraph([TextRun(text, style)])
    styles = {}
    if binding == 'no-family':
        style.font_family = None
    if binding == 'inherited':
        styles['own'] = style
        paragraph = Paragraph([TextRun(text)], style_id='own')
    return DocumentModel(sections=[Section(blocks=[paragraph])], styles=styles, resources={
        'font': Resource('font', ResourceKind.FONT, media, FIXTURE.read_bytes() if font is None else font),
    })


def export(document, target, public, **options):
    if public:
        return write_document(document, target, options=ExportOptions(**options))
    if 'document_limits' in options:
        options['limits'] = options.pop('document_limits')
    return write_pdf_model(document, target, **options)


@pytest.mark.parametrize('public', [False, True])
@pytest.mark.parametrize('binding', ['direct', 'no-family', 'inherited'])
@pytest.mark.parametrize('face', [None, 0])
def test_reference_program_survives_two_json_cycles_without_system_fonts_or_subsetting(tmp_path, monkeypatch,
                                                                                     public, binding, face):
    import opendoc_formats.fonts.html_embedding as embedding

    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: FontResolver([])))

    def forbidden(*args, **kwargs):
        pytest.fail('Explicit resource program was subset')

    monkeypatch.setattr(embedding, 'subset_font', forbidden)
    document = model(binding=binding, face=face)
    font = document.resources['font'].data
    digest, pixels = hashlib.sha256(font).hexdigest(), None
    for cycle in range(2):
        document = document_from_json(document_to_json(document))
        before = document_to_json(document)
        target = tmp_path/f'cycle-{cycle}.pdf'
        report = export(document, target, public)
        assert report.success, report.issues
        assert report.metrics['font_resolution']['substitution_count'] == 0
        assert report.metrics['font_embedding']['verified_program_sha256'] == [digest]
        assert report.metrics['font_embedding']['source_bytes'] == report.metrics['font_embedding']['embedded_bytes']
        with pymupdf.open(target) as pdf:
            assert ''.join(pdf[0].get_text().split()) == 'fitifi'
            image = pdf[0].get_pixmap().samples
            assert image == (pixels or image)
            pixels = image
            assert any(pdf.extract_font(f[0])[3] == font for f in pdf[0].get_fonts(full=True))
        with PdfDocument(target) as native:
            assert {p.font_program_sha256 for p in native.page_text_placements(0)} == {digest}
        assert document_to_json(document) == before
        style = document.styles['own'] if binding == 'inherited' else document.sections[0].blocks[0].content[0].style
        assert get_font_reference(style).extra == {'own': 'retained'}


def altered_font(*, flags=None, wider=False):
    with TTFont(BytesIO(FIXTURE.read_bytes()), recalcTimestamp=False) as font:
        if flags is not None:
            font['OS/2'].fsType = flags
        if wider:
            name = font.getGlyphName(6)
            font['hmtx'].metrics[name] = (900, 0)
        output = BytesIO()
        font.save(output)
    return output.getvalue()


def test_same_family_programs_keep_distinct_actual_paint_bindings(tmp_path, monkeypatch):
    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: FontResolver([])))
    document = model(text='fi ')
    other = altered_font(wider=True)
    document.resources['other'] = Resource('other', ResourceKind.FONT, 'font/ttf', other)
    style = TextStyle(font_family='Declared label', font_size=Length(20))
    set_font_reference(style, FontReference('other', 0))
    document.sections[0].blocks[0].content.append(TextRun('ti', style))
    before = document_to_json(document)
    target = tmp_path/'two-programs.pdf'
    report = write_document(document, target)
    assert report.success, report.issues
    first, second = (hashlib.sha256(data).hexdigest() for data in (FIXTURE.read_bytes(), other))
    assert report.metrics['font_embedding']['verified_program_sha256'] == sorted([first, second])
    with PdfDocument(target) as native:
        placements = native.page_text_placements(0)
        assert {p.font_program_sha256 for p in placements} == {first, second}
        assert any(p.font_program_sha256 == first and any(g.glyph_id == 5 for g in p.glyphs) for p in placements)
        assert any(p.font_program_sha256 == second and any(g.glyph_id == 6 for g in p.glyphs) for p in placements)
    assert document_to_json(document) == before


def cff_program():
    builder = FontBuilder(1000, isTTF=False)
    names = ['.notdef', 'A', 'B']
    builder.setupGlyphOrder(names)
    builder.setupCharacterMap({65: 'A', 66: 'B'})
    builder.setupHorizontalMetrics({name: (600, 50) for name in names})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable({'familyName': 'Own CFF', 'styleName': 'Regular',
                            'fullName': 'Own CFF Regular', 'psName': 'OwnCFF-Regular'})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    strings = {}
    for name in names:
        pen = T2CharStringPen(600, None)
        pen.moveTo((50, 0))
        pen.lineTo((450, 0))
        pen.lineTo((450, 700))
        pen.closePath()
        strings[name] = pen.getCharString()
    builder.setupCFF('OwnCFF-Regular', {'FullName': 'Own CFF Regular', 'FamilyName': 'Own CFF'}, strings, {})
    builder.setupPost()
    builder.font['head'].created = builder.font['head'].modified = 3400000000
    builder.font['name'].setName('Copyright 2026 Sergei Litvinov', 0, 3, 1, 0x409)
    builder.font['name'].setName('MIT License', 13, 3, 1, 0x409)
    builder.font.recalcTimestamp = False
    output = BytesIO()
    builder.font.save(output)
    return output.getvalue()


def test_owned_otf_fixture_is_reproducible():
    assert (FIXTURE.parent/'own-cff.otf').read_bytes() == cff_program()


@pytest.mark.parametrize('public', [False, True])
def test_owned_otf_keeps_full_program_and_licensing_records(tmp_path, monkeypatch, public):
    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: FontResolver([])))
    source = cff_program()
    document = model(source, text='AB', media='font/otf')
    before = document_to_json(document)
    target = tmp_path/'own-otf.pdf'
    report = export(document, target, public)
    assert report.success, report.issues
    assert report.metrics['font_embedding']['verified_program_sha256'] == [hashlib.sha256(source).hexdigest()]
    with pymupdf.open(target) as pdf:
        assert pdf[0].get_text().strip() == 'AB'
        assert any(pdf.extract_font(f[0])[3] == source for f in pdf[0].get_fonts(full=True))
    assert document_to_json(document) == before


@pytest.mark.parametrize('public', [False, True])
@pytest.mark.parametrize('problem', ['face', 'corrupt', 'profile', 'restricted', 'bitmap-only', 'coverage', 'collection'])
def test_unusable_reference_never_substitutes_or_replaces_destination(tmp_path, monkeypatch, public, problem):
    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: FontResolver([])))
    document = model(face=1 if problem == 'face' else 0, text='Ω' if problem == 'coverage' else 'fi')
    if problem == 'corrupt':
        document.resources['font'].data = b'own invalid font'
    elif problem == 'profile':
        document.resources['font'].media_type = 'application/font-cff'
    elif problem in ('restricted', 'bitmap-only'):
        document.resources['font'].data = altered_font(flags=2 if problem == 'restricted' else 0x200)
    elif problem == 'collection':
        collection = TTCollection()
        collection.fonts = [TTFont(BytesIO(FIXTURE.read_bytes())), TTFont(BytesIO(FIXTURE.read_bytes()))]
        try:
            output = BytesIO()
            collection.save(output)
            document.resources['font'].data = output.getvalue()
        finally:
            collection.close()
    before = document_to_json(document)
    target = tmp_path/'keep.pdf'
    target.write_bytes(b'Previous destination')
    report = export(document, target, public)
    assert not report.success and any(issue.feature == 'pdf.font-reference' for issue in report.issues)
    assert target.read_bytes() == b'Previous destination' and document_to_json(document) == before


def test_forbidden_subsetting_keeps_whole_source_program(tmp_path):
    source = altered_font(flags=0x100)
    target = tmp_path/'no-subset.pdf'
    report = write_document(model(source), target)
    assert report.success, report.issues
    assert any(issue.feature == 'font-subsetting-license' for issue in report.issues)
    assert report.metrics['font_embedding']['verified_program_sha256'] == [hashlib.sha256(source).hexdigest()]


def test_ambiguous_family_without_reference_is_not_guessed(tmp_path, monkeypatch):
    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: FontResolver([])))
    document = model()
    document.sections[0].blocks[0].content[0].style = TextStyle(font_family='OwnLigature', font_size=Length(20))
    document.resources['other'] = Resource('other', ResourceKind.FONT, 'font/ttf', altered_font(wider=True))
    target = tmp_path/'keep.pdf'
    target.write_bytes(b'Previous destination')
    report = write_document(document, target)
    assert not report.success and any(issue.feature == 'pdf.font-reference' for issue in report.issues)
    assert target.read_bytes() == b'Previous destination'


@pytest.mark.parametrize('text', ['', ' '])
def test_unpainted_reference_does_not_require_an_embedded_pdf_font(tmp_path, text):
    document = model()
    document.resources['other'] = Resource('other', ResourceKind.FONT, 'font/ttf', altered_font(wider=True))
    style = TextStyle(font_family='OwnLigature', font_size=Length(20))
    set_font_reference(style, FontReference('other', 0))
    document.sections[0].blocks[0].content.append(TextRun(text, style))
    target = tmp_path/'unused.pdf'
    report = write_document(document, target)
    assert report.success, report.issues
    assert report.metrics['font_embedding']['verified_program_sha256'] == [hashlib.sha256(FIXTURE.read_bytes()).hexdigest()]


def test_program_verification_cannot_pass_by_matching_family_name(tmp_path, monkeypatch):
    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: FontResolver([])))
    original = pymupdf.Document.extract_font

    def wrong_program(self, xref, *args, **kwargs):
        name, extension, kind, data = original(self, xref, *args, **kwargs)
        return name, extension, kind, b'Own replaced program'

    monkeypatch.setattr(pymupdf.Document, 'extract_font', wrong_program)
    document = model(text='f i')
    target = tmp_path/'keep.pdf'
    target.write_bytes(b'Previous destination')
    report = write_document(document, target)
    assert not report.success and any(issue.feature == 'pdf.font-program' for issue in report.issues)
    assert target.read_bytes() == b'Previous destination'


def test_selected_font_byte_quota_is_enforced_before_workspace_io(tmp_path, monkeypatch):
    import opendoc_formats.fonts.resource_fonts as resources

    def forbidden(*args, **kwargs):
        pytest.fail('Font data was materialized beyond selected byte budget')

    monkeypatch.setattr(resources.ArtifactWorkspace, 'write_bytes', forbidden)
    document = model()
    maximum = len(FIXTURE.read_bytes())-1
    with pytest.raises(ArtifactLimitError) as error:
        write_pdf_model(document, tmp_path/'new.pdf', limits=DocumentLimits(max_embedded_bytes=maximum))
    assert error.value.quota == 'embedded bytes' and error.value.maximum == maximum
    assert error.value.path == "$.resources['font'].data"
    assert not (tmp_path/'new.pdf').exists()


def test_cancel_during_font_materialization_closes_workspace_and_preserves_input(tmp_path, monkeypatch):
    import opendoc_formats.fonts.resource_fonts as resources

    stop, paths = Event(), []
    original = resources.ArtifactWorkspace.write_bytes

    def interrupted(self, *args, **kwargs):
        path = original(self, *args, **kwargs)
        paths.append(path)
        stop.set()
        return path

    monkeypatch.setattr(resources.ArtifactWorkspace, 'write_bytes', interrupted)
    document = model()
    before = document_to_json(document)
    target = tmp_path/'keep.pdf'
    target.write_bytes(b'Previous destination')
    with pytest.raises(OperationCancelledError):
        write_pdf_model(document, target, cancelled=stop.is_set)
    assert paths and all(not path.parent.exists() for path in paths)
    assert target.read_bytes() == b'Previous destination' and document_to_json(document) == before
