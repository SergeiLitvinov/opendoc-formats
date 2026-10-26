"""Name selection parity with the established engine, including conservative recovery fallback."""

import builtins
import struct
from io import BytesIO
from threading import Event

import pytest
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError
from opendoc_formats.fonts.resolver import _read_face
from opendoc_formats.fonts.resource_fonts import font_program_names
from opendoc_formats.fonts.sfnt_names import read_program_names
from opendoc_formats.support.cancellation import cancellation_scope
from tests.binary_fixtures import own_placement_font
from tests.test_native_font_face import engine_face


def records(platform=3, encoding=1, language=0x409, prefix='Own', codec='utf-16-be'):
    return [(platform, encoding, language, identifier, (prefix+suffix).encode(codec))
            for identifier, suffix in ((1, ' Family'), (4, ' Full'), (6, '-Regular'), (16, ' Typographic'))]


def name_font(values, *, version=0, languages=()):
    strings, entries = bytearray(), bytearray()
    for platform, encoding, language, identifier, text in values:
        entries.extend(struct.pack('>6H', platform, encoding, language, identifier, len(text), len(strings)))
        strings.extend(text)
    extra = bytearray()
    if version == 1:
        extra.extend(struct.pack('>H', len(languages)))
        for language in languages:
            encoded = language.encode('utf-16-be')
            extra.extend(struct.pack('>2H', len(encoded), len(strings)))
            strings.extend(encoded)
    table = struct.pack('>3H', version, len(values), 6+len(entries)+len(extra))+entries+extra+strings
    return struct.pack('>4s4H4sIII', b'\0\1\0\0', 1, 16, 0, 0, b'name', 0, 28, len(table))+table


def reference_names(data):
    with TTFont(BytesIO(data), lazy=True) as font:
        names = font['name']
        family = names.getDebugName(16) or names.getDebugName(1)
        if not family:
            raise ValueError('Font program has no family name')
        if not names.getDebugName(4):
            raise ValueError('Word font program requires a full font name')
        return family, tuple(value for identifier in (1, 4, 6, 16) if (value := names.getDebugName(identifier)))


