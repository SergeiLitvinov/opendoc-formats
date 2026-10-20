"""List boundaries that cannot be flattened into independent numbered paragraphs."""

import pytest
from opendoc_model import document_from_json, document_to_json, get_integration

from opendoc_formats import read_document


@pytest.mark.parametrize(('body', 'reason', 'texts'), [
    (r'\begin{itemize}\item[Own label] Text\end{itemize}', 'list-item-label', ['Text']),
    (r'\begin{itemize}Before\item Text\end{itemize}', 'list-missing-item', ['Before', 'Text']),
    (r'\item Outside', 'list-orphan-item', ['Outside']),
])
def test_list_loss_has_a_located_record_and_original_bytes_after_two_json_cycles(tmp_path, body, reason, texts):
    source = tmp_path / 'list.tex'
    raw = ('\\begin{document}'+body+'\\end{document}').encode('utf-8')
    source.write_bytes(raw)
    document = read_document(source).document
    for _ in range(2):
        document = document_from_json(document_to_json(document))
        assert [p.plain_text for p in document.sections[0].blocks] == texts
        assert document.resources['latex-original-source'].data == raw
        records = [r for r in get_integration(document).preservation if r.issue.reason == reason]
        assert len(records) == 1
        record = records[0]
        span = record.extra['source_span']
        assert 0 <= span['start'] < span['end'] <= len(raw.decode('utf-8'))
        assert record.issue.location == f"{source}:{span['line']}:{span['column']}"
        assert record.extra['resource_id'] == 'latex-original-source'


def test_single_paragraph_items_do_not_receive_false_boundary_diagnostics(tmp_path):
    source = tmp_path / 'own.tex'
    source.write_text(r'\begin{document}\begin{itemize}\item First\item Parent'
                      r'\begin{enumerate}\item Child\end{enumerate}\item Last\end{itemize}\end{document}', encoding='utf-8')
    document = read_document(source).document
    assert [p.plain_text for p in document.sections[0].blocks] == ['First', 'Parent', 'Child', 'Last']
    assert not [r for r in get_integration(document).preservation if (r.issue.reason or '').startswith('list-')]
