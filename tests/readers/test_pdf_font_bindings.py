"""Production font binding uses bounded native observations without weakening identity."""

from io import BytesIO
from pathlib import Path
from threading import Event

import pymupdf
import pytest
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable
from opendoc_model import ArtifactLimitError, DocumentLimits, Resource, ResourceKind

from opendoc_formats import read_document, write_document
from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.native.sfnt import inspect_sfnt
from opendoc_formats.readers.pdf_font_bindings import painted_font_programs
from tests.binary_fixtures import own_pdf, own_placement_font
from tests.writers.test_pdf_resource_fonts import model


def resources(font, duplicate=False):
    result = {'own': Resource('own', ResourceKind.FONT, 'font/ttf', font, properties={'pdf_font_name': 'Unrelated label'})}
    if duplicate:
        result['other'] = Resource('other', ResourceKind.FONT, 'font/ttf', font)
    return result


def origins(page):
    return {(round(char[2][0], 3), round(char[2][1], 3))
            for span in page.get_texttrace() for char in span['chars']}


@pytest.mark.parametrize('rotation', [0, 90])
@pytest.mark.parametrize('mode', range(8))
@pytest.mark.parametrize('duplicate', [False, True])
def test_actual_program_origin_and_unicode_bindings_keep_fill_only_policy_and_ambiguity(rotation, mode, duplicate):
    font = own_placement_font()
    source = own_pdf(font_program=font, parent_extra=f'/Rotate {rotation} '.encode(),
                     commands=f'BT /F1 12 Tf {mode} Tr 1 .25 .5 1 60 300 Tm (ABC) Tj ET\n'.encode())[0]
    with pymupdf.open(stream=source, filetype='pdf') as pdf:
        page = pdf[0]
        before = page.get_pixmap().samples
        result = painted_font_programs(page, resources(font, duplicate), origins(page))
        if mode in {0, 2, 4, 6}:
            expected = {((round(char[2][0], 3), round(char[2][1], 3)), char[0]): {None if duplicate else 'own'}
                        for span in page.get_texttrace() if span['type'] == 0 for char in span['chars']}
            assert result == expected and {code for _, code in result} == {65, 66, 102, 105}
        else:
            assert result == {}
        assert page.rotation == rotation and page.get_pixmap().samples == before


@pytest.mark.parametrize('limits,quota,maximum', [(DocumentLimits(max_bytes=0), 'bytes', 0),
                                                (DocumentLimits(max_bytes=1), 'bytes', 1),
                                                (DocumentLimits(max_nodes=1), 'nodes', 1)])
def test_native_budget_failure_is_located_and_restores_rotation(limits, quota, maximum):
    font = own_placement_font()
    source = own_pdf(font_program=font, parent_extra=b'/Rotate 90 ',
                     commands=b'BT /F1 12 Tf 60 300 Td (AB) Tj ET BT /F1 13 Tf 60 280 Td (AB) Tj ET\n')[0]
    with pymupdf.open(stream=source, filetype='pdf') as pdf:
        page = pdf[0]
        with pytest.raises(ArtifactLimitError) as error:
            painted_font_programs(page, resources(font), origins(page), limits=limits)
        assert error.value.quota == quota and error.value.maximum == maximum
        assert error.value.path == '$.sections[0].pdf_font_bindings' and page.rotation == 90


def test_font_resource_quota_is_checked_before_native_copy(monkeypatch):
    import opendoc_formats.readers.pdf_font_bindings as bindings

    font = own_placement_font()
    source = own_pdf(font_program=font)[0]

    def forbidden(*args, **kwargs):
        pytest.fail('Native placement started before font resource quota')

    monkeypatch.setattr(bindings, 'text_placements', forbidden)
    with pymupdf.open(stream=source, filetype='pdf') as pdf:
        with pytest.raises(ArtifactLimitError) as error:
            painted_font_programs(pdf[0], resources(font), {(30, 50)},
                                  limits=DocumentLimits(max_embedded_bytes=len(font)-1))
        assert error.value.quota == 'embedded bytes' and error.value.path == "$.resources['own']"


