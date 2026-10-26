"""Resource fonts survive self-contained HTML export without a font engine."""

import base64
import builtins
import hashlib
import re
from threading import Event

import pytest
from opendoc_model import (
    ArtifactLimitError,
    DocumentLimits,
    FontReference,
    Resource,
    ResourceKind,
    TextRun,
    TextStyle,
    document_from_json,
    document_to_json,
    set_font_reference,
)

from opendoc_formats import write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.fonts.resolver import FontResolver
from opendoc_formats.writers.html_writer import write_html_model
from tests.writers.test_pdf_resource_fonts import FIXTURE, altered_font, model


def embedded_fonts(html):
    pattern = (r'@font-face\s*\{ font-family: "([^"]+)"; src: url\("data:([^;]+);base64,([^"]+)"\) '
               r'format\("([^"]+)"\);')
    return [(family, media, base64.b64decode(data, validate=True), kind)
            for family, media, data, kind in re.findall(pattern, html)]


@pytest.mark.parametrize('public', [False, True])
@pytest.mark.parametrize('binding', ['direct', 'no-family', 'inherited'])
@pytest.mark.parametrize('face', [None, 0])
@pytest.mark.parametrize('otf', [False, True])
def test_full_program_and_binding_survive_two_json_cycles_without_engine(tmp_path, monkeypatch,
                                                                        public, binding, face, otf):
    source = (FIXTURE.parent/'own-cff.otf').read_bytes() if otf else FIXTURE.read_bytes()
    document = model(source, binding=binding, face=face, text='AB' if otf else 'fi ti fi',
                     media='font/otf' if otf else 'font/ttf')
    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: FontResolver([])))
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name == 'fontTools' or name.startswith('fontTools.'):
            pytest.fail('HTML resource font export imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    writer = write_document if public else write_html_model
    for cycle in range(2):
        document = document_from_json(document_to_json(document))
        before = document_to_json(document)
        target = tmp_path/f'cycle-{cycle}.html'
        report = writer(document, target)
        assert report.success, report.issues
        assert report.metrics['font_resolution']['substitution_count'] == 0
        html = target.read_text(encoding='utf-8')
        fonts = embedded_fonts(html)
        alias = 'ODF Embedded '+hashlib.sha256(source).hexdigest()[:12]
        assert fonts == [(alias, 'font/otf' if otf else 'font/ttf', source, 'opentype' if otf else 'truetype')]
        assert f'font-family:&quot;{alias}&quot;' in html
        assert 'AB' in html if otf else 'fi ti fi' in html
        assert report.metrics['font_embedding']['source_bytes'] == len(source)
        assert report.metrics['font_embedding']['embedded_bytes'] == len(source)
        assert document_to_json(document) == before


@pytest.mark.parametrize('public', [False, True])
@pytest.mark.parametrize('problem', ['face', 'corrupt', 'profile', 'restricted', 'bitmap-only', 'coverage'])
def test_invalid_reference_cannot_silently_substitute_or_replace_output(tmp_path, monkeypatch, public, problem):
    document = model(face=1 if problem == 'face' else 0, text='Ω' if problem == 'coverage' else 'fi')
    if problem == 'corrupt':
        document.resources['font'].data = b'own invalid font'
    elif problem == 'profile':
        document.resources['font'].media_type = 'application/font-cff'
    elif problem in ('restricted', 'bitmap-only'):
        document.resources['font'].data = altered_font(flags=2 if problem == 'restricted' else 0x200)
    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: FontResolver([])))
    before = document_to_json(document)
    target = tmp_path/'keep.html'
    target.write_bytes(b'Previous destination')
    report = (write_document if public else write_html_model)(document, target)
    assert not report.success and any(issue.feature == 'html.font-reference' for issue in report.issues)
    assert target.read_bytes() == b'Previous destination' and document_to_json(document) == before


def test_same_named_programs_keep_distinct_css_bindings(tmp_path, monkeypatch):
    document = model(text='fi ')
    second = altered_font(wider=True)
    document.resources['other'] = Resource('other', ResourceKind.FONT, 'font/ttf', second)
    style = TextStyle(font_family='Declared label')
    set_font_reference(style, FontReference('other', 0))
    document.sections[0].blocks[0].content.append(TextRun('ti', style))
    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: FontResolver([])))
    target = tmp_path/'own.html'
    report = write_document(document, target)
    assert report.success, report.issues
    html = target.read_text(encoding='utf-8')
    fonts = embedded_fonts(html)
    assert {font[2] for font in fonts} == {FIXTURE.read_bytes(), second}
    assert len({font[0] for font in fonts}) == 2
    for family, _, _, _ in fonts:
        assert f'font-family:&quot;{family}&quot;' in html


def test_ambiguous_family_without_reference_is_not_guessed(tmp_path, monkeypatch):
    document = model()
    document.sections[0].blocks[0].content[0].style = TextStyle(font_family='OwnLigature')
    document.resources['other'] = Resource('other', ResourceKind.FONT, 'font/ttf', altered_font(wider=True))
    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: FontResolver([])))
    target = tmp_path/'new.html'
    report = write_document(document, target)
    assert not report.success and any(issue.feature == 'html.font-reference' for issue in report.issues)
    assert not target.exists()


def test_font_quota_precedes_materialization(tmp_path, monkeypatch):
    import opendoc_formats.fonts.resource_fonts as resources

    def forbidden(*args, **kwargs):
        pytest.fail('Font byte quota checked after materialization')

    monkeypatch.setattr(resources.ArtifactWorkspace, 'write_bytes', forbidden)
    maximum = len(FIXTURE.read_bytes())-1
    with pytest.raises(ArtifactLimitError) as error:
        write_html_model(model(), tmp_path/'new.html', limits=DocumentLimits(max_embedded_bytes=maximum))
    assert error.value.quota == 'embedded bytes' and error.value.maximum == maximum
    assert error.value.path == "$.resources['font'].data"
    assert not (tmp_path/'new.html').exists()


def test_cancel_during_materialization_cleans_workspace(tmp_path, monkeypatch):
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
    target = tmp_path/'keep.html'
    target.write_bytes(b'Previous destination')
    with pytest.raises(OperationCancelledError):
        write_html_model(document, target, cancelled=stop.is_set)
    assert paths and all(not path.parent.exists() for path in paths)
    assert target.read_bytes() == b'Previous destination' and document_to_json(document) == before
