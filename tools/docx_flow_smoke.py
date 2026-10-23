"""Exercise the installed public Word flow API from an engine-free canonical JSON."""

import argparse
import hashlib
import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minimal', action='store_true')
    args = parser.parse_args()
    if args.minimal:
        for name in ('pymupdf', 'pdf2docx', 'cv2', 'numpy', 'PIL'):
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
    for index, (a, b) in enumerate(segments):
        key = f'own-grid-{index}'
        model.resources[key] = Resource(key, ResourceKind.VECTOR_IMAGE, 'application/pdf+vector', data=b'own-grid', properties={
            'items': [['l', list(a), list(b)]], 'width': 1, 'stroke': ColorValue.from_hex('000000').to_dict(),
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
            assert len(mapping.sources) == 8 and len(mapping.targets) == 1 and mapping.publication == 'published'
            assert mapping.result_id == 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
            assert document_to_json(model) == original
    print('Installed DOCX flow: public/direct API, cropped cells, grid mapping and source immutability passed')


if __name__ == '__main__':
    main()
