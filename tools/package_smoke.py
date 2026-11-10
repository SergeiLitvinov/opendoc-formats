"""Exercise the installed wheel in an isolated interpreter, without importing the checkout."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import struct
import sys
import zipfile
import zlib
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory


def diagnostics_smoke() -> None:
    from xml.etree.ElementTree import fromstring

    from opendoc_model import (
        DiagnosticIssue,
        IssueSeverity,
        Provenance,
        document_from_json,
        document_to_json,
        integration_from_dict,
    )

    from opendoc_formats.ooxml.color import resolve_drawingml_color
    from opendoc_formats.support.document_adapters import document_to_text, text_to_document
    from opendoc_formats.support.text_diagnostics import append_text_warning
    from opendoc_formats.types import DocFormat, Text

    color_xml = fromstring('<a:srgbClr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" val="204060">'
                           '<a:shade val="50000"/><a:tint val="50000"/><a:alpha val="25000"/></a:srgbClr>')
    color, _ = resolve_drawingml_color(color_xml, {})
    assert color.to_hex(include_alpha=True) == '#BCBEC040'
    luminance = fromstring('<a:srgbClr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" val="204060">'
                           '<a:lumMod val="200000"/></a:srgbClr>')
    assert resolve_drawingml_color(luminance, {})[0].to_hex() == '#4080C0'

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
    from opendoc_formats.anatomy_tree import inspect_container_tree
    from opendoc_formats.fonts.resolver import _read_face
    from opendoc_formats.fonts.resource_fonts import font_program_names
    from opendoc_formats.fonts.sfnt_cmap import read_unicode_coverage, read_unicode_mapping
    from opendoc_formats.fonts.sfnt_ligatures import read_ligature_mapping
    from opendoc_formats.fonts.word_metrics import word_line_ascent, word_line_descent
    from opendoc_formats.native.epub import local_path
    from opendoc_formats.native.sfnt import inspect_sfnt, inspect_sfnt_checksums, inspect_sfnt_structure, read_face_metrics

    def png_chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))

    png = (b'\x89PNG\r\n\x1a\n' + png_chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
           + png_chunk(b'gAMA', struct.pack('>I', 45455)) + png_chunk(b'sRGB', b'\x01')
           + png_chunk(b'pHYs', struct.pack('>IIB', 3780, 2835, 1))
           + png_chunk(b'tRNS', struct.pack('>HHH', 255, 0, 0))
           + png_chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + png_chunk(b'IEND', b''))
    png_snapshot = inspect_binary(png, capture=True)
    assert png_snapshot.container == 'png' and dict(png_snapshot.details)['width'] == 1
    png_metadata = {entry['chunk_type']: entry['values'] for entry in dict(png_snapshot.details)['metadata_declarations']}
    assert png_metadata['gAMA'] == {'gamma_times_100000': 45455}
    assert png_metadata['tRNS']['transparent_samples'] == (255, 0, 0)
    assert png_metadata['pHYs']['unit_specifier'] == 1 and not dict(png_snapshot.details)['metadata_findings']
    assert b''.join(item.payload for item in png_snapshot.items) == png
    png_zip = io.BytesIO()
    with zipfile.ZipFile(png_zip, 'w') as archive:
        archive.writestr('ppt/media/own.png', png)
    tree = inspect_container_tree(png_zip.getvalue(), capture=True)
    assert [entry.snapshot.container for entry in tree.occurrences] == ['zip', 'png']
    assert tree.occurrences[1].snapshot == png_snapshot

    pdf_source = bytearray(b'%PDF-1.7\n')
    positions = {}
    member = b'<< /Title (Own native member) >>'
    compressed = b'7 0 '+member
    objects = [(1, b'<< /Type /Catalog /Pages 2 0 R >>'),
               (2, b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>'),
               (3, b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] >>'),
               (4, b'<< /Type /ObjStm /N 1 /First 4 /Length '+str(len(compressed)).encode()
                +b' /Extends 5 0 R >>\nstream\n'+compressed+b'\nendstream'),
               (5, b'<< /Type /ObjStm /N 1 /First 4 /Length 6 >>\nstream\n8 0 42\nendstream')]
    for number, body in objects:
        positions[number] = len(pdf_source)
        pdf_source.extend(f'{number} 0 obj\n'.encode()+body+b'\nendobj\n')
    xref_offset = len(pdf_source)
    records = [(0, 0, 65535)]+[(1, positions[number], 0) for number in range(1, 6)]
    records += [(1, xref_offset, 0), (2, 4, 0)]
    raw = b''.join(bytes([kind])+target.to_bytes(4, 'big')+generation.to_bytes(2, 'big')
                   for kind, target, generation in records)
    pdf_source.extend(b'6 0 obj\n<< /Type /XRef /Size 9 /Root 1 0 R /Info 7 0 R /Index [0 8] /W [1 4 2] '
                      +f'/Length {len(raw)} >>\nstream\n'.encode()+raw
                      +f'\nendstream\nendobj\nstartxref\n{xref_offset}\n%%EOF\n'.encode())
    pdf_snapshot = inspect_binary(bytes(pdf_source), pdf_source=True, pdf_decode_xrefs=True, pdf_object_streams=True)
    link, = dict(pdf_snapshot.details)['compressed_object_links']
    assert link['status'] == 'matched-declared-member' and link['container_offset'] == positions[4]
    assert link['member_sha256'] == hashlib.sha256(member).hexdigest()
    assert not link['ownership_proven'] and not link['object_resolved']
    extension, = dict(pdf_snapshot.details)['object_stream_extends_links']
    assert extension['status'] == 'matched-declared-extends' and extension['target_offset'] == positions[5]
    assert dict(pdf_snapshot.details)['decoded_object_streams'] == 2
    assert not extension['members_inherited'] and not extension['ownership_proven']
    current_extension, = dict(pdf_snapshot.details)['object_stream_current_extends_links']
    assert current_extension['target_offset'] == positions[5] and not current_extension['object_resolved']
    assert dict(pdf_snapshot.details)['object_stream_current_extends_dag_valid']
    # A classic incremental section replaces only the parent; both child and type-2 user are inherited.
    replacement = len(pdf_source)
    pdf_source.extend(b'5 0 obj\n<< /Type /ObjStm /N 1 /First 4 /Length 6 >>\nstream\n8 0 84\nendstream\nendobj\n')
    current_xref = len(pdf_source)
    pdf_source.extend((f'xref\n5 1\n{replacement:010} 00000 n \ntrailer\n'
                       f'<< /Size 9 /Root 1 0 R /Info 7 0 R /Prev {xref_offset} >>\n'
                       f'startxref\n{current_xref}\n%%EOF\n').encode())
    updated = inspect_binary(bytes(pdf_source), pdf_source=True, pdf_decode_xrefs=True, pdf_object_streams=True)
    old, = dict(updated.details)['object_stream_extends_links']
    current_link, = dict(updated.details)['object_stream_current_extends_links']
    current_root, = dict(updated.details)['object_stream_current_extends_roots']
    assert old['target_offset'] == positions[5] and current_link['target_offset'] == replacement
    assert current_link['primary_xref'] == current_xref and current_root['reference_xref'] == xref_offset
    assert not current_link['object_resolved'] and not current_link['members_inherited']

    # Replace only the member's container: the type-2 user is still inherited.
    new_member = b'<< /Title (Own current installed) >>'
    raw_member = b'7 0 '+new_member
    new_container = len(pdf_source)
    pdf_source.extend(b'4 0 obj\n<< /Type /ObjStm /N 1 /First 4 /Length '+str(len(raw_member)).encode()
                      +b' >>\nstream\n'+raw_member+b'\nendstream\nendobj\n')
    member_xref = len(pdf_source)
    pdf_source.extend((f'xref\n4 1\n{new_container:010} 00000 n \ntrailer\n'
                       f'<< /Size 9 /Root 1 0 R /Info 7 0 R /Prev {current_xref} >>\n'
                       f'startxref\n{member_xref}\n%%EOF\n').encode())
    projected = inspect_binary(bytes(pdf_source), pdf_source=True, pdf_decode_xrefs=True, pdf_object_streams=True)
    historical, = dict(projected.details)['compressed_object_links']
    selected, = dict(projected.details)['compressed_object_current_links']
    assert historical['container_offset'] == positions[4] and selected['container_offset'] == new_container
    assert selected['context_xref'] == member_xref and selected['xref_offset'] == xref_offset
    assert selected['member_sha256'] == hashlib.sha256(new_member).hexdigest()
    assert not selected['object_resolved'] and not selected['ownership_proven']

    # A later scalar-only update must be checked at the current context even
    # though the container and its compressed user are both inherited.
    scalar_member = b'7 0 << /Title (Own scalar installed) >>'
    scalar_container = len(pdf_source)
    pdf_source.extend(b'4 0 obj\n<< /Type /ObjStm /N 1 /First 4 /Length 9 0 R >>\nstream\n'
                      +scalar_member+b'\nendstream\nendobj\n')
    scalar_offset = len(pdf_source)
    pdf_source.extend(b'9 0 obj\n'+str(len(scalar_member)).encode()+b'\nendobj\n')
    scalar_xref = len(pdf_source)
    pdf_source.extend((f'xref\n4 1\n{scalar_container:010} 00000 n \n9 1\n{scalar_offset:010} 00000 n \n'
                       f'trailer\n<< /Size 10 /Root 1 0 R /Info 7 0 R /Prev {member_xref} >>\n'
                       f'startxref\n{scalar_xref}\n%%EOF\n').encode())
    previous = scalar_xref
    for value in (len(scalar_member), 0):
        scalar_offset = len(pdf_source)
        pdf_source.extend(b'9 0 obj\n'+str(value).encode()+b'\nendobj\n')
        scalar_xref = len(pdf_source)
        pdf_source.extend((f'xref\n9 1\n{scalar_offset:010} 00000 n \ntrailer\n'
                           f'<< /Size 10 /Root 1 0 R /Info 7 0 R /Prev {previous} >>\n'
                           f'startxref\n{scalar_xref}\n%%EOF\n').encode())
        assessed = inspect_binary(bytes(pdf_source), pdf_source=True, pdf_decode_xrefs=True, pdf_object_streams=True)
        scalar_link, = dict(assessed.details)['compressed_object_current_links']
        witness = scalar_link['current_parameters']
        assert witness['current_parameter_values']['Length'] == value
        observation, = witness['source_integer_observations']['Length']
        assert observation['offset'] == scalar_offset and observation['primary_xref'] == scalar_xref
        if value:
            assert scalar_link['status'] == 'matched-declared-member'
        else:
            assert scalar_link['status'] == 'container-changed-from-decoded-parameters'
            assert 'member_locator' not in scalar_link
        previous = scalar_xref

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
    from opendoc_formats.anatomy_tree import inspect_container_tree

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
    assert dict(snapshot.details)['directory_colors_assessed']
    assert dict(snapshot.details)['directory_color_constraints_valid']
    assert dict(snapshot.details)['directory_name_order_assessed']
    assert dict(snapshot.details)['directory_name_order_valid']
    assert dict(snapshot.details)['directory_fields_assessed']
    assert dict(snapshot.details)['directory_field_constraints_valid']
    assert dict(snapshot.details)['directory_field_recommendations_met']
    assert dict(snapshot.details)['header_fields_assessed']
    assert dict(snapshot.details)['header_field_constraints_valid']
    assert dict(snapshot.details)['header_field_recommendations_met']
    header_source = bytearray(original)
    header_source[8] = header_source[34] = 1
    header_source[24] = 0
    header_snapshot = inspect_binary(bytes(header_source), capture=True)
    header_details = dict(header_snapshot.details)
    assert not header_details['header_field_constraints_valid']
    assert not header_details['header_field_recommendations_met']
    assert {(item['code'], item['rule']) for item in header_details['header_field_findings']} == {
        ('nonzero-header-clsid', 'must'), ('nonzero-reserved', 'must'), ('unexpected-minor-version', 'should'),
    }
    assert b''.join(item.payload for item in header_snapshot.items if item.kind == 'cfbf-physical-sector') == header_source
    field_source = bytearray(original)
    field_source[1024+128+80] = 1  # Stream CLSID: MUST zero.
    field_source[1024+128+96] = 1  # Stream state bits: SHOULD zero.
    field_source[1024+256+67] = 1  # Unallocated slot color: MUST zero.
    field_snapshot = inspect_binary(bytes(field_source), capture=True)
    field_details = dict(field_snapshot.details)
    assert not field_details['directory_field_constraints_valid']
    assert not field_details['directory_field_recommendations_met']
    assert {(item['code'], item['rule']) for item in field_details['directory_field_findings']} == {
        ('nonzero-stream-field', 'must'), ('nonzero-stream-state-bits', 'should'),
        ('nonzero-unallocated-field', 'must'),
    }
    assert next(item for item in field_snapshot.items if item.locator == 'cfbf:directory=1').payload == payload
    red_root = bytearray(original)
    red_root[1024+67] = 0
    assert dict(inspect_binary(bytes(red_root)).details)['directory_color_constraints_valid']
    bad_color = bytearray(original)
    bad_color[1024+128+67] = 2
    observed = inspect_binary(bytes(bad_color), capture=True)
    assert not dict(observed.details)['directory_color_constraints_valid']
    assert dict(observed.details)['directory_color_findings'][0]['offset'] == 1219
    assert b''.join(item.payload for item in observed.items if item.kind == 'cfbf-physical-sector') == bad_color
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, 'w'):
        pass
    payload = empty.getvalue()
    pool[:] = b'\x00' * 512
    pool[:len(payload)] = payload
    struct.pack_into('<Q', directory, 128 + 120, len(payload))
    compound = bytes(header + fat + directory + mini + pool)
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, 'w') as archive:
        archive.writestr('word/embeddings/own.bin', compound)
    tree = inspect_container_tree(outer.getvalue(), capture=True)
    assert [entry.snapshot.container for entry in tree.occurrences] == ['zip', 'cfbf', 'zip']
    assert tree.occurrences[-1].location == ('zip:/word/embeddings/own.bin', 'cfbf:directory=1')
    assert tree.occurrences[-1].snapshot.items == ()
    native = struct.pack('<I', len(payload)) + payload
    pool[:] = b'\x00' * 512
    pool[:len(native)] = native
    name = ('\x01Ole10Native\x00').encode('utf-16-le')
    directory[128:192] = name.ljust(64, b'\x00')
    struct.pack_into('<H', directory, 128 + 64, len(name))
    struct.pack_into('<Q', directory, 128 + 120, len(native))
    wrapped = bytes(header + fat + directory + mini + pool)
    tree = inspect_container_tree(wrapped, capture=True)
    assert [entry.snapshot.container for entry in tree.occurrences] == ['cfbf', 'ole-native', 'zip']
    assert tree.occurrences[-1].location == ('cfbf:directory=1', 'ole-native:data')
    assert b''.join(item.payload for item in tree.occurrences[1].snapshot.items) == native


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
        get_integration,
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
    assert version("opendoc-model") == "0.1.0"
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
        try:
            PdfDocument(b"missing engine")
        except BackendUnavailableError:
            pass
        else:
            raise AssertionError("Native PDF access should diagnose absent optional backend")
        find_libreoffice()
        docx_source = Path(__file__).resolve().parents[1] / "tests/corpus/native/native-edit.docx"
        with DocxPackage(docx_source) as package:
            assert not package.info.inspection_only and package.paragraphs and package.relationships
            assert package.to_bytes() == docx_source.read_bytes()
        from opendoc_formats.readers.docx import read_docx
        from opendoc_formats.readers.pptx import read_pptx
        from opendoc_formats.readers.text import extract_text

        text = read_docx(docx_source)
        assert text.engine == "native-docx" and text.blocks[0].text == "Before {{ value }} after"
        assert text.tables[0].rows[1] == ["Merged cell", "Merged cell"]
        assert extract_text(docx_source) == text.plain
        pptx_source = docx_source.parents[1] / "office/libreoffice-scientific-slides.pptx"
        slides = read_pptx(pptx_source)
        assert slides.engine == "native-pptx" and slides.pages == 2
        assert slides.blocks[0].text == "Scientific conversion quality" and slides.blocks[-1].page == 2
        assert slides.tables[0].rows[1] == ["Text", "Editability", "Exact"]
        assert all(name not in sys.modules for name in ("docx", "pptx", "lxml", "PIL"))
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
        optional = root / 'own-optional.tex'
        argument = r'[Short {]} and \textbf{bold} $x^2$]'
        optional.write_text(r'\begin{document}\section' + argument + r'{Visible}Body.\end{document}', encoding='utf-8')
        optional_model = read_document(optional)
        assert optional_model.success and optional_model.document.sections[0].blocks[0].plain_text == 'Visible'
        optional_record, = [value for value in get_integration(optional_model.document).preservation
                             if value.issue.reason == 'heading-short-title']
        optional_span = optional_record.extra['source_span']
        assert optional.read_text(encoding='utf-8')[optional_span['start']:optional_span['end']] == argument
        native_tex = DocumentModel(sections=[Section(blocks=[Paragraph(content=[TextRun('Own [text] & percent 100%')])])])
        for index in range(2):
            native_target = root / f'native-text-{index}.tex'
            native_report = write_document(native_tex, native_target)
            assert native_report.success and native_report.metrics['latex_route'] == 'native-text-v1'
            native_tex = document_from_json(document_to_json(read_document(native_target).document))
            assert native_tex.sections[0].blocks[0].plain_text == 'Own [text] & percent 100%'
        native_table = DocumentModel(sections=[Section(blocks=[Table([TableRow([
            TableCell([Paragraph([TextRun('Own & table')])]),
            TableCell([Paragraph([Formula('x^2', FormulaFormat.LATEX)])]), TableCell(),
        ]), TableRow([TableCell([Paragraph([TextRun('Own merged cell')])], column_span=2), TableCell()])])])])
        native_table.sections[0].blocks[0].properties['opendoc_formats.latex_tabular'] = {
            'version': 2, 'columns': '|l|l|l|', 'rules': [[None], [[1, 2], [3, 3]], [None]], 'trailing_break': True}
        for index in range(2):
            native_table = document_from_json(document_to_json(native_table))
            table_target = root / f'native-table-{index}.tex'
            table_report = write_document(native_table, table_target)
            assert table_report.success and table_report.metrics['latex_route'] == 'native-table-v1'
            table_source = table_target.read_text(encoding='utf-8')
            assert r'\begin{tabular}{|l|l|l|}' in table_source
            assert r'Own \& table' in table_source and r'\(x^2\)' in table_source
            assert '\\cline{1-2}\n\\cline{3-3}' in table_source
            table_import = read_document(table_target)
            assert table_import.success and isinstance(table_import.document.sections[0].blocks[0], Table)
            imported_table = table_import.document.sections[0].blocks[0]
            assert [cell.blocks[0].plain_text for cell in imported_table.rows[0].cells] == ['Own & table', 'x^2', '']
            assert len(imported_table.rows[1].cells) == 2 and imported_table.rows[1].cells[0].column_span == 2
            native_table = table_import.document
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
        chapters = root / 'source-chapters.tex'
        chapters.write_text(r'\documentclass[11pt,a5paper,oneside,openany]{book}\begin{document}\chapter{Own chapter}'
                            r'\section*{Own section}\subparagraph{Own sixth level}\end{document}', encoding='utf-8')
        chapter_model = read_document(chapters).document
        for index in range(2):
            target = root / f'chapters-{index}.tex'
            chapter_report = write_document(document_from_json(document_to_json(chapter_model)), target)
            assert chapter_report.success and chapter_report.metrics['latex_route'] == 'native-text-v1'
            chapter_model = read_document(target).document
            assert chapter_model.metadata['documentclass'] == 'book'
            assert chapter_model.metadata['opendoc_formats.latex_documentclass_options'] == {
                'version': 1, 'source': '11pt,a5paper,oneside,openany'}
            assert target.read_text(encoding='utf-8').startswith(r'\documentclass[11pt,a5paper,oneside,openany]{book}')
            assert [get_heading(p).level for p in chapter_model.sections[0].blocks] == [1, 2, 6]
            assert r'\chapter{Own chapter}' in target.read_text(encoding='utf-8')
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
        from opendoc_formats.readers.epub import read_epub, read_epub_metadata
        from opendoc_formats.readers.epub_package import read_epub_package

        book_report = write_document(DocumentModel(metadata={"creator": ["Own author"], "identifier": "urn:example:installed"},
                                                    sections=[Section(blocks=[Paragraph(content=[TextRun("Own EPUB")])])]), book)
        assert book_report.success and book_report.metrics["output_verified"], book_report.to_dict()
        package = read_epub_package(book)
        assert package.spine == (("chapter", "yes"),)
        metadata = read_epub_metadata(book)
        assert metadata == package.dc_values and metadata["creator"] == ("Own author",)
        assert metadata["identifier"] == ("urn:example:installed",)
        if not (args.epub or args.all_formats):
            extracted = read_epub(book)
            assert extracted.engine == "native-epub-xhtml" and extracted.plain == "Own EPUB"
            imported_book = read_document(book)
            assert imported_book.success, imported_book.issues
            assert imported_book.document.sections[0].blocks[0].plain_text == "Own EPUB"
            assert "bs4" not in sys.modules
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
                archive.writestr("c.xhtml", '''<html><head><meta charset="utf-8"/></head><body>
                    <p id="literal%FF" style="position:absolute;font-size:12pt">Native EPUB 123</p>
                    <table><tr><td colspan="2">Own cell</td></tr></table>
                    <math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>
                    <blockquote id="compound"><p>Before</p><table id="nested-source-table">
                    <tr><td>Own original nested cell</td></tr></table><p>After</p></blockquote>
                    <p id="media-owner"><a href="#media-math">Go math</a>
                    <math id="media-math" xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>
                    <a href="#media-svg">Go SVG</a><svg id="media-svg" xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 2 2"><path d="M0 0L2 2"/></svg><span id="inline-empty"></span>
                    <a href="#inline-empty">Go empty</a></p>
                    <p id="café">Unicode target A</p><p id="cafè">Unicode target B</p>
                    <p><a href="#caf%C3%A9">Go Unicode A</a></p><p><a href="#caf%C3%A8">Go Unicode B</a></p>
                    <p><a href="//example.invalid/own.xhtml#part">Remote URI</a></p>
                    <p><a href="#literal%25FF">Literal percent</a></p>
                    <p><a id="invalid-uri" href="%FF.xhtml">Unresolved URI</a></p>
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
            remote, literal, unresolved = result.document.sections[0].blocks[-3:]
            assert remote.content[0].link == '//example.invalid/own.xhtml#part'
            assert literal.content[0].link == '#'+result.document.sections[0].blocks[0].properties['anchor_id']
            marker, unresolved_run = unresolved.content
            assert marker.text == '' and marker.link is None
            assert unresolved_run.text == 'Unresolved URI' and unresolved_run.link is None
            target_a, target_b, go_a, go_b = result.document.sections[0].blocks[-7:-3]
            assert target_a.properties['anchor_id'] != target_b.properties['anchor_id']
            assert go_a.content[0].link == '#'+target_a.properties['anchor_id']
            assert go_b.content[0].link == '#'+target_b.properties['anchor_id']
            assert any(issue.reason == 'unresolved-reference-uri' and issue.measurement['value'] == '%FF.xhtml'
                       for issue in result.issues)
            from html.parser import HTMLParser
            from urllib.parse import unquote

            from opendoc_model import Image, get_anchor, get_integration

            class EpubTargets(HTMLParser):
                def __init__(self) -> None:
                    super().__init__()
                    self.ids: list[str] = []
                    self.links: list[str] = []

                def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                    values = dict(attrs)
                    if identifier := values.get('id'):
                        self.ids.append(identifier)
                    if (href := values.get('href')) and href.startswith('#'):
                        self.links.append(unquote(href[1:]))

            compound, = [record for record in get_integration(result.document).preservation
                         if record.issue.reason == 'nested-table-block']
            assert compound.state.value == 'opaque' and compound.provenance.object_id == 'nested-source-table'
            retained = result.document.resources[compound.extra['resource_id']]
            with zipfile.ZipFile(source) as archive:
                assert retained.data == archive.read('c.xhtml')
            restored = document_from_json(document_to_json(result.document))
            assert restored.resources[retained.id].data == retained.data
            for cycle in range(2):
                restored = document_from_json(document_to_json(restored))
                media_paragraph = next(block for block in restored.sections[0].blocks
                                       if block.properties.get('anchor_id') == 'epub-c.xhtml--media-owner')
                targets = [item for item in media_paragraph.content if get_anchor(item) is not None]
                assert len(targets) == 3 and isinstance(targets[0], Formula) and isinstance(targets[1], Image)
                assert isinstance(targets[2], TextRun) and targets[2].text == ''
                before_export = document_to_json(restored)
                html_output = root/f'epub-targets-{cycle}.html'
                html_report = write_document(restored, html_output)
                assert html_report.success, html_report.issues
                parsed = EpubTargets()
                parsed.feed(html_output.read_text(encoding='utf-8'))
                assert len(parsed.ids) == len(set(parsed.ids)) and set(parsed.links) <= set(parsed.ids)
                assert document_to_json(restored) == before_export
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
