"""Тесты разделённых геометрического и семантического слоёв PDF."""

import io

import fitz
import pytest
from PIL import Image

from opendoc_formats.readers.pdf import read_pdf_geometry
from opendoc_formats.readers.pdf_geometry import (
    PdfGeometryDocument,
    PdfLineGeometry,
    PdfPageGeometry,
    PdfSpanGeometry,
    PdfTextBlockGeometry,
)
from opendoc_formats.readers.pdf_ocr_merge import merge_pdf_with_ocr
from opendoc_formats.readers.pdf_ocr_types import OcrBlockGeometry, OcrPageResult
from opendoc_formats.readers.pdf_semantic import analyze_pdf_geometry
from opendoc_formats.types import BlockType
from tests.corpus.multiformat import build_multiformat_corpus


def _build_positioned_pdf(path):
    document = fitz.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((40, 60), "Geometry heading", fontname="helv", fontsize=14)
    page.insert_text((40, 95), "Semantic paragraph", fontname="Times-Roman", fontsize=11)
    document.set_metadata({"title": "Layered PDF", "author": "OpenDoc Formats"})
    document.save(path)
    document.close()


def test_read_pdf_geometry_preserves_pages_coordinates_and_spans(tmp_path):
    path = tmp_path / "positioned.pdf"
    _build_positioned_pdf(path)

    geometry = read_pdf_geometry(str(path))

    assert geometry.engine == "pymupdf"
    assert geometry.metadata["title"] == "Layered PDF"
    assert len(geometry.pages) == 1
    page = geometry.pages[0]
    assert page.number == 1
    assert page.width == 300
    assert page.height == 400
    assert len(page.text_blocks) == 2
    heading = page.text_blocks[0]
    assert heading.text == "Geometry heading"
    assert heading.bbox[0] == 40
    assert heading.bbox[1] < 60 < heading.bbox[3]
    assert heading.lines[0].spans[0].font == "Helvetica"
    assert heading.lines[0].spans[0].size == 14


def test_analyze_pdf_geometry_builds_semantic_text_without_reopening_pdf(tmp_path):
    path = tmp_path / "semantic.pdf"
    _build_positioned_pdf(path)
    geometry = read_pdf_geometry(str(path))

    text = analyze_pdf_geometry(geometry)

    assert text.engine == "pymupdf"
    assert text.pages == 1
    assert text.plain == "Geometry heading\nSemantic paragraph"
    assert [block.page for block in text.blocks] == [1, 1]
    assert text.blocks[0].meta["bbox"] == list(geometry.pages[0].text_blocks[0].bbox)
    assert text.blocks[0].meta["page_width"] == 300
    assert text.blocks[0].meta["page_height"] == 400


def _geometry_block(number, text, bbox):
    span = PdfSpanGeometry(text=text, bbox=bbox, origin=(bbox[0], bbox[3]))
    line = PdfLineGeometry(spans=(span,), bbox=bbox)
    return PdfTextBlockGeometry(lines=(line,), bbox=bbox, number=number)


def test_analyze_pdf_geometry_orders_spanning_blocks_and_two_columns():
    page = PdfPageGeometry(
        number=1,
        width=300,
        height=400,
        text_blocks=(
            _geometry_block(0, "Document title", (20, 20, 280, 45)),
            _geometry_block(1, "Right first", (170, 70, 280, 90)),
            _geometry_block(2, "Left first", (20, 65, 130, 85)),
            _geometry_block(3, "Page footer", (20, 350, 280, 370)),
            _geometry_block(4, "Right second", (170, 110, 280, 130)),
            _geometry_block(5, "Left second", (20, 105, 130, 125)),
        ),
    )

    text = analyze_pdf_geometry(PdfGeometryDocument(pages=[page]))

    assert [block.text for block in text.blocks] == [
        "Document title",
        "Left first",
        "Left second",
        "Right first",
        "Right second",
        "Page footer",
    ]
    assert [block.meta["reading_order"] for block in text.blocks] == list(range(6))
    assert [block.meta["column"] for block in text.blocks] == [None, 0, 0, 1, 1, None]
    assert all(block.meta["column_count"] == 2 for block in text.blocks)
    assert text.blocks[0].meta["spanning"] is True
    assert text.blocks[-1].meta["spanning"] is True
    assert text.blocks[1].meta["gutter"] == [130, 170]


