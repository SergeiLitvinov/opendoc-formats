from zipfile import ZipFile

import pytest

from opendoc_formats import read_ooxml_core_properties
from opendoc_formats.errors import InvalidDocumentError, UnsupportedDocumentError

_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
_TYPE = _REL + '/metadata/core-properties'
_CORE = 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties'
_PROPERTIES = f'''<cp:coreProperties xmlns:cp="{_CORE}" xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Проект &amp; план</dc:title><dc:creator>Автор</dc:creator><cp:revision>001</cp:revision>
</cp:coreProperties>'''


def _package(path, edge, properties):
    with ZipFile(path, 'w') as archive:
        archive.writestr('_rels/.rels', f'<Relationships xmlns="{_REL}">{edge}</Relationships>')
        archive.writestr('properties/main.xml', properties)
        archive.writestr('docProps/core.xml', 'Unrelated decoy; must not be read.')
        archive.writestr('ppt/slides/slide1.xml', '<unreadable XML')


_EDGE = f'<Relationship Id="p1" Type="{_TYPE}" Target="properties/main.xml"/>'


def test_reads_only_declared_physical_core_properties(tmp_path):
    path = tmp_path / 'slides.pptx'
    _package(path, _EDGE, _PROPERTIES)
    assert read_ooxml_core_properties(path) == {'title': 'Проект & план', 'creator': 'Автор', 'revision': '001'}
    _package(path, '', _PROPERTIES)
    assert read_ooxml_core_properties(path) == {}


@pytest.mark.parametrize('edge', [_EDGE + _EDGE, _EDGE.replace('/>', ' TargetMode="External"/>'),
                                  _EDGE.replace('main.xml', 'main.xml#fragment')])
def test_rejects_ambiguous_and_nonlocal_relationships(tmp_path, edge):
    path = tmp_path / 'slides.pptx'
    _package(path, edge, _PROPERTIES)
    with pytest.raises(InvalidDocumentError, match='core properties relationship'):
        read_ooxml_core_properties(path)


def test_rejects_dtd_before_expanding_entities(tmp_path):
    path = tmp_path / 'slides.pptx'
    _package(path, _EDGE, '<!DOCTYPE coreProperties [<!ENTITY x "test">]>' + _PROPERTIES)
    with pytest.raises(UnsupportedDocumentError, match='DTD'):
        read_ooxml_core_properties(path)
