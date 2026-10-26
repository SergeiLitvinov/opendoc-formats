"""Complete finite face metadata without fontTools imports; established profiles remain available."""

import builtins
import struct
from io import BytesIO
from threading import Event

import pytest
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.DefaultTable import DefaultTable

from opendoc_formats.errors import OperationCancelledError, UnsupportedDocumentError
from opendoc_formats.fonts.resolver import FontFace, _read_face
from opendoc_formats.native.sfnt import inspect_sfnt, read_face_metrics
from opendoc_formats.support.cancellation import cancellation_scope
from tests.binary_fixtures import own_placement_font


def engine_face(path, *, face_index=0):
    with TTFont(path, lazy=True, fontNumber=face_index) as font:
        names, os2, head = font['name'], font.get('OS/2'), font.get('head')
        flags = int(getattr(os2, 'fsType', 0))
        return FontFace(
            family=names.getDebugName(16) or names.getDebugName(1) or path.stem, path=path,
            weight=int(getattr(os2, 'usWeightClass', 400)), italic=bool(getattr(font.get('post'), 'italicAngle', 0)),
            width_class=int(getattr(os2, 'usWidthClass', 5)), units_per_em=int(getattr(head, 'unitsPerEm', 1000)),
            average_width=float(getattr(os2, 'xAvgCharWidth', 500) or 500),
            glyphs=frozenset((font.getBestCmap() or {}).keys()), embeddable=not bool(flags & (2 | 0x200)),
            subsettable=not bool(flags & 0x100),
        )


def program(*, version=3, flags=0, post_version=2, angle=0, average=0, weight=700, width=7):
    with TTFont(BytesIO(own_placement_font()), recalcTimestamp=False) as font:
        raw = bytearray(font.getTableData('OS/2'))
        size = {0: 78, 1: 86, 2: 96, 3: 96, 4: 96, 5: 100}[version]
        raw.extend(bytes(max(0, size-len(raw))))
        struct.pack_into('>Hh3H', raw, 0, version, average, weight, width, flags)
        os2 = DefaultTable('OS/2')
        os2.data = bytes(raw[:size])
        font['OS/2'] = os2
        font['post'].formatType = post_version
        font['post'].italicAngle = angle
        output = BytesIO()
        font.save(output)
        return output.getvalue()


@pytest.mark.parametrize('version', range(6))
@pytest.mark.parametrize('flags', [0, 2, 4, 8, 0x100, 0x200, 0x10a])
def test_all_os2_versions_and_permission_flags_match_engine_without_importing_it(tmp_path, monkeypatch, version, flags):
    path = tmp_path/'own.ttf'
    source = program(version=version, flags=flags, angle=-12.5 if flags else 0, average=-200 if flags else 0)
    path.write_bytes(source)
    expected = engine_face(path)
    original = builtins.__import__

    def no_engine(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Supported static face imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_engine)
    assert _read_face(path) == expected
    assert path.read_bytes() == source


@pytest.mark.parametrize('post_version', [1, 2, 3])
def test_supported_post_versions_preserve_face_fields(tmp_path, post_version):
    path = tmp_path/'own.ttf'
    path.write_bytes(program(post_version=post_version))
    assert _read_face(path) == engine_face(path)


def post4_program(*, codes=(0xffff, 65, 66, 0xfb01), flags=0, angle=0):
    source = program(flags=flags, angle=angle)
    with TTFont(BytesIO(source), recalcTimestamp=False) as font:
        header = bytearray(font.getTableData('post')[:32])
        struct.pack_into('>I', header, 0, 0x40000)
        table = DefaultTable('post')
        table.data = bytes(header)+struct.pack('>'+'H'*len(codes), *codes)
        font['post'] = table
        output = BytesIO()
        font.save(output)
    return output.getvalue()


