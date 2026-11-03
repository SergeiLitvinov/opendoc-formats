"""Malformed URI escapes must not bind through replacement characters to a different ZIP part."""

import pytest

from opendoc_formats.docx import DocxPackage
from opendoc_formats.errors import InvalidDocumentError, UnsupportedDocumentError
from tests.binary_fixtures import PR
from tests.native.test_docx_consumer_contract import original


def source(target, part, *, external=False):
    mode = ' TargetMode="External"' if external else ''
    relationships = (f'<Relationships xmlns="{PR}"><Relationship Id="own" Type="urn:own" '
                     f'Target="{target}"{mode}/></Relationships>').encode()
    return original('<w:p><w:r><w:t>Own unchanged body</w:t></w:r></w:p>', [
        ('word/_rels/document.xml.rels', relationships), ('custom/'+part+'.xml', b'<own/>')])


@pytest.mark.parametrize('inspection_only', [False, True])
@pytest.mark.parametrize('encoded,wrong_name', [('%FF', '�'), ('%C3%28', '�('), ('%C0%AF', '��'), ('%ED%A0%80', '���')])
def test_invalid_utf8_never_binds_a_replacement_character_part(tmp_path, encoded, wrong_name, inspection_only):
    data = source('../custom/'+encoded+'.xml', wrong_name)
    path = tmp_path/'own.docx'
    path.write_bytes(data)
    with pytest.raises(UnsupportedDocumentError, match=r'word/_rels/document.xml.rels.*own.*UTF-8'):
        DocxPackage(path, inspection_only=inspection_only)
    assert path.read_bytes() == data


@pytest.mark.parametrize('encoded', ['%', '%A', '%GG', '%2G'])
def test_malformed_percent_escape_never_binds_a_literal_malformed_name(encoded):
    with pytest.raises(InvalidDocumentError, match=r'word/_rels/document.xml.rels.*own.*percent'):
        DocxPackage(source('../custom/'+encoded+'.xml', encoded))


@pytest.mark.parametrize('encoded,name', [('%C3%A9', 'é'), ('%F0%9F%A6%8A', '🦊'), ('%252F', '%2F'),
                                         ('%25', '%'), ('%EF%BF%BD', '�')])
def test_valid_utf8_and_genuine_replacement_character_names_remain_exact(encoded, name):
    data = source('../custom/'+encoded+'.xml', name)
    with DocxPackage(data) as package:
        assert package.to_bytes() == data and not package.info.issues
        assert any(part.name == 'custom/'+name+'.xml' for part in package.info.parts)


def test_external_target_remains_inert_opaque_metadata():
    data = source('https://example.invalid/%FF', 'own', external=True)
    with DocxPackage(data) as package:
        assert package.to_bytes() == data
