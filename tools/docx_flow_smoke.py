"""Exercise the installed public Word flow API from an engine-free canonical JSON."""

import argparse
import hashlib
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory


def owned_font_smoke(root: Path) -> None:
    """Use only the owned font bytes from a fixture, in a fresh semantic document."""
    from opendoc_model import (
        DocumentModel,
        FontReference,
        Length,
        Paragraph,
        Resource,
        ResourceKind,
        Section,
        TextRun,
        TextStyle,
        document_from_json,
        document_to_json,
        get_font_reference,
        load_document,
        set_font_reference,
    )

    from opendoc_formats import read_document, write_document

    fixture = Path(__file__).resolve().parents[1]/'tests/native/data/text-layout-v1.json'
    original = fixture.read_bytes()
    assert hashlib.sha256(original).hexdigest() == '04c7254f88c20bfa0ddd67d7b018b82e2754282ea4b155b0bf8a329ec17c7a16'
    font_data = load_document(fixture).resources['font'].data
    style = TextStyle(font_family='OwnPlacement', font_size=Length(12))
    set_font_reference(style, FontReference('owned-font', 0))
    document = DocumentModel(sections=[Section(blocks=[Paragraph([TextRun('AB', style)])])], resources={
        'owned-font': Resource('owned-font', ResourceKind.FONT, 'font/ttf', font_data),
    })
    for index in range(2):
        document = document_from_json(document_to_json(document))
        before = document_to_json(document)
        path = root/f'owned-font-{index}.docx'
        report = write_document(document, path)
        assert report.success, report.issues
        assert not any(issue.feature in {'font-resource', 'font-glyphs', 'font-embedding'} for issue in report.issues)
        assert report.metrics['font_embedding']['embedded_faces'] >= 1
        assert report.metrics['font_embedding']['source_bytes'] == report.metrics['font_embedding']['subset_bytes']
        assert document_to_json(document) == before
        restored = read_document(path)
        assert restored.success, restored.issues
        document = restored.document
        assert document.sections[0].blocks[0].plain_text == 'AB'
        assert any(resource.kind is ResourceKind.FONT and resource.data == font_data
                   for resource in document.resources.values())
        reference = get_font_reference(document.sections[0].blocks[0].content[0].style)
        assert reference is not None and document.resources[reference.resource_id].data == font_data
    assert fixture.read_bytes() == original


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minimal', action='store_true')
    parser.add_argument('--fragmented', action='store_true')
    parser.add_argument('--cell-borders', action='store_true')
    args = parser.parse_args()
    args.fragmented = args.fragmented or args.cell_borders
    import opendoc_formats

    assert 'site-packages' in Path(opendoc_formats.__file__).parts, 'Use the installed wheel for this acceptance'
    if args.minimal:
        for name in ('fontTools', 'pymupdf', 'fitz', 'pdf2docx', 'cv2', 'numpy', 'PIL'):
            assert importlib.util.find_spec(name) is None, name

    from docx import Document
    from opendoc_model import (
        Box,
        ColorValue,
        DocumentModel,
        Image,
        Paragraph,
        Resource,
        ResourceKind,
        Section,
        Table,
        TableCell,
        TableRow,
        TextRun,
        document_from_json,
        document_to_json,
    )

    from opendoc_formats import DocxProfile, ExportOptions, get_object_mapping, write_document
    from opendoc_formats.writers.docx_writer import write_docx_model

    # The original 3x3 grid remains as eight independent vector occurrences.
    edges_x, edges_y = [70, 170, 270, 370], [150, 190, 230, 270]
    model = DocumentModel(source_format='pdf', sections=[Section()])
    section = model.sections[0]
    segments = [((x, 150), (x, 270)) for x in edges_x]+[((70, y), (370, y)) for y in edges_y]
    if args.fragmented:
        segments = [(tuple(a[axis]+(b[axis]-a[axis])*part/3 for axis in range(2)),
                     tuple(a[axis]+(b[axis]-a[axis])*(part+1)/3 for axis in range(2)))
                    for a, b in segments for part in range(3)]
    for index, (a, b) in enumerate(segments):
        key = f'own-grid-{index}'
        palette = ((.5, 'FF0000'), (.75, 'FF00FF'), (1, '000000'), (1.5, '00FF00'), (2.25, '00FFFF'), (3, '0000FF'))
        style_index = (round((a[0]-70)/100)+round((a[1]-150)/40) if a[0] == b[0] else
                       round((a[1]-150)/40)+2*round((a[0]-70)/100))
        width, color = palette[style_index % len(palette)] if args.cell_borders else (1, '000000')
        model.resources[key] = Resource(key, ResourceKind.VECTOR_IMAGE, 'application/pdf+vector', data=b'own-grid', properties={
            'items': [['l', list(a), list(b)]], 'width': width, 'stroke': ColorValue.from_hex(color).to_dict(),
        })
        section.blocks.append(Paragraph([Image(key, box=Box(a[0], a[1], b[0]-a[0], b[1]-a[1]))]))
    # Only current rows R2/R3 and columns C1/C2 are selected.
    table = Table([TableRow([TableCell([Paragraph([TextRun(f'R{row+1}C{col+1}')])], properties={
        'pdf_cell_bbox': [edges_x[col], edges_y[row], edges_x[col+1], edges_y[row+1]],
    }) for col in range(2)]) for row in (1, 2)], properties={
        'pdf_column_edges': edges_x, 'pdf_row_edges': edges_y,
    })
    section.blocks.append(table)
    model = document_from_json(document_to_json(model))
    original = document_to_json(model)
    with TemporaryDirectory(prefix='opendoc_flow_smoke_') as directory:
        path = Path(directory) / 'flow.docx'
        for public in (False, True):
            profile = DocxProfile(layout='flow')
            report = (write_document(model, path, options=ExportOptions(docx_profile=profile)) if public
                      else write_docx_model(model, path, profile=profile))
            assert report.success, report.issues
            assert any(issue.feature == 'docx.flow-layout' for issue in report.issues)
            native = Document(path).tables[0]
            assert [[cell.text for cell in row.cells] for row in native.rows] == [['R2C1', 'R2C2'], ['R3C1', 'R3C2']]
            mapping = get_object_mapping(report)
            assert len(mapping.sources) == (24 if args.fragmented else 8)
            assert len(mapping.targets) == 1 and mapping.publication == 'published'
            assert sum(len(entry.source_ids) for entry in mapping.entries if entry.extra['range_exclusion']) == (
                12 if args.fragmented else 2)
            assert mapping.result_id == 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
            assert document_to_json(model) == original
            if args.cell_borders:
                assert mapping.targets[0].extra['cell_borders']
                from opendoc_model import get_borders

                from opendoc_formats import read_document

                for cycle in range(2):
                    restored = read_document(path)
                    assert restored.success, restored.issues
                    actual_table = next(b for b in restored.document.sections[0].blocks if isinstance(b, Table))
                    border = get_borders(actual_table.rows[0].cells[0]).sides['top']
                    assert border.width_pt == .75 and border.color.to_hex().upper() == '#FF00FF'
                    assert write_document(document_from_json(document_to_json(restored.document)), path).success
        if args.minimal:
            owned_font_smoke(Path(directory))
    print('Installed DOCX flow: public/direct API, cropped cells, grid mapping and source immutability passed')
    if args.fragmented:
        print('Fragmented grid: all 24 sources accounted, 12 excluded by the crop, no PDF engine used')
    if args.cell_borders:
        print('Cell-specific native borders retain widths and colors through two JSON/DOCX cycles')
    if args.minimal:
        print('Owned static TTF: full program retained through two JSON/DOCX cycles without fontTools')


if __name__ == '__main__':
    main()
