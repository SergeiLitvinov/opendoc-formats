"""Actual loss inventory, nested cell text and occurrence order in legacy views."""

from threading import Event

import pytest
from opendoc_model import (
    INTEGRATION_PROPERTY,
    ArtifactLimitError,
    DocumentLimits,
    DocumentModel,
    Footnote,
    Formula,
    FormulaFormat,
    Image,
    IntegrationModel,
    Length,
    PackageGraph,
    PackagePart,
    PageSettings,
    Paragraph,
    PreservationState,
    Provenance,
    ProvenanceEvent,
    Resource,
    ResourceKind,
    Section,
    SourceFile,
    SourceMap,
    Table,
    TableCell,
    TableRow,
    TextRun,
    TextStyle,
    document_from_json,
    document_to_json,
    get_integration,
    set_integration,
)

from opendoc_formats.errors import OperationCancelledError
from opendoc_formats.support.cancellation import cancellation_scope, checkpoint
from opendoc_formats.support.document_adapters import document_to_text, text_to_document
from opendoc_formats.types import Block, BlockType, Text
from opendoc_formats.types import Table as LegacyTable


def paragraph(value):
    return Paragraph(content=[TextRun(value)])


def own_model():
    origin = Provenance('docx', 'own.docx', page=3, package_part='/word/document.xml')
    origin.events.append(ProvenanceEvent('own.import', 'Own original history'))
    cell = TableCell(blocks=[
        Paragraph(content=[TextRun('Own cell ', style=TextStyle(bold=True), link='https://example.invalid/own'),
                           Formula('x^2', FormulaFormat.LATEX, fallback_text='x squared'),
                           Image('own-image', alt_text=' own inline image')], provenance=origin),
        Table(rows=[TableRow(cells=[TableCell(blocks=[paragraph('Nested')])])]),
        Formula('y+1', FormulaFormat.LATEX, fallback_text='y plus one'),
        Image('own-image', alt_text='cell block image'),
    ], column_span=2)
    return DocumentModel(
        sections=[Section(blocks=[paragraph('Before'), Table(rows=[TableRow(cells=[cell])]), paragraph('After')],
                          headers=[paragraph('Excluded header')])], source_format='docx',
        resources={'own-image': Resource('own-image', ResourceKind.RASTER_IMAGE, 'image/png', data=b'own image bytes')},
        styles={'Own': TextStyle(italic=True)}, metadata={'title': 'Own title'},
        footnotes=[Footnote('own-note', blocks=[paragraph('Excluded footnote')])],
    )


def test_nested_cell_content_and_top_level_order_survive_two_json_cycles():
    source = own_model()
    before = document_to_json(source)
    text = document_to_text(source)
    expected_cell = 'Own cell x squared own inline image\nNested\ny plus one\ncell block image'
    assert text.tables[0].rows == [[expected_cell]]
    assert len(text.tables) == 1 and text.plain == 'Before\n'+expected_cell+'\nAfter'
    assert [block.type for block in text.blocks] == [BlockType.PARAGRAPH, BlockType.TABLE, BlockType.PARAGRAPH]
    original = text.to_dict()
    for _ in range(2):
        restored = document_from_json(document_to_json(text_to_document(text)))
        assert [type(block) for block in restored.sections[0].blocks] == [Paragraph, Table, Paragraph]
        assert restored.sections[0].blocks[1].rows[0].cells[0].blocks[0].plain_text == expected_cell
        text = document_to_text(restored)
        assert text.to_dict() == original
        assert not get_integration(restored).assessment_complete
    assert document_to_json(source) == before


def test_inventory_has_exact_source_paths_real_provenance_and_no_target_refs():
    source = own_model()
    before = document_to_json(source)
    text = document_to_text(source)
    records = text.diagnostics.preservation
    codes = {record.issue.code for record in records}
    assert {'legacy.image', 'legacy.formula', 'legacy.nested-table', 'legacy.table-merge', 'legacy.cell-blocks',
            'legacy.text-style', 'legacy.link', 'legacy.resource', 'legacy.style-definition', 'legacy.nonbody-content',
            'legacy.footnote', 'legacy.metadata', 'legacy.inline-boundaries'} <= codes
    link = next(record for record in records if record.issue.code == 'legacy.link')
    assert link.issue.location == 'sections[0].blocks[1].rows[0].cells[0].blocks[0].content[0].link'
    assert link.provenance.source_path == 'own.docx' and link.provenance.page == 3
    assert link.provenance.package_part == '/word/document.xml'
    assert link.provenance.events[-1].operation == 'legacy-text-projection'
    owner = next(record for record in records if record.issue.code == 'legacy.node-provenance')
    assert [event.operation for event in owner.provenance.events] == ['own.import', 'legacy-text-projection']
    for index, record in enumerate(records):
        assert record.state is PreservationState.LOST and record.node_id is None
        assert record.issue.reason == 'legacy-text-projection'
        assert record.issue.measurement['source_model_path'] == record.issue.location
        assert record.issue.measurement['legacy_warning_path'] == f'metadata.warnings[{index}]'
    link.provenance.events[-1].detail = 'Own edited report'
    assert document_to_json(source) == before