def test_cancel_inside_native_font_copy_propagates_and_restores_rotation(monkeypatch):
    font, stop = own_placement_font(), Event()
    source = own_pdf(font_program=font, parent_extra=b'/Rotate 90 ')[0]
    original = pymupdf.mupdf.ll_fz_buffer_extract_copy

    def interrupted(*args):
        data = original(*args)
        stop.set()
        return data

    monkeypatch.setattr(pymupdf.mupdf, 'll_fz_buffer_extract_copy', interrupted)
    with pymupdf.open(stream=source, filetype='pdf') as pdf:
        page = pdf[0]
        with pytest.raises(OperationCancelledError):
            painted_font_programs(page, resources(font), origins(page), cancelled=stop.is_set)
        assert stop.is_set() and page.rotation == 90


def test_absent_native_profile_stays_unbound_and_restores_rotation(monkeypatch):
    import opendoc_formats.readers.pdf_font_bindings as bindings

    font = own_placement_font()
    source = own_pdf(font_program=font, parent_extra=b'/Rotate 90 ')[0]

    def unavailable(*args, **kwargs):
        raise AttributeError('Own unavailable native profile')

    monkeypatch.setattr(bindings, 'text_placements', unavailable)
    with pymupdf.open(stream=source, filetype='pdf') as pdf:
        page = pdf[0]
        assert painted_font_programs(page, resources(font), origins(page)) == {} and page.rotation == 90


def test_same_family_label_without_program_digest_is_never_used():
    font = own_placement_font()
    source = own_pdf(font_program=font)[0]
    with pymupdf.open(stream=source, filetype='pdf') as pdf:
        result = painted_font_programs(pdf[0], resources(font+b'own different bytes'), origins(pdf[0]))
        assert result and all(values == {None} for values in result.values())


def test_program_binding_does_not_measure_unneeded_glyph_outlines(monkeypatch):
    font = own_placement_font()
    source = own_pdf(font_program=font)[0]

    def forbidden(*args):
        pytest.fail('Font identity unnecessarily measured glyph outlines')

    monkeypatch.setattr(pymupdf.mupdf, 'fz_bound_glyph', forbidden)
    with pymupdf.open(stream=source, filetype='pdf') as pdf:
        result = painted_font_programs(pdf[0], resources(font), origins(pdf[0]))
        assert result and all(values == {'own'} for values in result.values())


def test_otf_native_cff_buffer_binds_only_to_unique_byte_exact_container(tmp_path):
    source = (Path(__file__).parents[1]/'native/data/own-cff.otf').read_bytes()
    path = tmp_path/'own.pdf'
    report = write_document(model(source, text='AB', media='font/otf'), path)
    assert report.success, report.issues
    document = read_document(path).document
    from opendoc_model import TextRun, get_font_reference, walk_model

    runs = [location.node for location in walk_model(document) if isinstance(location.node, TextRun)]
    assert runs
    for run in runs:
        reference = get_font_reference(run.style)
        assert reference is not None and document.resources[reference.resource_id].data == source
    output = BytesIO()
    with TTFont(BytesIO(source), recalcTimestamp=False) as font:
        font['head'].flags ^= 1  # Different wrapper, exactly the same CFF program.
        font.save(output)
    assert output.getvalue() != source
    with pymupdf.open(path) as pdf:
        page = pdf[0]
        programs = {'one': Resource('one', ResourceKind.FONT, 'font/otf', source),
                    'two': Resource('two', ResourceKind.FONT, 'font/otf', output.getvalue())}
        result = painted_font_programs(page, programs, origins(page))
        assert result and all(identifiers == {None} for identifiers in result.values())


@pytest.mark.parametrize('tag', ['fvar', 'CFF2'])
def test_variable_or_cff2_wrapper_cannot_borrow_static_cff_binding(tmp_path, tag):
    source = (Path(__file__).parents[1]/'native/data/own-cff.otf').read_bytes()
    path = tmp_path/'own.pdf'
    assert write_document(model(source, text='AB', media='font/otf'), path).success
    output = BytesIO()
    with TTFont(BytesIO(source), recalcTimestamp=False) as font:
        table = DefaultTable(tag)
        table.data = bytes(16)
        font[tag] = table
        font.save(output)
    with pymupdf.open(path) as pdf:
        candidate = Resource('own', ResourceKind.FONT, 'font/otf', output.getvalue())
        original_cff = next(t.sha256 for t in inspect_sfnt(source).tables if t.tag == 'CFF ')
        assert next(t.sha256 for t in inspect_sfnt(candidate.data).tables if t.tag == 'CFF ') == original_cff
        result = painted_font_programs(pdf[0], {'own': candidate}, origins(pdf[0]))
        assert result and all(identifiers == {None} for identifiers in result.values())