@pytest.mark.parametrize('codes', [(0xffff, 65, 66, 0xfb01), (0, 0, 0, 0), (0xd800, 0xfffe, 0xffff, 65)])
@pytest.mark.parametrize('flags', [0, 2, 0x100, 0x200, 0x10a])
def test_post4_complete_face_matches_engine_without_fonttools(tmp_path, monkeypatch, codes, flags):
    path = tmp_path/'own.ttf'
    source = post4_program(codes=codes, flags=flags, angle=-12.5 if flags else 0)
    path.write_bytes(source)
    expected = engine_face(path)
    original = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Native post 4 face imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', forbidden)
    assert _read_face(path) == expected
    # Printer codes, including surrogate-like values, are never used as cmap evidence.
    assert expected.glyphs == frozenset((65, 66, 0xfb01))
    assert path.read_bytes() == source


@pytest.mark.parametrize('codes', [(), (65,), (65, 66, 67, 68, 69)])
def test_post4_noncanonical_array_keeps_lazy_engine_recovery(tmp_path, monkeypatch, codes):
    path = tmp_path/'legacy.ttf'
    source = post4_program(codes=codes)
    path.write_bytes(source)
    expected, original, calls = engine_face(path), TTFont.__init__, []

    def engine(self, *args, **kwargs):
        calls.append(True)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(TTFont, '__init__', engine)
    with pytest.raises(UnsupportedDocumentError, match='format 4'):
        read_face_metrics(source)
    assert _read_face(path) == expected and calls == [True]
    assert path.read_bytes() == source


def test_owned_cff_otf_maxp_half_profile_matches_engine_without_import(tmp_path, monkeypatch):
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.t2CharStringPen import T2CharStringPen

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
    path = tmp_path/'own.otf'
    builder.save(path)
    assert path.read_bytes().startswith(b'OTTO')
    expected = engine_face(path)
    original = builtins.__import__

    def no_engine(name, *args, **kwargs):
        if name.startswith('fontTools'):
            pytest.fail('Static CFF face imported fontTools')
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_engine)
    assert _read_face(path) == expected


def test_unknown_metrics_profile_keeps_existing_engine_result(tmp_path, monkeypatch):
    import opendoc_formats.fonts.resolver as module

    path = tmp_path/'own.ttf'
    path.write_bytes(program())
    expected = engine_face(path)
    original = module.read_face_metrics

    def outside_profile(data, **kwargs):
        raise UnsupportedDocumentError('Exercise established reader')

    monkeypatch.setattr(module, 'read_face_metrics', outside_profile)
    assert _read_face(path) == expected
    monkeypatch.setattr(module, 'read_face_metrics', original)


def test_post_pascal_storage_is_bounded_before_native_face_is_accepted():
    source = bytearray(program())
    post = next(table for table in inspect_sfnt(bytes(source)).tables if table.tag == 'post')
    # An index beyond the supplied Pascal-string storage must leave the native profile.
    struct.pack_into('>H', source, post.offset+34, 65535)
    with pytest.raises(UnsupportedDocumentError, match='Pascal'):
        read_face_metrics(bytes(source))


def test_missing_permission_table_does_not_infer_native_embedding_rights(tmp_path):
    path = tmp_path/'legacy.ttf'
    with TTFont(BytesIO(own_placement_font()), recalcTimestamp=False) as font:
        del font['OS/2']
        font.save(path)
    with pytest.raises(UnsupportedDocumentError, match='OS/2'):
        read_face_metrics(path.read_bytes())
    assert _read_face(path) == engine_face(path)


def test_cancelled_native_face_does_not_import_engine(tmp_path, monkeypatch):
    import opendoc_formats.fonts.resolver as module

    path = tmp_path/'own.ttf'
    path.write_bytes(program())
    stop = Event()
    original = module.read_face_metrics

    def cancel(data, **kwargs):
        stop.set()
        return original(data, **kwargs)

    monkeypatch.setattr(module, 'read_face_metrics', cancel)
    with cancellation_scope(stop.is_set, 'Own face'):
        with pytest.raises(OperationCancelledError):
            _read_face(path)
        stop.clear()
