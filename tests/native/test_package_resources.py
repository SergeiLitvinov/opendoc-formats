"""Generic resource assembly owns DOCX topology and leaves consumer models unchanged."""

import pytest
from opendoc_model import DocumentModel, PackageGraph, Resource, ResourceKind

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError
from opendoc_formats.package_resources import assemble_docx_package_resources


def native_resource(key, data=b"<notes/>", **properties):
    return Resource(key, ResourceKind.ATTACHMENT, "application/xml", data=data, properties=properties)


def test_standard_roles_and_native_links_build_graph_without_mutation():
    document = DocumentModel(
        resources={
            "notes": native_resource(
                "notes",
                relationships=[
                    {"id": "rIdImage", "type": "urn:fixture:image", "resource_id": "picture"},
                    {"id": "rIdLink", "type": "urn:fixture:link", "external": True, "target": "https://example.invalid"},
                ],
            ),
            "picture": Resource("picture", ResourceKind.RASTER_IMAGE, "image/png", data=b"PNG", filename="note.png"),
        }
    )
    result = assemble_docx_package_resources(document, {"notes": "footnotes"}, consume_resources=True)
    assert document.package is None and set(document.resources) == {"notes", "picture"}
    assert result is not document and result.resources == {}
    graph = result.package
    assert graph.format == "ooxml" and graph.root == "/word/document.xml"
    assert set(graph.parts) == {"/word/footnotes.xml", "/word/media/note.png"}
    assert graph.related_part(graph.root, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes")
    assert any(r.id == "rIdImage" and r.target == "/word/media/note.png" for r in graph.relationships)
    assert any(r.id == "rIdLink" and r.external for r in graph.relationships)
    assert result.validate() == []


@pytest.mark.parametrize(
    "role,part",
    [
        ("footnotes", "/word/footnotes.xml"),
        ("endnotes", "/word/endnotes.xml"),
        ("numbering", "/word/numbering.xml"),
        ("styles", "/word/styles.xml"),
        ("theme", "/word/theme/theme1.xml"),
        ("media", "/word/media/item"),
    ],
)
def test_standard_role_contract(role, part):
    document = DocumentModel(resources={"item": native_resource("item")})
    result = assemble_docx_package_resources(document, {"item": role})
    assert part in result.package.parts
    assert "item" in result.resources


def test_existing_graph_is_preserved_as_independent_copy():
    document = DocumentModel(package=PackageGraph("ooxml"))
    result = assemble_docx_package_resources(document, {})
    assert result.package == document.package and result.package is not document.package


@pytest.mark.parametrize(
    "properties",
    [
        {"partname": "/../outside.xml"},
        {"partname": "relative.xml"},
        {"partname": "/word\\outside.xml"},
        {"relationships": "not list"},
        {"relationships": [{"id": "id", "type": "uri", "resource_id": "missing"}]},
        {"relationships": [{"id": "id", "type": "uri", "external": True}]},
    ],
)
def test_invalid_native_metadata_is_diagnosed(properties):
    document = DocumentModel(resources={"item": native_resource("item", **properties)})
    with pytest.raises(InvalidDocumentError):
        assemble_docx_package_resources(document, {"item": "footnotes"})
    assert document.package is None


def test_missing_resource_limit_and_cancellation():
    document = DocumentModel(resources={"item": native_resource("item")})
    with pytest.raises(InvalidDocumentError):
        assemble_docx_package_resources(document, {"missing": "footnotes"})
    with pytest.raises(ResourceLimitError):
        assemble_docx_package_resources(document, {"item": "footnotes"}, max_bytes=1)
    with pytest.raises(OperationCancelledError):
        assemble_docx_package_resources(document, {"item": "footnotes"}, cancelled=lambda: True)


def test_non_embedded_resources_are_never_opened():
    resource = Resource("item", ResourceKind.ATTACHMENT, "application/xml", source="https://example.invalid/item.xml")
    with pytest.raises(InvalidDocumentError):
        assemble_docx_package_resources(DocumentModel(resources={"item": resource}), {"item": "footnotes"})