def test_repeated_objects_keep_separate_occurrences_and_equal_tables_are_not_merged():
    image = Image('own-image', alt_text='Own alt')
    table = Table(rows=[TableRow(cells=[TableCell(blocks=[paragraph('Same cell')])])])
    source = DocumentModel(sections=[Section(blocks=[image, table, image, table])],
                           resources={'own-image': Resource('own-image', ResourceKind.RASTER_IMAGE, 'image/png', data=b'own')})
    text = document_to_text(source)
    assert len(text.tables) == 2
    assert [block.meta['table_index'] for block in text.blocks if block.type is BlockType.TABLE] == [0, 1]
    assert [record.issue.location for record in text.diagnostics.preservation if record.issue.code == 'legacy.image'] == [
        'sections[0].blocks[0]', 'sections[0].blocks[2]',
    ]
    assert [type(block) for block in text_to_document(text).sections[0].blocks] == [Paragraph, Table, Paragraph, Table]


def test_section_page_and_unknown_properties_have_located_losses():
    source = DocumentModel(sections=[
        Section(blocks=[Paragraph(content=[TextRun('Own text')], alignment='right',
                                  properties={'unknown': {'own': [1]}})], page=PageSettings(width=Length(400))),
        Section(blocks=[paragraph('Other section')]),
    ])
    text = document_to_text(source)
    locations = {(record.issue.code, record.issue.location) for record in text.diagnostics.preservation}
    assert ('legacy.page-settings', 'sections[0].page') in locations
    assert ('legacy.paragraph-alignment', 'sections[0].blocks[0].alignment') in locations
    assert ('legacy.property', "sections[0].blocks[0].properties['unknown']") in locations
    assert sum(code == 'legacy.section-boundary' for code, _ in locations) == 2
    assert text.plain == 'Own text\nOther section'


def test_integration_extra_without_records_is_retained_as_an_independent_ledger():
    source = DocumentModel(sections=[Section(blocks=[paragraph('Own text')])])
    set_integration(source, IntegrationModel(extra={'own_unknown': {'items': [1]}}))
    text = document_to_text(source)
    assert text.diagnostics.extra['own_unknown'] == {'items': [1]}
    text.diagnostics.extra['own_unknown']['items'].append(2)
    assert get_integration(source).extra['own_unknown'] == {'items': [1]}


def test_package_graph_source_map_and_outer_extension_fields_have_explicit_losses():
    source = DocumentModel(sections=[Section(blocks=[paragraph('Own text')])], source_format='docx',
                           package=PackageGraph('docx', parts={
                               '/word/document.xml': PackagePart('/word/document.xml', 'application/xml', b'<own/>'),
                           }))
    set_integration(source, IntegrationModel(source_map=SourceMap(sources=(SourceFile('own', 'own.tex'),))))
    source.metadata[INTEGRATION_PROPERTY]['own_outer'] = {'items': [1]}
    original = document_to_json(source)
    text = document_to_text(source)
    locations = {(record.issue.code, record.issue.location) for record in text.diagnostics.preservation}
    assert ('legacy.package', 'package') in locations
    assert ('legacy.integration-structure', "metadata['opendoc.integration'].data.source_map") in locations
    assert ('legacy.integration-envelope-field', "metadata['opendoc.integration']['own_outer']") in locations
    assert document_to_json(source) == original


def test_unrecognized_integration_is_not_dropped_without_a_loss_record():
    source = DocumentModel(metadata={INTEGRATION_PROPERTY: {'own': [1]}})
    text = document_to_text(source)
    record = text.diagnostics.preservation[0]
    assert record.issue.code == 'legacy.integration-opaque'
    assert record.state is PreservationState.LOST


def test_resource_locator_and_history_are_retained_without_opening_external_content():
    origin = Provenance('html', 'own.html', object_id='own-external')
    origin.events.append(ProvenanceEvent('own.import'))
    source = DocumentModel(resources={'own': Resource('own', ResourceKind.RASTER_IMAGE, 'image/png',
                                                     source='https://example.invalid/own.png', provenance=origin)})
    record = document_to_text(source).diagnostics.preservation[0]
    assert record.issue.code == 'legacy.resource'
    assert record.provenance.source_path == 'own.html'
    assert record.provenance.object_id == 'own-external'
    assert [event.operation for event in record.provenance.events] == ['own.import', 'legacy-text-projection']