def test_pdf_geometry_and_semantics_restore_ruled_table(tmp_path):
    pdf = build_multiformat_corpus(tmp_path)["pdf"]

    geometry = read_pdf_geometry(pdf)
    table = geometry.pages[0].tables[0]
    text = analyze_pdf_geometry(geometry)
    table_blocks = [block for block in text.blocks if block.type is BlockType.TABLE]

    assert table.strategy == "lines_strict"
    assert table.row_count == 3
    assert table.column_count == 3
    assert table.rows == (
        ("Feature", "Expected", "Observed"),
        ("Text", "Editable", "Exact"),
        ("Vector", "Native", "Preserved"),
    )
    assert len(table.cells) == 9
    assert all(cell.bbox is not None for cell in table.cells)
    assert len(text.tables) == 1
    assert text.tables[0].rows == [list(row) for row in table.rows]
    assert len(table_blocks) == 1
    assert table_blocks[0].meta["table_strategy"] == "lines_strict"
    assert table_blocks[0].meta["row_count"] == 3
    assert text.plain.count("Feature") == 1


def test_pdf_geometry_restores_borderless_table_by_text_alignment(tmp_path):
    path = tmp_path / "borderless-table.pdf"
    document = fitz.open()
    page = document.new_page(width=300, height=240)
    for y, values in ((60, ("Name", "Value")), (90, ("Alpha", "10")), (120, ("Beta", "20"))):
        page.insert_text((40, y), values[0], fontname="helv", fontsize=10)
        page.insert_text((180, y), values[1], fontname="helv", fontsize=10)
    document.save(path, no_new_id=True)
    document.close()

    geometry = read_pdf_geometry(path)

    assert len(geometry.pages[0].tables) == 1
    table = geometry.pages[0].tables[0]
    assert table.strategy == "text"
    assert table.rows == (("Name", "Value"), ("Alpha", "10"), ("Beta", "20"))


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_pdf_semantics_keeps_aligned_prose_columns_out_of_text_table(tmp_path, rotation):
    path = tmp_path / "aligned-prose.pdf"
    columns = [[f"{side} paragraph {index} has several words." for index in range(1, 4)] for side in ("Left", "Right")]
    with fitz.open() as document:
        page = document.new_page(width=500, height=260)
        for x, paragraphs in zip((40, 280), columns, strict=True):
            for index, paragraph in enumerate(paragraphs):
                page.insert_text((x, 70 + 30 * index), paragraph)
        page.set_rotation(rotation)
        document.save(path, no_new_id=True)

    geometry = read_pdf_geometry(path)
    assert not geometry.pages[0].tables
    text = analyze_pdf_geometry(geometry)
    assert text.plain.splitlines() == columns[0] + columns[1]
    assert [block.meta["column"] for block in text.blocks] == [0, 0, 0, 1, 1, 1]
    assert {(block.meta["page_width"], block.meta["page_height"]) for block in text.blocks} == {(500, 260)}
    first = geometry.pages[0].text_blocks[0]
    ocr = OcrPageResult(blocks=[OcrBlockGeometry(first.text, first.bbox, 0.99)])
    merged = merge_pdf_with_ocr(geometry, [ocr])
    assert merged.plain == text.plain
    assert [block.meta["column"] for block in merged.blocks] == [0, 0, 0, 1, 1, 1]


