"""Exercise the installed wheel in an isolated interpreter, without importing the checkout."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import struct
import sys
import zipfile
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory


def diagnostics_smoke() -> None:
    from opendoc_model import (
        DiagnosticIssue,
        IssueSeverity,
        Provenance,
        document_from_json,
        document_to_json,
        integration_from_dict,
    )

    from opendoc_formats.support.document_adapters import document_to_text, text_to_document
    from opendoc_formats.support.text_diagnostics import append_text_warning
    from opendoc_formats.types import DocFormat, Text

    text = Text(plain='Own portable text', source_format=DocFormat.PDF)
    append_text_warning(text, DiagnosticIssue(
        'pdf.own-source-warning', IssueSeverity.LOSS, 'Own uncertainty', 'own.pdf#page=2',
        reason='own-source-unassessed',
    ), Provenance('pdf', 'own.pdf', page=2))
    for _ in range(2):
        restored = document_to_text(document_from_json(document_to_json(text_to_document(text))))
        assert restored.diagnostics == text.diagnostics
        assert restored.warnings == text.warnings and not restored.diagnostics.assessment_complete
        assert integration_from_dict(restored.to_dict()['diagnostics']) == text.diagnostics
        text = restored


def anatomy_smoke() -> None:
    from opendoc_model import Length, TextStyle

    from opendoc_formats.anatomy import compare_snapshots, inspect_binary
    from opendoc_formats.fonts.resolver import _read_face
    from opendoc_formats.fonts.resource_fonts import font_program_names
    from opendoc_formats.fonts.sfnt_cmap import read_unicode_coverage, read_unicode_mapping
    from opendoc_formats.fonts.sfnt_ligatures import read_ligature_mapping
    from opendoc_formats.fonts.word_metrics import word_line_ascent, word_line_descent
    from opendoc_formats.native.epub import local_path
    from opendoc_formats.native.sfnt import inspect_sfnt, inspect_sfnt_checksums, inspect_sfnt_structure, read_face_metrics

    assert local_path('OPS/book.opf', 'Text/%F0%9F%A6%8A#part') == 'OPS/Text/🦊'
    assert local_path('OPS/book.opf', 'Text/%252F') == 'OPS/Text/%2F'
    for ambiguous in ('Text/%FF', 'Text/own%', 'Text%2Fown', 'Text/own?query'):
        try:
            local_path('OPS/book.opf', ambiguous)
        except ValueError:
            pass
        else:
            raise AssertionError('Ambiguous EPUB URL was silently resolved')

    font = struct.pack('>4s4H4sIII', b'\0\1\0\0', 1, 16, 0, 0, b'OWN ', 0, 28, 3)+b'Own\0'
    font_inventory = inspect_sfnt(font, capture=True)
    assert font_inventory.source_sha256 == hashlib.sha256(font).hexdigest()
    assert font_inventory.tables[0].payload == b'Own' and font_inventory.tables[0].offset == 28
    assert not font_inventory.assessment_complete
    checksums = inspect_sfnt_checksums(font)
    assert checksums.tables[0].computed == 0x4f776e00 and not checksums.tables[0].valid
    assert checksums.adjustment_valid is None and not checksums.assessment_complete
    assert not inspect_sfnt_structure(font).findings
    damaged_padding = font[:-1]+b'\1'
    assert inspect_sfnt_structure(damaged_padding).findings[0].code == 'sfnt.padding.nonzero'
    structured = inspect_binary(damaged_padding, capture=True, sfnt_structure=True)
    assert structured.items[0].payload == damaged_padding
    assert dict(structured.details)['structure']['findings'][0]['code'] == 'sfnt.padding.nonzero'
    font_snapshot = inspect_binary(font, capture=True)
    assert font_snapshot.container == 'sfnt' and font_snapshot.items[0].payload == font
    assert font_snapshot.items[1].payload == b'Own'
    audited_snapshot = inspect_binary(font, sfnt_checksums=True)
    assert dict(audited_snapshot.details)['checksums']['source_sha256'] == font_snapshot.source_sha256
    assert dict(audited_snapshot.details)['checksums']['tables'][0]['computed'] == 0x4f776e00

    names = ((1, 'Own Family'), (4, 'Own Full'), (6, 'Own-Regular'), (16, 'Own Typographic'))
    name_records, strings = bytearray(), bytearray()
    for identifier, value in names:
        encoded = value.encode('utf-16-be')
        name_records.extend(struct.pack('>6H', 3, 1, 0x409, identifier, len(encoded), len(strings)))
        strings.extend(encoded)
    name_table = struct.pack('>3H', 0, len(names), 6+len(name_records))+name_records+strings
    name_program = (struct.pack('>4s4H4sIII', b'\0\1\0\0', 1, 16, 0, 0, b'name', 0, 28, len(name_table))+name_table)
    assert font_program_names(name_program) == ('Own Typographic', tuple(value for _, value in names))
    tagged_records = bytearray(name_records)
    for number in range(len(names)):
        struct.pack_into('>H', tagged_records, 12*number+4, 0x8000)
    tagged_table = (struct.pack('>3H', 1, len(names), 6+len(tagged_records)+6)+tagged_records
                    +struct.pack('>3H', 1, 4, len(strings))+strings+b'\0e\0n')
    tagged_program = struct.pack('>4s4H4sIII', b'\0\1\0\0', 1, 16, 0, 0, b'name', 0, 28, len(tagged_table))+tagged_table
    assert font_program_names(tagged_program) == ('Own Typographic', tuple(value for _, value in names))
    legacy_records, legacy_strings = bytearray(), bytearray()
    legacy_names = [(identifier, '日本 '+value if identifier != 6 else value) for identifier, value in names]
    for identifier, value in legacy_names:
        encoded = value.encode('shift_jis')
        legacy_records.extend(struct.pack('>6H', 3, 2, 0x411, identifier, len(encoded), len(legacy_strings)))
        legacy_strings.extend(encoded)
    legacy_table = struct.pack('>3H', 0, len(names), 6+len(legacy_records))+legacy_records+legacy_strings
    legacy_program = struct.pack('>4s4H4sIII', b'\0\1\0\0', 1, 16, 0, 0, b'name', 0, 28, len(legacy_table))+legacy_table
    assert font_program_names(legacy_program) == ('日本 Own Typographic', tuple(value for _, value in legacy_names))
    for platform, encoding, language, prefix, codec in (
        (1, 7, 32, 'Шрифт', 'mac_cyrillic'),
        (1, 0, 17, 'Şİğ', 'mac_turkish'),
        (2, 2, 0, 'Café', 'latin1'),
    ):
        portable_records, portable_strings = bytearray(), bytearray()
        portable_names = [(identifier, prefix+value) for identifier, value in names]
        for identifier, value in portable_names:
            encoded = value.encode(codec)
            portable_records.extend(struct.pack('>6H', platform, encoding, language, identifier,
                                                len(encoded), len(portable_strings)))
            portable_strings.extend(encoded)
        portable_table = struct.pack('>3H', 0, len(names), 6+len(portable_records))+portable_records+portable_strings
        portable_font = struct.pack('>4s4H4sIII', b'\0\1\0\0', 1, 16, 0, 0, b'name', 0, 28, len(portable_table))+portable_table
        assert font_program_names(portable_font) == (prefix+'Own Typographic', tuple(value for _, value in portable_names))

    subtable = struct.pack('>HH6I', 12, 0, 28, 0, 1, 0x1f600, 0x1f602, 1)
    cmap_table = struct.pack('>4HI', 0, 1, 3, 10, 12)+subtable
    cmap_program = struct.pack('>4s4H4sIII', b'\0\1\0\0', 1, 16, 0, 0, b'cmap', 0, 28, len(cmap_table))+cmap_table
    assert read_unicode_coverage(cmap_program) == frozenset({0x1f600, 0x1f601, 0x1f602})
    for legacy_subtable in (
        struct.pack('>3H', 0, 262, 0)+bytes(65)+b'\1\0\2'+bytes(188),
        struct.pack('>8H', 6, 16, 0, 65, 3, 1, 0, 2),
    ):
        legacy_cmap = struct.pack('>4HI', 0, 1, 3, 1, 12)+legacy_subtable
        legacy_font = struct.pack('>4s4H4sIII', b'\0\1\0\0', 1, 16, 0, 0, b'cmap', 0, 28, len(legacy_cmap))+legacy_cmap
        assert read_unicode_coverage(legacy_font) == frozenset({65, 67})

    # Own physical metric tables; no glyph interpreter or complete-font claim.
    head, horizontal = bytearray(54), bytearray(36)
    struct.pack_into('>I', head, 0, 0x10000)
    struct.pack_into('>I', head, 12, 0x5f0f3cf5)
    struct.pack_into('>H', head, 18, 1000)
    struct.pack_into('>Ihhh', horizontal, 0, 0x10000, 800, -200, 0)
    metrics_program = (struct.pack('>4s4H', b'\0\1\0\0', 2, 32, 1, 0)
                       + struct.pack('>4sIII', b'head', 0, 44, 54)
                       + struct.pack('>4sIII', b'hhea', 0, 100, 36)+head+b'\0\0'+horizontal)
    with TemporaryDirectory(prefix='opendoc_metrics_') as directory:
        path = Path(directory)/'own.ttf'
        path.write_bytes(metrics_program)
        style = TextStyle(font_family='Own', font_size=Length(10), properties={'font_resolution': {'path': str(path)}})
        assert word_line_ascent(style) == 8 and word_line_descent(style) == 2

        os2, post, maximum = bytearray(78), bytearray(32), bytearray(32)
        struct.pack_into('>Hh3H', os2, 0, 0, 500, 400, 5, 0)
        struct.pack_into('>I', post, 0, 0x30000)
        struct.pack_into('>IH', maximum, 0, 0x10000, 4)
        tables = {'head': head, 'hhea': horizontal, 'OS/2': os2, 'post': post,
                  'maxp': maximum, 'name': name_table, 'cmap': cmap_table}
        def face_program() -> bytes:
            directory_records, payload = bytearray(), bytearray()
            for tag, table in sorted(tables.items()):
                offset = 12+16*len(tables)+len(payload)
                directory_records.extend(struct.pack('>4sIII', tag.encode('ascii'), 0, offset, len(table)))
                payload.extend(table)
                payload.extend(bytes(-len(payload) % 4))
            selector = len(tables).bit_length()-1
            search = 16*(1 << selector)
            header = struct.pack('>4s4H', b'\0\1\0\0', len(tables), search, selector, 16*len(tables)-search)
            return header+directory_records+payload

        path.write_bytes(face_program())
        face = _read_face(path)
        assert face is not None and face.family == 'Own Typographic' and face.units_per_em == 1000
        assert face.glyphs == frozenset({0x1f600, 0x1f601, 0x1f602})
        assert face.embeddable and face.subsettable
        post4 = bytearray(post)
        struct.pack_into('>I', post4, 0, 0x40000)
        post4.extend(struct.pack('>4H', 0xffff, 0xd800, 65, 65))
        tables['post'] = post4
        native_post4 = face_program()
        path.write_bytes(native_post4)
        assert _read_face(path) == face and path.read_bytes() == native_post4
        tables['post'] = post
        tables['fvar'] = (struct.pack('>8H', 1, 0, 16, 2, 1, 20, 1, 8)
                          +struct.pack('>4s3i2H', b'wght', 100*65536, 400*65536, 900*65536, 0, 256)
                          +struct.pack('>2Hi', 257, 0, 700*65536))
        path.write_bytes(face_program())
        default_face = _read_face(path)
        assert default_face == face and default_face.weight == 400
        tables.pop('fvar')
        first = face_program()
        struct.pack_into('>H', head, 18, 2048)
        second = face_program()
        struct.pack_into('>H', head, 18, 1000)
        collection_parts = []
        base = 20
        for program in (first, second):
            absolute = bytearray(program)
            count = struct.unpack_from('>H', absolute, 4)[0]
            for index in range(count):
                location = 12+16*index+8
                struct.pack_into('>I', absolute, location, base+struct.unpack_from('>I', absolute, location)[0])
            collection_parts.append(bytes(absolute))
            base += len(absolute)
        collection = struct.pack('>4s4I', b'ttcf', 0x10000, 2, 20, 20+len(first))+b''.join(collection_parts)
        path.write_bytes(collection)
        assert _read_face(path) == face
        selected = inspect_sfnt(collection, face_index=1, capture=True)
        assert selected.face_index == 1 and selected.directory_offset == 20+len(first)
        assert all(table.payload == collection[table.offset:table.offset+table.length] for table in selected.tables)
        assert read_face_metrics(collection, face_index=1).units_per_em == 2048
        collection_snapshot = inspect_binary(collection, sfnt_face_index=1, capture=True)
        assert collection_snapshot.container == 'sfnt' and dict(collection_snapshot.details)['face_index'] == 1
        assert collection_snapshot.items[0].payload == collection
        assert [item.locator for item in collection_snapshot.items[1:]] == [
            'sfnt:face=1:table='+table.tag for table in selected.tables]
        assert all(item.payload == table.payload
                   for item, table in zip(collection_snapshot.items[1:], selected.tables, strict=True))
        assert path.read_bytes() == collection
        keys = [0]*256
        keys[0x81] = keys[0x82] = 8
        high_bytes = (struct.pack('>3H', 2, 546, 0)+struct.pack('>256H', *keys)
                      +struct.pack('>2HhH', 65, 3, 0, 10)+struct.pack('>2HhH', 65, 3, -1, 8)
                      +struct.pack('>6H', 1, 0, 2, 2, 0, 3))
        tables['cmap'] = struct.pack('>4HI', 0, 1, 3, 1, 12)+high_bytes
        encoded = face_program()
        expected_mapping = {65: 1, 67: 2, 0x8141: 1, 0x8143: 2, 0x8241: 1, 0x8243: 2}
        assert read_unicode_mapping(encoded) == expected_mapping
        path.write_bytes(encoded)
        high_byte_face = _read_face(path)
        assert high_byte_face is not None and high_byte_face.glyphs == frozenset(expected_mapping)
        assert high_byte_face.family == face.family and high_byte_face.units_per_em == face.units_per_em
        assert high_byte_face.embeddable == face.embeddable and high_byte_face.subsettable == face.subsettable
        assert path.read_bytes() == encoded
        tables['cmap'] = struct.pack('>4HI', 0, 1, 3, 1, 12)+struct.pack('>9H', 6, 18, 0, 102, 4, 1, 0, 0, 2)
        scripts = struct.pack('>H4s7H', 1, b'DFLT', 8, 4, 0, 0, 0xffff, 1, 0)
        features = struct.pack('>H4s4H', 1, b'liga', 8, 0, 1, 0)
        ligature = struct.pack('>12H', 1, 18, 1, 8, 1, 4, 3, 2, 2, 1, 1, 1)
        lookups = struct.pack('>6H', 1, 4, 4, 0, 1, 8)+ligature
        tables['GSUB'] = struct.pack('>I3H', 0x10000, 10, 30, 44)+scripts+features+lookups
        assert read_ligature_mapping(face_program()) == {3: 'fi'}

    source = io.BytesIO()
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('word/own', '<own xmlns="urn:own"><child>Own text</child></own>')
        archive.writestr('word/unknown.bin', b'Own opaque bytes\x00\xff')
        archive.writestr('[Content_Types].xml',
                         '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                         '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                         '<Default Extension="bin" ContentType="application/octet-stream"/>'
                         '<Override PartName="/word/own" ContentType="application/vnd.own+xml"/></Types>')
        archive.writestr('_rels/.rels',
                         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         '<Relationship Id="own" Type="urn:own" Target="word/own"/></Relationships>')
    snapshot = inspect_binary(source.getvalue(), capture=True)
    assert snapshot.items[1].payload == b'Own opaque bytes\x00\xff'
    assert snapshot.items[0].xml_nodes[1].tag == '{urn:own}child'
    assert dict(snapshot.items[0].details)['xml_detection'] == 'opc-content-type'
    assert snapshot.opc is not None and snapshot.opc.reachability_complete
    assert snapshot.opc.reachable_parts == ('/word/own',)
    assert snapshot.opc.unreachable_parts == ('/word/unknown.bin',)
    assert compare_snapshots(snapshot, inspect_binary(source.getvalue()))['binary_identical']
    for old, new, code in [('Id="own"', 'Id="Связь1"', None),
                           ('Id="own"', 'Id="1bad"', 'opc.relationship-id'),
                           ('Type="urn:own"', 'Type="urn:bad%"', 'opc.relationship-type')]:
        lexical = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(source.getvalue())) as original, zipfile.ZipFile(lexical, 'w') as updated:
            for info in original.infolist():
                data = original.read(info.filename)
                if info.filename == '_rels/.rels':
                    data = data.decode().replace(old, new).encode()
                updated.writestr(info, data)
        audited = inspect_binary(lexical.getvalue(), capture=True)
        assert audited.items[0].payload is not None
        assert audited.opc.reachability_complete is (code is None)
        if code is not None:
            assert any(finding.code == code for finding in audited.opc.findings)
            assert not audited.opc.unreachable_parts
    epub = io.BytesIO()
    with zipfile.ZipFile(epub, 'w') as archive:
        archive.writestr('mimetype', b'application/epub+zip')
        archive.writestr('Book/chapter', '<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Own</p></body></html>')
        archive.writestr('META-INF/container.xml',
                         '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                         '<rootfile full-path="Book/package" media-type="application/oebps-package+xml"/>'
                         '</rootfiles></container>')
        archive.writestr('Book/package', '<package xmlns="http://www.idpf.org/2007/opf"><manifest>'
                         '<item id="own" href="chapter" media-type="application/xhtml+xml"/>'
                         '<item id="audio" href="https://example.invalid/own.mp3" media-type="audio/mpeg"/>'
                         '</manifest></package>')
    snapshot = inspect_binary(epub.getvalue())
    assert snapshot.opc is None and dict(snapshot.details)['epub_rootfiles'] == ('Book/package',)
    assert dict(snapshot.items[1].details)['xml_detection'] == 'epub-media-type'
    assert snapshot.items[1].xml_nodes[0].tag == '{http://www.w3.org/1999/xhtml}html'
    assert snapshot.epub is not None and len(snapshot.epub.references) == 2
    assert snapshot.epub.references[-1].status == 'external-unassessed'
    assert snapshot.epub.references[-1].resolved_target is None
    assert not snapshot.to_dict()['epub']['assessment_complete']
    compound_smoke()


def compound_smoke() -> None:
    from opendoc_formats.anatomy import inspect_binary

    header, fat, directory, mini, pool = [bytearray(512) for _ in range(5)]
    header[:8] = b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'
    struct.pack_into('<5H', header, 24, 0x3e, 3, 0xfffe, 9, 6)
    struct.pack_into('<9I', header, 40, 0, 1, 1, 0, 4096, 2, 1, 0xfffffffe, 0)
    header[76:] = b'\xff'*436
    struct.pack_into('<I', header, 76, 0)
    fat[:] = mini[:] = b'\xff'*512
    struct.pack_into('<4I', fat, 0, 0xfffffffd, 0xfffffffe, 0xfffffffe, 0xfffffffe)
    struct.pack_into('<I', mini, 0, 0xfffffffe)
    payload = b'Own portable compound stream\x00\xff'
    pool[:len(payload)] = payload
    for index in range(4):
        struct.pack_into('<3I', directory, index*128+68, 0xffffffff, 0xffffffff, 0xffffffff)
    for index, name, kind, start, size in ((0, 'Root Entry', 5, 3, 64), (1, 'Small', 2, 0, len(payload))):
        encoded = (name+'\0').encode('utf-16-le')
        directory[index*128:index*128+len(encoded)] = encoded
        struct.pack_into('<HBB', directory, index*128+64, len(encoded), kind, 1)
        struct.pack_into('<IQ', directory, index*128+116, start, size)
    struct.pack_into('<I', directory, 76, 1)
    original = bytes(header+fat+directory+mini+pool)
    snapshot = inspect_binary(original, capture=True)
    assert snapshot.container == 'cfbf'
    assert next(item for item in snapshot.items if item.locator == 'cfbf:directory=1').payload == payload
    assert b''.join(item.payload for item in snapshot.items if item.kind == 'cfbf-physical-sector') == original
    assert not dict(snapshot.details)['assessment_complete']
    assert dict(snapshot.details)['directory_links_valid']


def font_subset_smoke() -> None:
    from fontTools import subset
    from fontTools.ttLib import TTFont

    from opendoc_formats.fonts.embedding import FontUsage, subset_font

    source = (Path(__file__).resolve().parents[1]/'tests/native/data/ligature-post3.ttf').read_bytes()
    calls, original = [], subset.Subsetter.subset

    def observed(self, font):
        calls.append(True)
        return original(self, font)

    subset.Subsetter.subset = observed
    try:
        with TemporaryDirectory(prefix='opendoc_subset_cache_') as directory:
            path = Path(directory)/'own.ttf'
            path.write_bytes(source)
            usage = FontUsage('Own', path, False, False, frozenset('fi'), True, True)
            first = subset_font(usage)
            assert first == subset_font(usage) and calls == [True]
            with TTFont(io.BytesIO(first)) as reduced, TTFont(io.BytesIO(source)) as original_font:
                def records(font):
                    return sorted((n.platformID, n.platEncID, n.langID, n.nameID, n.string) for n in font['name'].names)
                assert records(reduced) == records(original_font)
                assert set(reduced.getBestCmap()) >= {ord('f'), ord('i')}
            assert path.read_bytes() == source
    finally:
        subset.Subsetter.subset = original


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all-formats", action="store_true")
    parser.add_argument("--pdf-text", action="store_true")
    parser.add_argument("--epub", action="store_true")
    parser.add_argument("--fonts", action="store_true")
    args = parser.parse_args()
    from opendoc_model import (
        DocumentLimits,
        DocumentModel,
        Formula,
        FormulaFormat,
        Paragraph,
        Section,
        Table,
        TableCell,
        TableRow,
        TextRun,
        document_from_json,
        document_to_json,
        get_heading,
        get_list_item,
        iter_list_numbers,
    )

    import opendoc_formats
    from opendoc_formats import (
        ExportOptions,
        ImportOptions,
        TextProfile,
        default_exporter_registry,
        default_registry,
        read_document,
        write_document,
    )
    from opendoc_formats.docx import DocxPackage, ReplaceTextSpan
    from opendoc_formats.errors import BackendUnavailableError
    from opendoc_formats.office import find_libreoffice
    from opendoc_formats.package_resources import assemble_docx_package_resources
    from opendoc_formats.pdf import PdfDocument
    from opendoc_formats.support.inspection import inspect_path

    assert opendoc_formats.__version__ == version("opendoc-formats")
    assert version("opendoc-model") == "0.19.0"
    assert importlib.util.find_spec("ebooklib") is None, "Removed EPUB engine leaked into the installed profile"
    engines = ("bs4", "fitz", "pymupdf", "lxml", "docx", "pptx", "ebooklib", "fontTools")
    assert all(name not in sys.modules for name in engines)
    installed = Path(opendoc_formats.__file__).resolve().parent
    assert "site-packages" in installed.parts, installed
    assert (installed / "py.typed").is_file()
    diagnostics_smoke()
    anatomy_smoke()
    default_registry()
    default_exporter_registry()
    if not args.all_formats:
        absent = tuple(name for name in engines if not ((name == 'bs4' and args.epub) or (name == 'fontTools' and args.fonts)))
        assert all(importlib.util.find_spec(name) is None for name in absent)
        for constructor in (DocxPackage, PdfDocument):
            try:
                constructor(b"missing engine")
            except BackendUnavailableError:
                pass
            else:
                raise AssertionError("Native access should diagnose absent optional backend")
        find_libreoffice()
    if args.fonts:
        font_subset_smoke()
    document = DocumentModel(
        sections=[
            Section(
                blocks=[
                    Paragraph([TextRun("Installed package / Проверка 123")]),
                    Table([TableRow([TableCell([Paragraph([TextRun("Cell")])])])]),
                ]
            )
        ]
    )
    assert assemble_docx_package_resources(document, {}) == document
    if args.pdf_text:
        from opendoc_formats.readers.pdf import get_pdf_info, read_pdf
        from opendoc_formats.support.io import validate_pdf

        pdf_source = Path(__file__).resolve().parents[1] / "tests/corpus/native/text-pages.pdf"
        text = read_pdf(str(pdf_source))
        assert text.engine == "pypdf" and text.pages == 2 and "Native PDF" in text.plain, text
        assert validate_pdf(pdf_source) and get_pdf_info(str(pdf_source)) == {'title': '', 'author': '', 'subject': ''}
    with TemporaryDirectory(prefix="opendoc-formats-installed-") as directory:
        root = Path(directory)
        tex = root / "own-source.tex"
        tex.write_text(r"\documentclass{article}\begin{document}\section{Own}Text $x^2$.\end{document}", encoding="utf-8")
        source_tex = read_document(tex)
        assert source_tex.success and not source_tex.lossless and not source_tex.assessment_complete
        assert source_tex.document.sections[0].blocks[0].plain_text == "Own"
        assert source_tex.document.sections[0].blocks[1].content[-2].format is FormulaFormat.LATEX
        assert source_tex.document.resources["latex-original-source"].data == tex.read_bytes()
        native_tex = DocumentModel(sections=[Section(blocks=[Paragraph(content=[TextRun('Own [text] & percent 100%')])])])
        for index in range(2):
            native_target = root / f'native-text-{index}.tex'
            native_report = write_document(native_tex, native_target)
            assert native_report.success and native_report.metrics['latex_route'] == 'native-text-v1'
            native_tex = document_from_json(document_to_json(read_document(native_target).document))
            assert native_tex.sections[0].blocks[0].plain_text == 'Own [text] & percent 100%'
        headings = root / 'source-headings.tex'
        scripts = root / 'source-scripts.tex'
        scripts.write_text(r'\begin{document}Own\textsuperscript{\bfseries B\normalfont N} '
                           r'and H\textsubscript{2}O.\end{document}', encoding='utf-8')
        script_model = read_document(scripts).document
        for index in range(2):
            script_target = root / f'scripts-{index}.tex'
            script_report = write_document(document_from_json(document_to_json(script_model)), script_target)
            assert script_report.success and script_report.metrics['latex_route'] == 'native-text-v1'
            script_model = read_document(script_target).document
            runs = script_model.sections[0].blocks[0].content
            assert any(run.style.superscript for run in runs) and any(run.style.subscript for run in runs)
            assert r'\textsuperscript{{\bfseries B}N}' in script_target.read_text(encoding='utf-8')
        headings.write_text(r'\begin{document}\section{Own}\subsection*{Child}'
                            r'\subsubsection{Math $x^2$}\end{document}', encoding='utf-8')
        native_headings = read_document(headings).document
        for index in range(2):
            target = root / f'headings-{index}.tex'
            heading_report = write_document(native_headings, target)
            assert heading_report.success and heading_report.metrics['latex_route'] == 'native-text-v1'
            native_headings = document_from_json(document_to_json(read_document(target).document))
            assert [get_heading(p).level for p in native_headings.sections[0].blocks] == [1, 2, 3]
            assert next(f for f in native_headings.sections[0].blocks[-1].content if isinstance(f, Formula)).value == 'x^2'
            assert r'\section{Own}' in target.read_text(encoding='utf-8')
            assert r'\subsection*{Child}' in target.read_text(encoding='utf-8')
        list_source = root / 'source-list.tex'
        list_source.write_text(r'\begin{enumerate}\item First\par Continuation\end{enumerate} Outside', encoding='utf-8')
        list_model = read_document(list_source).document
        assert [p.plain_text for p in list_model.sections[0].blocks] == ['First', 'Continuation', 'Outside']
        assert get_list_item(list_model.sections[0].blocks[1]).continuation_of is not None
        assert [entry.number for entry in iter_list_numbers(list_model)] == [1, None]
        for index in range(2):
            target = root / f'lists-{index}.tex'
            list_report = write_document(list_model, target)
            assert list_report.success and list_report.metrics['latex_route'] == 'native-text-v1'
            list_model = document_from_json(document_to_json(read_document(target).document))
            assert [entry.number for entry in iter_list_numbers(list_model)] == [1, None]
        native_math = DocumentModel(sections=[Section(blocks=[Paragraph(content=[
            TextRun('Before '), Formula(r'\frac{x}{2}', FormulaFormat.LATEX, fallback_text='own fraction'),
            Formula(r'\begin{pmatrix}1&2\\3&4\end{pmatrix}', FormulaFormat.LATEX, display=True),
            TextRun(' after'),
        ])])])
        for index in range(2):
            target = root / f'math-{index}.tex'
            report = write_document(native_math, target)
            assert report.success and report.metrics['latex_route'] == 'native-text-v1'
            native_math = document_from_json(document_to_json(read_document(target).document))
            paragraph, = native_math.sections[0].blocks
            formulas = [run for run in paragraph.content if isinstance(run, Formula)]
            assert [(f.value, f.display, f.fallback_text) for f in formulas] == [
                (r'\frac{x}{2}', False, 'own fraction'), (r'\begin{pmatrix}1&2\\3&4\end{pmatrix}', True, ''),
            ]
        book = root / "base-writer.epub"
        from opendoc_formats.readers.epub_package import read_epub_package

        book_report = write_document(DocumentModel(metadata={"creator": ["Own author"], "identifier": "urn:example:installed"},
                                                    sections=[Section(blocks=[Paragraph(content=[TextRun("Own EPUB")])])]), book)
        assert book_report.success and book_report.metrics["output_verified"], book_report.to_dict()
        assert read_epub_package(book).spine == (("chapter", "yes"),)
        assert read_epub_package(book).dc_values["creator"] == ("Own author",)
        assert read_epub_package(book).metadata["identifier"] == "urn:example:installed"
        for cancel_model, cancel_target in ((native_tex, native_target), (native_math, target), (native_tex, book)):
            previous = cancel_target.read_bytes()
            export_polls = 0

            def stop_text_export() -> bool:
                nonlocal export_polls
                export_polls += 1
                return export_polls >= 12

            refused_export = write_document(cancel_model, cancel_target, options=ExportOptions(cancelled=stop_text_export))
            assert export_polls == 12 and not refused_export.success
            assert any(issue.feature == 'export.cancelled' for issue in refused_export.issues)
            assert cancel_target.read_bytes() == previous
        for encoding in ("utf-8", "utf-16-le", "utf-16-be", "cp1251"):
            source = root / "profile.txt"
            original = "Первая\r\nВторая\rПоследняя\n".encode(encoding)
            source.write_bytes(original)
            imported = read_document(source, options=ImportOptions(txt_profile=TextProfile(encoding)))
            assert imported.success, imported.issues
            transport = root / "profile.json"
            assert write_document(imported.document, transport).success
            restored = read_document(transport)
            target = root / "profile-copy.txt"
            copied = write_document(restored.document, target, options=ExportOptions(txt_profile=TextProfile()))
            assert copied.success and copied.lossless and copied.metrics["output_verified"], copied.to_dict()
            assert target.read_bytes() == original
        if args.epub:
            source = root / "native.epub"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("mimetype", "application/epub+zip")
                archive.writestr("META-INF/container.xml", '''
                  <container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>
                  <rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>''')
                archive.writestr("book.opf", '''<package xmlns="http://www.idpf.org/2007/opf"><metadata/>
                  <manifest><item id="c" href="c.xhtml" media-type="application/xhtml+xml"/>
                  <item id="appendix" href="appendix.xhtml" media-type="application/xhtml+xml"/></manifest>
                  <spine><itemref idref="c"/><itemref idref="appendix" linear="no"/></spine></package>''')
                archive.writestr("c.xhtml", '''<html><body><p style="position:absolute;font-size:12pt">Native EPUB 123</p>
                    <table><tr><td colspan="2">Own cell</td></tr></table>
                    <math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>
                    </body></html>''')
                archive.writestr("appendix.xhtml", "<html><body><p>Own nonlinear appendix</p></body></html>")
            result = read_document(source)
            assert result.success, result.issues
            assert result.document.sections[0].blocks[0].plain_text == "Native EPUB 123"
            assert any(issue.reason == "unsupported-declaration" for issue in result.issues)
            assert isinstance(result.document.sections[0].blocks[1], Table)
            assert result.document.sections[0].blocks[1].rows[0].cells[0].column_span == 2
            assert isinstance(result.document.sections[0].blocks[2].content[0], Formula)
            vector = result.document.sections[0].blocks[3].content[0]
            assert result.document.resources[vector.resource_id].media_type == "image/svg+xml"
            assert len(result.document.sections) == 1
            inclusive = read_document(source, options=ImportOptions(epub_include_nonlinear=True))
            assert inclusive.success and len(inclusive.document.sections) == 2
            assert inclusive.document.sections[1].blocks[0].plain_text == "Own nonlinear appendix"
            assert inclusive.document.sections[1].properties["epub"]["linear"] == "no"
            assert all(name not in sys.modules for name in ("lxml", "ebooklib"))
        math_path = root / "math.html"
        math = DocumentModel(sections=[Section(blocks=[Formula(
            '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>', FormulaFormat.MATHML,
        )])])
        math_report = write_document(math, math_path)
        assert math_report.success, math_report.to_dict()
        assert "<mi>x</mi>" in math_path.read_text(encoding="utf-8")
        if not args.all_formats:
            assert "lxml" not in sys.modules
        if args.all_formats:
            from bs4 import BeautifulSoup
            from opendoc_model.document_codec import document_from_json, document_to_json

            source = root / "semantic.html"
            source.write_text('<html lang="en"><body><table><caption>Own measurements</caption>'
                              '<thead><tr><th id="value" scope="col">Value</th></tr></thead>'
                              '<tbody><tr><td headers="value">12</td></tr></tbody></table></body></html>')
            for cycle in range(2):
                imported = read_document(source)
                assert imported.success, imported.issues
                restored = document_from_json(document_to_json(imported.document))
                target = root / f"semantic-{cycle}.html"
                assert write_document(restored, target).success
                parsed = BeautifulSoup(target.read_text(encoding="utf-8"), "html.parser")
                assert parsed.html["lang"] == "en"
                assert parsed.table.caption.get_text() == "Own measurements"
                assert parsed.table.th["scope"] == "col"
                assert parsed.table.td["headers"] == ["value"]
                source = target
        formats = ("txt", "json", "html", "docx", "pptx", "pdf", "latex") if args.all_formats else ("txt", "json", "html")
        for format_id in formats:
            path = root / ("document." + ("tex" if format_id == "latex" else format_id))
            report = write_document(document, path)
            assert report.success, report.to_dict()
            assert report.metrics["output_verified"] is True
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            inspected = inspect_path(path, options=ImportOptions(document_limits=DocumentLimits(max_nodes=200000)))
            assert inspected.valid and inspected.metadata['inspection_status'] == 'completed', inspected.to_dict()
            assert inspected.metadata['inspection_source_sha256'] == digest
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
            if format_id in {'txt', 'json', 'docx', 'pptx'}:
                refused = inspect_path(path, options=ImportOptions(document_limits=DocumentLimits(max_nodes=10)))
                assert not refused.valid and refused.metadata['document_limit']['maximum'] == 10
            if format_id != "latex" and (args.all_formats or format_id != "html"):
                result = read_document(path)
                assert result.success, result.issues
                assert result.document.validate() == []
                assert "Cell" in str(result.document)
                if format_id in {'docx', 'pptx'}:
                    native_polls = 0

                    def stop_native() -> bool:
                        nonlocal native_polls
                        native_polls += 1
                        return native_polls >= 12

                    cancelled = read_document(path, options=ImportOptions(cancelled=stop_native))
                    assert native_polls == 12
                    assert cancelled.document is None and any(issue.code == 'import.cancelled' for issue in cancelled.issues)
                    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
                    assert document_to_json(read_document(path).document) == document_to_json(result.document)
                    export_polls = 0

                    def stop_export() -> bool:
                        nonlocal export_polls
                        export_polls += 1
                        return export_polls >= 12

                    cancelled_export = write_document(document, path, options=ExportOptions(cancelled=stop_export))
                    assert export_polls == 12 and not cancelled_export.success
                    assert any(issue.feature == 'export.cancelled' for issue in cancelled_export.issues)
                    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
            if args.all_formats and format_id == "docx":
                from opendoc_model import (
                    Heading,
                    TableIndent,
                    TabStop,
                    TabStops,
                    WidthMeasure,
                    get_heading,
                    get_preferred_width,
                    get_tab_stops,
                    get_table_indent,
                    set_heading,
                    set_preferred_width,
                    set_tab_stops,
                    set_table_indent,
                )
                from opendoc_model.document_codec import document_from_json, document_to_json

                heading = Paragraph([TextRun("Own formal heading")])
                set_tab_stops(heading, TabStops((TabStop(396, alignment='right', leader='line'),)))
                set_heading(heading, Heading(2))
                width_cell = TableCell([Paragraph([TextRun("Own typed width")])])
                width_table = Table([TableRow([width_cell])])
                set_table_indent(width_table, TableIndent(30))
                set_preferred_width(width_table, WidthMeasure("relative", 0.8, "ratio", "content"))
                set_preferred_width(width_cell, WidthMeasure("absolute", 120, "pt"))
                heading_model = DocumentModel(sections=[Section(blocks=[heading, width_table])])
                for cycle in range(2):
                    heading_target = root / f"heading-{cycle}.docx"
                    restored = document_from_json(document_to_json(heading_model))
                    assert write_document(restored, heading_target).success
                    heading_result = read_document(heading_target)
                    assert heading_result.success, heading_result.issues
                    heading_model = heading_result.document
                    assert get_heading(heading_model.sections[0].blocks[0]) == Heading(2)
                    assert get_tab_stops(heading_model.sections[0].blocks[0]) == TabStops((
                        TabStop(396, alignment='right', leader='line'),
                    ))
                    returned_table = heading_model.sections[0].blocks[1]
                    assert get_table_indent(returned_table) == TableIndent(30)
                    assert get_preferred_width(returned_table) == WidthMeasure("relative", 0.8, "ratio", "content")
                    assert get_preferred_width(returned_table.rows[0].cells[0]) == WidthMeasure("absolute", 120, "pt")
                with DocxPackage(path) as package:
                    paragraph = next(p for p in package.paragraphs if p.is_body and p.text)
                    updated = package.to_bytes([ReplaceTextSpan(paragraph.id, 0, 0, "Native ")])
                with DocxPackage(updated) as package:
                    assert package.paragraphs[0].text.startswith("Native ")
            if args.all_formats and format_id == "pdf":
                with PdfDocument(path) as pdf:
                    assert pdf.page_count > 0 and pdf.page_info(0).width > 0
                    assert isinstance(pdf.page_text_spans(0), tuple)
                    rendered = pdf.render_page(0, max_dimension=512)
                    assert rendered.png.startswith(b"\x89PNG") and rendered.effective_scale > 0
    print(f"Installed wheel smoke passed: epub writer, {', '.join(formats)}")


if __name__ == "__main__":
    main()