@pytest.mark.parametrize('source', [
    own_placement_font(),
    name_font(records()),
    name_font(records(0, 4, 0, 'Текст 🦊')),
    name_font(records(1, 0, 0, 'Café', 'mac_roman')+records(prefix='Windows')),
    name_font(records(language=0x40c, prefix='French')+records(0, 3, 0, 'Last')),
    name_font(records(prefix='First')+records(prefix='Second')),
    name_font([(3, 2, 0x411, 0, b'\xff')]+records()),  # Unused copyright encoding is not decoded.
    name_font(records(), version=1),
    name_font(records(0, 4, 0x8000, 'Tagged'), version=1, languages=('en',)),
    name_font(records(0, 4, 0x8000, 'English')+records(0, 4, 0x8001, 'French'),
              version=1, languages=('en', 'fr')),
    name_font(records(0, 4, 0x8000, 'Tagged')+records(prefix='Numeric English'), version=1, languages=('en',)),
    name_font(records(3, 2, 0x411, '日本', 'shift_jis')),
    name_font(records(3, 3, 0x804, '字体', 'gb2312')),
    name_font(records(3, 4, 0x404, '字體', 'big5')),
    name_font(records(3, 5, 0x412, '글꼴', 'euc_kr')),
    name_font(records(3, 6, 0x412, '글꼴', 'johab')),
    name_font(records(1, 0, 1, 'Café', 'mac_roman')+records(prefix='English')),
    name_font(records(1, 0, 0, 'First', 'mac_roman')+records(1, 7, 0, 'Last', 'mac_cyrillic')),
    name_font(records(2, 0, 0, 'Own', 'ascii')),
    name_font(records(2, 1, 0, 'Текст 🦊', 'utf-16-be')),
    name_font(records(2, 2, 0, 'Café', 'latin1')),
])
def test_native_names_match_engine_and_do_not_import_it(source, monkeypatch):
    expected = reference_names(source)
    original = builtins.__import__

    def no_engine(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Ordinary name table imported the font engine')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_engine)
    assert font_program_names(source) == expected


@pytest.mark.parametrize('encoding,language', [
    (0, 0), (0, 1), (0, 15), (0, 17), (0, 18),
    (0, 24), (0, 25), (0, 26), (0, 27), (0, 28), (0, 36), (0, 37),
    (0, 38), (0, 39), (0, 40), (6, 14), (7, 32), (29, 0), (35, 0), (37, 0),
])
def test_mac_single_byte_repertoire_matches_engine_without_import(encoding, language, monkeypatch):
    # Every non-NUL byte, including language-dependent differences; no re-encoding shortcuts.
    source = name_font([(1, encoding, language, identifier, bytes(range(1, 256))) for identifier in (1, 4, 6, 16)])
    expected = reference_names(source)
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Single-byte names imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert font_program_names(source) == expected


@pytest.mark.parametrize('encoding,codec', [(1, 'x_mac_japanese'), (2, 'x_mac_trad_chinese'),
                                          (3, 'x_mac_korean'), (25, 'x_mac_simp_chinese')])
def test_mac_cjk_standard_repertoire_matches_engine_without_import(encoding, codec, monkeypatch):
    # Enumerate every strictly decodable single/two-byte unit, independently of the reader.
    # Separators keep neighbouring units from forming different multibyte sequences.
    units = []
    for size in (1, 2):
        for number in range(256**size):
            raw = number.to_bytes(size, 'big')
            if b'\0' in raw:
                continue
            try:
                raw.decode(codec)
            except UnicodeDecodeError:
                continue
            units.append(raw)
    sources = [name_font([(1, encoding, 0, identifier, b'|'.join(units[start:start+4000]))
                          for identifier in (1, 4, 6, 16)]) for start in range(0, len(units), 4000)]
    expected = [reference_names(source) for source in sources]
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Standard Macintosh CJK names imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert [font_program_names(source) for source in sources] == expected


@pytest.mark.parametrize('encoding,raw', [(1, b'\x80'), (1, b'\xfc'), (2, b'\xff'),
                                        (3, b'\x81'), (25, b'\x80')])
def test_mac_cjk_extensions_keep_engine_recovery(encoding, raw, monkeypatch):
    import opendoc_formats.fonts.resource_fonts as module

    source = name_font([(1, encoding, 0, identifier, b'Own'+raw) for identifier in (1, 4, 6, 16)])
    expected, original, calls = reference_names(source), module._fonttools_program_names, []

    def fallback(data):
        calls.append(data)
        return original(data)

    monkeypatch.setattr(module, '_fonttools_program_names', fallback)
    assert font_program_names(source) == expected and calls == [source]


def test_mac_cjk_names_charge_decoded_bytes_before_returning():
    count, length = 2200, 4096
    table = (struct.pack('>3H', 0, count, 6+12*count)
             + struct.pack('>6H', 1, 1, 11, 1, length, 0)*count+b'\x93\xfa'*(length//2))
    source = struct.pack('>4s4H4sIII', b'\0\1\0\0', 1, 16, 0, 0, b'name', 0, 28, len(table))+table
    with pytest.raises(ResourceLimitError, match='decoded-byte'):
        read_program_names(source)


def test_mac_cjk_cancel_during_records_never_enters_engine(monkeypatch):
    import opendoc_formats.fonts.sfnt_names as native

    source = name_font(records(1, 1, 11, '日本', 'shift_jis'))
    stop, calls, original = Event(), [], native.checkpoint

    def cancel():
        calls.append(True)
        if len(calls) == 2:
            stop.set()
        original()

    def forbidden(data):
        pytest.fail('Cancelled CJK names entered fontTools fallback')

    monkeypatch.setattr(native, 'checkpoint', cancel)
    monkeypatch.setattr('opendoc_formats.fonts.resource_fonts._fonttools_program_names', forbidden)
    with cancellation_scope(stop.is_set, 'CJK names'):
        with pytest.raises(OperationCancelledError):
            font_program_names(source)
        stop.clear()
    assert len(calls) == 2


@pytest.mark.parametrize('name_source', [
    name_font(records(1, 1, 11, '日本', 'shift_jis')),
    name_font(records(1, 2, 19, '字體', 'big5')),
    name_font(records(1, 3, 23, '한글', 'euc_kr')),
    name_font(records(1, 25, 33, '字体', 'gb2312')),
    name_font(records(0, 4, 0x8000, 'Tagged'), version=1, languages=('en',)),
    name_font(records(3, 2, 0x411, '日本', 'shift_jis')),
    name_font(records(1, 7, 32, 'Шрифт', 'mac_cyrillic')),
    name_font(records(1, 0, 17, 'Şİğ', 'mac_turkish')),
])
def test_complete_face_uses_new_name_profiles_without_fonttools(tmp_path, monkeypatch, name_source):
    path = tmp_path/'own.ttf'
    with TTFont(BytesIO(own_placement_font()), recalcTimestamp=False) as font:
        names = DefaultTable('name')
        names.data = name_source[28:]
        font['name'] = names
        font.save(path)
    expected, before = engine_face(path), path.read_bytes()
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Supported name profile entered fontTools from full resolver')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert _read_face(path) == expected
    assert path.read_bytes() == before


@pytest.mark.parametrize('identifier', [1, 4, 6, 16])
def test_empty_english_record_keeps_existing_selection_and_validation(identifier):
    values = records(language=0x40c, prefix='French')
    values.append((3, 1, 0x409, identifier, b''))
    source = name_font(values)
    if identifier == 4:
        with pytest.raises(ValueError, match='full font name'):
            font_program_names(source)
    else:
        assert font_program_names(source) == reference_names(source)


@pytest.mark.parametrize('source', [
    name_font([(1, 1, 11, identifier, b'Own\x80') for identifier in (1, 4, 6, 16)]),
    name_font(records(0, 4, 0x8001, 'Missing tag'), version=1, languages=('en',)),
    name_font([(3, 1, 0x409, 16, b'\x00AB')]+records()),
    name_font([(3, 1, 0x409, 16, b'\x00\x00\x00A\x00\x00\x00B')]+records()),
])
def test_unfamiliar_or_recovery_profiles_keep_engine_result(source, monkeypatch):
    import opendoc_formats.fonts.resource_fonts as module

    expected = reference_names(source)
    original = module._fonttools_program_names
    calls = []

    def fallback(data):
        calls.append(data)
        return original(data)

    monkeypatch.setattr(module, '_fonttools_program_names', fallback)
    assert font_program_names(source) == expected and calls == [source]


def test_compressed_program_keeps_previous_optional_reader():
    stream = BytesIO()
    with TTFont(BytesIO(own_placement_font()), recalcTimestamp=False) as font:
        font.flavor = 'woff'
        font.save(stream)
    source = stream.getvalue()
    assert font_program_names(source) == reference_names(source)


def test_missing_required_names_are_rejected_without_guessing():
    for values, message in [(records()[1:3], 'family name'), (records()[:1], 'full font name')]:
        with pytest.raises(ValueError, match=message):
            font_program_names(name_font(values))


def test_bad_unselected_string_range_uses_existing_lazy_reader_without_partial_native_result(monkeypatch):
    import opendoc_formats.fonts.resource_fonts as module

    source = bytearray(name_font([(3, 1, 0, 0, b'')]+records()))
    struct.pack_into('>H', source, 28+6+10, 65535)
    original = module._fonttools_program_names
    calls = []

    def fallback(data):
        calls.append(True)
        return original(data)

    monkeypatch.setattr(module, '_fonttools_program_names', fallback)
    assert font_program_names(bytes(source)) == reference_names(bytes(source)) and calls


def test_native_record_and_shared_string_work_budgets_are_bounded():
    with pytest.raises(ResourceLimitError, match='record budget'):
        read_program_names(name_font([(0, 4, 0, 0, b'')]*4097))
    count, length = 2200, 4096
    table = (struct.pack('>3H', 0, count, 6+12*count)
             + struct.pack('>6H', 0, 4, 0, 1, length, 0)*count+b'\0A'*(length//2))
    source = struct.pack('>4s4H4sIII', b'\0\1\0\0', 1, 16, 0, 0, b'name', 0, 28, len(table))+table
    with pytest.raises(ResourceLimitError, match='decoded-byte'):
        read_program_names(source)


def test_language_tag_offsets_counts_and_utf16_recovery_are_bounded(monkeypatch):
    import opendoc_formats.fonts.resource_fonts as module

    source = bytearray(name_font(records(0, 4, 0x8000), version=1, languages=('en',)))
    tag_record = 28+6+4*12+2
    struct.pack_into('>H', source, tag_record+2, 65535)
    with pytest.raises(InvalidDocumentError, match='storage'):
        read_program_names(bytes(source))
    source = bytearray(name_font(records(), version=1))
    struct.pack_into('>H', source, 28+6+4*12, 4097)
    with pytest.raises(ResourceLimitError, match='language-tag'):
        read_program_names(bytes(source))
    source = bytearray(name_font(records(0, 4, 0x8000), version=1, languages=('en',)))
    struct.pack_into('>H', source, tag_record, 1)  # Odd UTF-16 requires established recovery behavior.
    original = module._fonttools_program_names
    calls = []

    def fallback(data):
        calls.append(True)
        return original(data)

    monkeypatch.setattr(module, '_fonttools_program_names', fallback)
    assert font_program_names(bytes(source)) == reference_names(bytes(source)) and calls


def test_cancel_during_native_name_walk_propagates_without_engine_fallback(monkeypatch):
    import opendoc_formats.fonts.resource_fonts as module
    import opendoc_formats.fonts.sfnt_names as native

    stop = Event()
    original = native.checkpoint

    def cancel():
        stop.set()
        original()

    def forbidden(data):
        pytest.fail('Cancellation started an optional font reader')

    monkeypatch.setattr(module, '_fonttools_program_names', forbidden)
    with cancellation_scope(stop.is_set, 'Own font names'):
        with monkeypatch.context() as context:
            context.setattr(native, 'checkpoint', cancel)
            with pytest.raises(OperationCancelledError):
                font_program_names(name_font(records()))
        stop.clear()
    assert font_program_names(name_font(records())) == reference_names(name_font(records()))
