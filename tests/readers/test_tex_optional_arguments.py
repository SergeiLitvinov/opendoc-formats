"""LaTeX optional arguments stop at the first unbraced ], with exact opaque source scope."""

from threading import Event

import pytest
from opendoc_model import document_from_json, document_to_json, get_integration

from opendoc_formats.errors import InvalidDocumentError, OperationCancelledError, ResourceLimitError
from opendoc_formats.readers.tex_model import read_tex_model


@pytest.mark.parametrize('argument', [r'[Plain]', r'[]', r'[{]}]', r'[[Literal]',
                                     r'[Short {]} and \textbf{bold} $x^2$]',
                                     r'[{\textbf{label [and]}}]', r'[Short \{ literal \} ending]',
                                     '[Short % comment with ]\r\n title]'])
def test_heading_optional_scope_and_following_body_survive_exact_source_json(tmp_path, argument):
    path = tmp_path / 'own.tex'
    text = '\\begin{document}\r\n\\section' + argument + '{Visible heading}Body text.\\end{document}'
    source = b'\xef\xbb\xbf' + text.encode('utf-8')
    path.write_bytes(source)
    document = read_tex_model(path)
    for _ in range(2):
        document = document_from_json(document_to_json(document))
        assert [block.plain_text for block in document.sections[0].blocks] == ['Visible heading', 'Body text.']
        record, = [value for value in get_integration(document).preservation if value.issue.reason == 'heading-short-title']
        span = record.extra['source_span']
        assert text[span['start']:span['end']] == argument
        assert (span['line'], span['column']) == (2, 9)
        assert document.resources[record.extra['resource_id']].data == source
        assert record.state.value == 'opaque' and record.provenance.object_id.startswith('chars:')
    assert path.read_bytes() == source


@pytest.mark.parametrize('argument', [r'[Unclosed', r'[{Unclosed]', r'[Unexpected }]'])
def test_unclosed_or_unbalanced_optional_argument_refuses_without_repair(tmp_path, argument):
    path = tmp_path / 'own.tex'
    source = ('\\begin{document}\\section' + argument + '{Visible}\\end{document}').encode()
    path.write_bytes(source)
    with pytest.raises(InvalidDocumentError):
        read_tex_model(path)
    assert path.read_bytes() == source


def test_optional_brace_depth_is_bounded_even_when_title_stays_opaque(tmp_path):
    path = tmp_path / 'own.tex'
    source = ('\\begin{document}\\section[' + '{' * 65 + 'Own' + '}' * 65 + ']{Visible}\\end{document}').encode()
    path.write_bytes(source)
    with pytest.raises(ResourceLimitError, match='depth limit'):
        read_tex_model(path)
    assert path.read_bytes() == source


def test_cancellation_inside_optional_scan_is_atomic_and_next_import_recovers(tmp_path, monkeypatch):
    import opendoc_formats.readers.tex_model as implementation
    path = tmp_path / 'own.tex'
    source = ('\\begin{document}\\section[' + 'Own {label} ' * 1000 + ']{Visible}\\end{document}').encode()
    path.write_bytes(source)
    armed = Event()
    calls = 0
    original = implementation._Parser.group
    def active(self, *args, **kwargs):
        if args == ('[', ']'):
            armed.set()
        try:
            return original(self, *args, **kwargs)
        finally:
            armed.clear()
    def cancel():
        nonlocal calls
        if armed.is_set():
            calls += 1
        return calls >= 5

    with monkeypatch.context() as context:
        context.setattr(implementation._Parser, 'group', active)
        with pytest.raises(OperationCancelledError):
            read_tex_model(path, cancelled=cancel)
    assert calls == 5 and path.read_bytes() == source
    assert read_tex_model(path).sections[0].blocks[0].plain_text == 'Visible'
