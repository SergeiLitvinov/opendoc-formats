"""Reproduce bounded Extends declarations on independently authored PDF bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from importlib.metadata import version
from io import BytesIO
from pathlib import Path

from tests.native.test_pdf_current_extends import revised
from tests.native.test_pdf_extends import collection, inspect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--current', action='store_true', help='Record paired historical/current projections after edits')
    args = parser.parse_args()
    cases = [('chain', (5, 6, None), {}), ('hybrid', (5, 6, None), {'hybrid': True}),
             ('self-cycle', (4,), {}), ('two-cycle', (5, 4), {}), ('missing', (99,), {})]
    cases += [(state, (5, None), {'target_state': state})
              for state in ('free', 'ordinary', 'compressed', 'generation')]
    sources = [(name, collection(targets, **options)[0]) for name, targets, options in cases]
    if args.current:
        sources = [(state, revised(state=state)[0]) for state in (
            'parent', 'free', 'unknown', 'compressed', 'ordinary', 'cycle', 'root-free', 'root-ordinary', 'no-users')]
        sources.append(('generation', revised(generation=1)[0]))
    rows = []
    for name, source in sources:
        snapshot = inspect(source, capture=True)
        details = dict(snapshot.details)
        before = hashlib.sha256(source).hexdigest()
        for item in snapshot.items:
            if item.kind == 'pdf-object-stream':
                value = dict(item.details)
                assert item.payload == source[value['offset']:value['end']]
        row = {'case': name, 'source_sha256': before, 'source_bytes': len(source),
               'declared_links': details['object_stream_extends_links'],
               'dag_valid': details['object_stream_extends_dag_valid'],
               'decoded_containers': details['decoded_object_streams'],
               'work_items': details['object_stream_extends_work_items']}
        row['current_projection'] = {key: value for key, value in details.items() if key.startswith('object_stream_current_')}
        if name in ('chain', 'parent'):
            import pypdf

            reader = pypdf.PdfReader(BytesIO(source), strict=True)
            assert len(reader.pages) == 1 and reader.metadata.title == 'Own 0'
            row['independent_reader'] = {'name': 'pypdf', 'version': version('pypdf'), 'strict': True,
                                         'pages': len(reader.pages), 'title': reader.metadata.title}
        assert hashlib.sha256(source).hexdigest() == before
        assert not details['assessment_complete'] and not details['object_stream_reference_links_assessed']
        rows.append(row)
    args.output.write_text(json.dumps({
        'profile': ('current-and-historical-object-stream-collections' if args.current else
                    'context-selected-object-stream-collection-declarations'), 'cases': rows,
        'test_fixture_sha256': hashlib.sha256(Path('tests/native/test_pdf_extends.py').read_bytes()).hexdigest(),
        'consumer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'current_fixture_sha256': hashlib.sha256(Path('tests/native/test_pdf_current_extends.py').read_bytes()).hexdigest(),
        'limitations': ['No member inheritance, object ownership or active-body resolution',
                        'Current collection declarations are separate from historical links; parameter contexts must agree',
                        'Independent reader checks valid chain/replacement only; '
                        'damaged and hybrid use literal source assertions'],
    }, indent=2)+'\n', encoding='utf-8')
    print(f'{len(rows)} source declaration cases recorded')


if __name__ == '__main__':
    main()