@pytest.mark.parametrize("rows", [
    (("Item", "Value"), ("Alpha", "10"), ("Beta", "20")),
    (("Item", "Value"),),
    (("Item",), ("Alpha",)),
])
def test_pdf_geometry_restores_table_with_filled_rectangles_instead_of_strokes(tmp_path, rows):
    path = tmp_path / "filled-table.pdf"
    with fitz.open() as document:
        page = document.new_page(width=350, height=360)
        for row, values in enumerate(rows):
            for column, label in enumerate(values):
                x, y = 35 + 100 * column, 40 + 70 * row
                fill = (0.85, 0.85, 0.85) if (row + column) % 2 else (0.8, 0.85, 1)
                page.draw_rect((x, y, x + 100, y + 70), color=None, fill=fill)
                page.insert_text((x + 10, y + 26), label)
        document.save(path, no_new_id=True)

    geometry = read_pdf_geometry(path)
    table, = geometry.pages[0].tables
    assert table.strategy == "lines"
    assert table.rows == rows
    assert table.column_edges == tuple(35 + 100 * index for index in range(len(rows[0]) + 1))
    assert table.row_edges == tuple(40 + 70 * index for index in range(len(rows) + 1))
    assert analyze_pdf_geometry(geometry).tables[0].rows == [list(row) for row in rows]


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
@pytest.mark.parametrize("placement", ["below", "beside", "diagonal"])
def test_pdf_geometry_keeps_ruled_and_borderless_tables_on_one_page(tmp_path, rotation, placement):
    path = tmp_path / "mixed-tables.pdf"
    ruled = (("Feature", "Value"), ("Alpha", "10"), ("Beta", "20"))
    borderless = (("Item", "Count"), ("Gamma", "30"), ("Delta", "40"))
    with fitz.open() as document:
        page = document.new_page(width=550, height=450)
        for x in (35, 140, 245):
            page.draw_line((x, 40), (x, 130))
        for y in (40, 70, 100, 130):
            page.draw_line((35, y), (245, y))
        x = 45 if placement == "below" else 300
        first_y = 60 if placement == "beside" else 245
        for left, top, rows in ((45, 60, ruled), (x, first_y, borderless)):
            for index, (label, value) in enumerate(rows):
                y = top + 30 * index
                page.insert_text((left, y), label)
                page.insert_text((left + 110, y), value)
        page.set_rotation(rotation)
        document.save(path, no_new_id=True)

    original = path.read_bytes()
    geometry = read_pdf_geometry(path)
    assert geometry.pages[0].rotation == rotation
    assert path.read_bytes() == original
    assert [(table.strategy, table.rows) for table in geometry.pages[0].tables] == [
        ("lines_strict", ruled), ("text", borderless),
    ]
    text = analyze_pdf_geometry(geometry)
    assert [block.type for block in text.blocks] == [BlockType.TABLE, BlockType.TABLE]
    assert [table.rows for table in text.tables] == [[list(row) for row in values] for values in (ruled, borderless)]


def test_pdf_semantics_classifies_captions_formulas_and_repeated_running_content(tmp_path):
    path = tmp_path / "classified.pdf"
    image_buffer = io.BytesIO()
    Image.new("RGB", (40, 24), "#2E74B5").save(image_buffer, format="PNG")
    document = fitz.open()
    for page_number in range(1, 4):
        page = document.new_page(width=300, height=400)
        page.insert_text((35, 20), "Journal of Conversion", fontname="helv", fontsize=8)
        page.insert_text((35, 90), f"Body paragraph on sheet {page_number}.", fontname="Times-Roman", fontsize=11)
        if page_number == 1:
            page.insert_text((75, 165), "E = mc^2 + integral_0^1 x^2", fontname="cour", fontsize=13)
            page.insert_image(fitz.Rect(80, 210, 220, 250), stream=image_buffer.getvalue())
            page.insert_text((75, 270), "Figure 1. Control curve", fontname="helv", fontsize=9)
        page.insert_text((125, 385), f"Page {page_number}", fontname="helv", fontsize=8)
    document.save(path, no_new_id=True)
    document.close()

    geometry = read_pdf_geometry(path)
    assert [page.tables for page in geometry.pages] == [(), (), ()]
    text = analyze_pdf_geometry(geometry)
    headers = [block for block in text.blocks if block.meta.get("semantic_role") == "header"]
    footers = [block for block in text.blocks if block.meta.get("semantic_role") == "footer"]
    equations = [block for block in text.blocks if block.type is BlockType.EQUATION]
    captions = [block for block in text.blocks if block.type is BlockType.CAPTION]

    assert len(headers) == 3
    assert len(footers) == 3
    assert all(block.meta["excluded_from_plain"] is True for block in [*headers, *footers])
    assert all(block.meta["semantic_confidence"] == 0.98 for block in [*headers, *footers])
    assert "Journal of Conversion" not in text.plain
    assert "Page 1" not in text.plain
    assert len(equations) == 1
    assert equations[0].meta["semantic_role"] == "formula"
    assert "equality" in equations[0].meta["semantic_evidence"]
    assert equations[0].meta["semantic_confidence"] >= 0.65
    assert len(captions) == 1
    assert captions[0].text == "Figure 1. Control curve"
    assert captions[0].meta["semantic_evidence"] == ["caption-prefix", "near-image-0"]
