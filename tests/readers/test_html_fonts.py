"""Static font-face imports preserve original programs and explicit text bindings."""

import base64
import builtins
from io import BytesIO
from threading import Event

import pytest
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable
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
    get_font_reference,
    set_font_reference,
)

from opendoc_formats import read_document, write_document
from opendoc_formats.errors import OperationCancelledError, ResourceLimitError
from opendoc_formats.fonts.resolver import FontResolver
from opendoc_formats.readers.html import read_html_model
from tests.writers.test_pdf_resource_fonts import FIXTURE, altered_font, model


def face(data=None, *, family='Own face', weight='400', slant='normal', media='font/ttf', extra='', uri=None):
    source = FIXTURE.read_bytes() if data is None else data
    uri = uri or f'data:{media};base64,'+base64.b64encode(source).decode('ascii')
    return (f'@font-face {{font-family:"{family}";src:url("{uri}") format("opentype");'
            f'font-weight:{weight};font-style:{slant};{extra}}}')


@pytest.mark.parametrize('public', [False, True])
@pytest.mark.parametrize('otf', [False, True])
def test_two_real_html_json_cycles_keep_font_program_and_binding_without_fonttools(tmp_path, monkeypatch, public, otf):
    source = (FIXTURE.parent/'own-cff.otf').read_bytes() if otf else FIXTURE.read_bytes()
    document = model(source, text='AB' if otf else 'fi ti fi', media='font/otf' if otf else 'font/ttf')
    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: FontResolver([])))
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name == 'fontTools' or name.startswith('fontTools.'):
            pytest.fail('Static HTML font cycle imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    for cycle in range(2):
        path = tmp_path/f'cycle-{cycle}.html'
        report = write_document(document, path)
        assert report.success, report.issues
        before = path.read_bytes()
        if public:
            result = read_document(path)
            assert result.success, result.issues
            document = result.document
        else:
            document = read_html_model(path)
        document = document_from_json(document_to_json(document))
        runs = document.sections[0].blocks[0].content
        assert ''.join(run.text for run in runs) == ('AB' if otf else 'fi ti fi')
        refs = [get_font_reference(run.style) for run in runs]
        assert all(ref is not None and ref.face_index == 0 for ref in refs)
        assert all(document.resources[ref.resource_id].data == source for ref in refs)
        assert len([r for r in document.resources.values() if r.kind is ResourceKind.FONT]) == 1
        assert path.read_bytes() == before


@pytest.mark.parametrize('weight,slant,markup', [('400', 'normal', 'Text'), ('700', 'normal', '<b>Text</b>'),
                                               ('400', 'italic', '<i>Text</i>'), ('700', 'italic', '<b><i>Text</i></b>')])
def test_exact_variants_and_inheritance_are_bound(tmp_path, weight, slant, markup):
    path = tmp_path/'own.html'
    path.write_text(f'<style>{face(weight=weight, slant=slant)}</style><div style="font-family:\'Own face\'">'
                    f'<p>{markup}</p></div>', encoding='utf-8')
    document = read_html_model(path)
    run = document.sections[0].blocks[0].content[0]
    ref = get_font_reference(run.style)
    assert ref is not None and document.resources[ref.resource_id].data == FIXTURE.read_bytes()


def test_same_named_distinct_programs_keep_text_associations_across_real_cycles(tmp_path, monkeypatch):
    document = model(text='fi')
    second = altered_font(wider=True)
    document.resources['other'] = Resource('other', ResourceKind.FONT, 'font/ttf', second)
    style = TextStyle(font_family='Declared label')
    set_font_reference(style, FontReference('other', 0))
    document.sections[0].blocks[0].content.append(TextRun('ti', style))
    monkeypatch.setattr(FontResolver, 'system', classmethod(lambda cls: FontResolver([])))
    for cycle in range(2):
        path = tmp_path/f'two-{cycle}.html'
        report = write_document(document, path)
        assert report.success, report.issues
        document = document_from_json(document_to_json(read_html_model(path)))
        observed = {run.text: document.resources[get_font_reference(run.style).resource_id].data
                    for run in document.sections[0].blocks[0].content}
        assert observed == {'fi': FIXTURE.read_bytes(), 'ti': second}


@pytest.mark.parametrize('duplicate', [False, True])
def test_identical_rules_deduplicate_and_conflicting_programs_are_not_guessed(tmp_path, duplicate):
    second = FIXTURE.read_bytes() if duplicate else altered_font(wider=True)
    path = tmp_path/'own.html'
    path.write_text(f'<style>{face()}{face(second)}</style><p style="font-family:\'Own face\'">fi</p>', encoding='utf-8')
    document = read_html_model(path)
    ref = get_font_reference(document.sections[0].blocks[0].content[0].style)
    assert (ref is not None) == duplicate
    assert len([r for r in document.resources.values() if r.kind is ResourceKind.FONT]) == (1 if duplicate else 2)
    if not duplicate:
        assert any('unambiguous' in warning['message'] for warning in document.metadata['html']['warnings'])


@pytest.mark.parametrize('problem', ['remote', 'local', 'corrupt', 'media', 'range', 'weight', 'multiple', 'variant'])
def test_unaccepted_profiles_keep_source_and_never_invent_reference(tmp_path, problem):
    options = {}
    if problem in {'remote', 'local'}:
        options['uri'] = 'https://example.invalid/own.ttf' if problem == 'remote' else 'file:///private/own.ttf'
    elif problem == 'corrupt':
        options['data'] = b'own invalid font'
    elif problem == 'media':
        options['media'] = 'font/otf'
    elif problem == 'range':
        options['extra'] = 'unicode-range: U+0041;'
    elif problem == 'weight':
        options['weight'] = '100 900'
    elif problem == 'multiple':
        options['extra'] = 'src:local("Own face");'
    elif problem == 'variant':
        options['slant'] = 'italic'
    path = tmp_path/'own.html'
    path.write_text(f'<style>{face(**options)}</style><p style="font-family:\'Own face\'">fi</p>', encoding='utf-8')
    before = path.read_bytes()
    document = read_html_model(path)
    assert get_font_reference(document.sections[0].blocks[0].content[0].style) is None
    assert document.metadata['html']['warnings']
    assert document.resources['html-original-source'].data == before
    assert path.read_bytes() == before


def test_unsupported_rule_for_same_family_prevents_partial_binding(tmp_path):
    path = tmp_path/'own.html'
    path.write_text(f'<style>{face()}{face(extra="unicode-range:U+0066;")}</style>'
                    '<p style="font-family:\'Own face\'">fi</p>', encoding='utf-8')
    document = read_html_model(path)
    assert get_font_reference(document.sections[0].blocks[0].content[0].style) is None


@pytest.mark.parametrize('uri', ['data:font/ttf;base64,AA=', 'data:font/ttf;base64,%%==',
                                'data:font/ttf;base64,====', 'data:font/ttf;base64,',
                                'data:font/woff;base64,AAAA', 'data:font/ttf;charset=utf-8;base64,AAAA'])
def test_malformed_or_unaccepted_payloads_do_not_create_font_resource(tmp_path, uri):
    path = tmp_path/'own.html'
    path.write_text(f'<style>{face(uri=uri)}</style><p style="font-family:\'Own face\'">fi</p>', encoding='utf-8')
    document = read_html_model(path)
    assert not any(r.kind is ResourceKind.FONT for r in document.resources.values())
    assert get_font_reference(document.sections[0].blocks[0].content[0].style) is None
    assert document.metadata['html']['warnings']


def test_font_rule_budget_fails_explicitly(tmp_path):
    path = tmp_path/'own.html'
    path.write_text('<style>'+face(uri='data:font/ttf;base64,AAAA')*1025+'</style><p>Own text</p>', encoding='utf-8')
    with pytest.raises(ResourceLimitError, match='font-face rule budget'):
        read_html_model(path)


@pytest.mark.parametrize('tag', ['fvar', 'CFF2'])
def test_variation_profiles_are_not_bound_as_static_fonts(tmp_path, tag):
    output = BytesIO()
    with TTFont(BytesIO(FIXTURE.read_bytes()), recalcTimestamp=False) as font:
        table = DefaultTable(tag)
        table.data = bytes(16)  # Presence alone excludes this profile; no variation decoding is attempted.
        font[tag] = table
        font.save(output)
    path = tmp_path/'own.html'
    path.write_text(f'<style>{face(output.getvalue())}</style><p style="font-family:\'Own face\'">fi</p>', encoding='utf-8')
    document = read_html_model(path)
    assert get_font_reference(document.sections[0].blocks[0].content[0].style) is None
    assert not any(r.kind is ResourceKind.FONT for r in document.resources.values())
    assert document.resources['html-original-source'].data == path.read_bytes()


def test_quota_precedes_base64_decode_and_duplicate_payload_uses_single_budget(tmp_path, monkeypatch):
    import opendoc_formats.readers.html_fonts as fonts

    path = tmp_path/'own.html'
    path.write_text(f'<style>{face()}{face()}</style><p style="font-family:\'Own face\'">fi</p>', encoding='utf-8')
    original, calls = fonts.base64.b64decode, []

    def decode(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(fonts.base64, 'b64decode', decode)
    maximum = len(FIXTURE.read_bytes())-1
    with pytest.raises(ArtifactLimitError) as error:
        read_html_model(path, limits=DocumentLimits(max_embedded_bytes=maximum))
    assert not calls and error.value.quota == 'embedded bytes' and error.value.maximum == maximum
    assert error.value.path == '$.html.font-face.src'
    document = read_html_model(path, limits=DocumentLimits(max_embedded_bytes=maximum+1))
    assert get_font_reference(document.sections[0].blocks[0].content[0].style) is not None and calls == [True]


def test_cancel_after_decoding_does_not_publish_resource(tmp_path, monkeypatch):
    import opendoc_formats.readers.html_fonts as fonts

    path = tmp_path/'own.html'
    path.write_text(f'<style>{face()}</style><p style="font-family:\'Own face\'">fi</p>', encoding='utf-8')
    before, stop = path.read_bytes(), Event()
    original = fonts.base64.b64decode

    def decode(*args, **kwargs):
        value = original(*args, **kwargs)
        stop.set()
        return value

    monkeypatch.setattr(fonts.base64, 'b64decode', decode)
    with pytest.raises(OperationCancelledError):
        read_html_model(path, cancelled=stop.is_set)
    assert path.read_bytes() == before
