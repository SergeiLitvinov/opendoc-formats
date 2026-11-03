"""Current scalar witnesses for previously decoded containers, without cross-context body reuse."""

from __future__ import annotations

from typing import Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_source_integers import SourceIntegers
from opendoc_formats.native.pdf_syntax import Reference
from opendoc_formats.support.cancellation import checkpoint

Key = tuple[int, int, int]


def assess(parameters: dict[Key, dict[str, tuple[Reference, int]]], integers: SourceIntegers,
           *, item_limit: int, byte_limit: int) -> dict[Key, dict[str, Any]]:
    if not parameters:
        return {}
    current = integers.sections[0]['offset']
    location = f'pdf:current-parameters:xref={current}: '
    _, index = integers.selection(current, item_limit=item_limit, location=location, explicit_primary=True)
    selected = set()
    for entry in index.values():
        checkpoint()
        integers.budget.tokens += 1
        if integers.budget.tokens > integers.budget.maximum:
            raise ResourceLimitError(location+'max_pdf_tokens exceeded by container selection')
        if entry['state'] != 'compressed':
            continue
        container = index.get(entry['object_stream'])
        if container is not None and container['state'] == 'uncompressed':
            key = entry['object_stream'], container['generation'], container['offset']
            if key in parameters:
                selected.add(key)
    result = {}
    for key in sorted(selected):
        checkpoint()
        if integers.items >= item_limit:
            raise ResourceLimitError(location+'max_items exceeded by current parameter assessment')
        integers.items += 1
        row: dict[str, Any] = {'context_xref': current, 'status': 'matched-decoded-parameters',
                               'decoded_parameter_values': {}, 'current_parameter_values': {},
                               'source_integer_observations': {}}
        result[key] = row
        for field, (reference, decoded) in parameters[key].items():
            checkpoint()
            row['decoded_parameter_values'][field] = decoded
            try:
                value, observations = integers.read(reference, {current}, item_limit=item_limit,
                                                     byte_limit=byte_limit, location=location+field+': ',
                                                     explicit_primary=True)
            except (InvalidDocumentError, UnsupportedDocumentError) as error:
                row.update(status='invalid-current-parameter' if isinstance(error, InvalidDocumentError)
                           else 'unsupported-current-parameter', parameter=field, error=str(error),
                           parameter_reference={'object': reference.object, 'generation': reference.generation})
                break
            row['current_parameter_values'][field] = value
            row['source_integer_observations'][field] = observations
            if value != decoded:
                row['status'] = 'changed-from-decoded-parameters'
    return result