@pytest.mark.parametrize('index', [-1, True, '0', 1])
def test_invalid_table_links_are_rejected_without_changing_input(index):
    text = Text(blocks=[Block(BlockType.TABLE, meta={'rows': [['Own']], 'table_index': index})],
                tables=[LegacyTable([['Own']])])
    original = text.to_dict()
    with pytest.raises(ValueError, match='table_index'):
        text_to_document(text)
    assert text.to_dict() == original


@pytest.mark.parametrize('conflict', ['rows', 'page', 'repeat'])
def test_conflicting_or_repeated_table_links_do_not_choose_a_stale_copy(conflict):
    text = Text(blocks=[Block(BlockType.TABLE, meta={'rows': [['Own']], 'table_index': 0})],
                tables=[LegacyTable([['Own']])])
    if conflict == 'rows':
        text.tables[0].rows = [['Own edit']]
    elif conflict == 'page':
        text.tables[0].page = 2
    else:
        text.blocks.append(text.blocks[0])
    original = text.to_dict()
    with pytest.raises(ValueError, match='legacy table'):
        text_to_document(text)
    assert text.to_dict() == original


def test_native_table_block_without_parallel_table_is_structural_and_standalone_tables_remain_distinct():
    text = Text(blocks=[Block(BlockType.TABLE, meta={'rows': [['Own']]})], tables=[LegacyTable([['Own']])])
    restored = text_to_document(text)
    assert len(restored.sections[0].blocks) == 2
    assert all(isinstance(block, Table) for block in restored.sections[0].blocks)


@pytest.mark.parametrize('limits', [DocumentLimits(max_nodes=1), DocumentLimits(max_depth=2),
                                   DocumentLimits(max_embedded_bytes=1)])
def test_source_walk_applies_the_selected_budget_without_changing_source(limits):
    source = own_model()
    before = document_to_json(source)
    with pytest.raises(ArtifactLimitError):
        document_to_text(source, limits=limits)
    assert document_to_json(source) == before


def test_cyclic_table_is_rejected_before_flattening():
    table = Table(rows=[TableRow(cells=[TableCell()])])
    table.rows[0].cells[0].blocks.append(table)
    source = DocumentModel(sections=[Section(blocks=[table])])
    with pytest.raises(ValueError, match='cycl'):
        document_to_text(source)
    assert table.rows[0].cells[0].blocks[0] is table


@pytest.mark.parametrize('direction', ['to_text', 'to_model'])
def test_scope_is_inherited_and_restored_and_inactive_signal_keeps_complete_result(direction):
    source = own_model() if direction == 'to_text' else Text(tables=[LegacyTable([['Own']])])
    operation = document_to_text if direction == 'to_text' else text_to_document
    serialize = (lambda value: value.to_dict()) if direction == 'to_text' else document_to_json
    expected = serialize(operation(source))
    assert serialize(operation(source, cancelled=lambda: False)) == expected
    stop = Event()
    with cancellation_scope(stop.is_set, 'Own outer operation'):
        stop.set()
        with pytest.raises(OperationCancelledError):
            operation(source)
        stop.clear()
        checkpoint()
        assert serialize(operation(source)) == expected
    checkpoint()
    with pytest.raises(ValueError, match='callable'):
        operation(source, cancelled=True)


def test_cancel_inside_inventory_stops_before_another_record_and_preserves_source(monkeypatch):
    source = own_model()
    before = document_to_json(source)
    stop, calls = Event(), []
    original = Provenance.transformed

    def transformed(self, *args, **kwargs):
        assert not calls, 'A second loss was inventoried after cancellation'
        calls.append(True)
        stop.set()
        return original(self, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Provenance, 'transformed', transformed)
        with pytest.raises(OperationCancelledError):
            document_to_text(source, cancelled=stop.is_set)
    assert calls == [True] and document_to_json(source) == before
    assert document_to_text(source).plain.startswith('Before')


def test_html_legacy_reader_forwards_selected_limits_and_cancel_without_changing_source(tmp_path):
    pytest.importorskip('bs4')
    pytest.importorskip('tinycss2')
    from opendoc_formats.readers.html_text import read_html

    source = tmp_path/'own.html'
    source.write_text('<p><b>Own text</b></p>', encoding='utf-8')
    original = source.read_bytes()
    with pytest.raises(ArtifactLimitError):
        read_html(source, limits=DocumentLimits(max_nodes=1))
    with pytest.raises(OperationCancelledError):
        read_html(source, cancelled=lambda: True)
    assert read_html(source).to_dict() == read_html(source, cancelled=lambda: False).to_dict()
    assert source.read_bytes() == original
