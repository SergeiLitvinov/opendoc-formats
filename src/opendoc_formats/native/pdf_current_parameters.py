"""Revision-specific scalar witnesses for previously decoded containers."""

from __future__ import annotations

from typing import Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_source_integers import FilterParameters, SourceIntegers
from opendoc_formats.native.pdf_syntax import Reference
from opendoc_formats.support.cancellation import checkpoint

Key = tuple[int, int, int]
ParameterValue = int | str | FilterParameters
Parameters = dict[str, tuple[Reference, ParameterValue]]


def assess_context(parameters: Parameters, integers: SourceIntegers, context: int, *,
                   item_limit: int, byte_limit: int, scope: str) -> dict[str, Any]:
    location = f'pdf:{scope}-parameters:xref={context}: '
    checkpoint()
    if integers.items >= item_limit:
        raise ResourceLimitError(location+'max_items exceeded by parameter assessment')
    integers.items += 1
    values: dict[str, ParameterValue] = {}
    row: dict[str, Any] = {'context_xref': context, 'status': 'matched-decoded-parameters',
                           'decoded_parameter_values': {}, f'{scope}_parameter_values': values,
                           'source_integer_observations': {}}
    for field, (reference, decoded) in parameters.items():
        checkpoint()
        row['decoded_parameter_values'][field] = decoded
        try:
            read = (integers.read_parameters if isinstance(decoded, (dict, list))
                    else integers.read_name if isinstance(decoded, str) else integers.read)
            value, observations = read(reference, {context}, item_limit=item_limit,
                                       byte_limit=byte_limit, location=location+field+': ', explicit_primary=True)
        except (InvalidDocumentError, UnsupportedDocumentError) as error:
            reason = 'invalid' if isinstance(error, InvalidDocumentError) else 'unsupported'
            row.update(status=f'{reason}-{scope}-parameter', parameter=field, error=str(error),
                       parameter_reference={'object': reference.object, 'generation': reference.generation})
            break
        values[field] = value
        row['source_integer_observations'][field] = observations
        if value != decoded:
            row['status'] = 'changed-from-decoded-parameters'
    return row


def assess(parameters: dict[Key, Parameters], integers: SourceIntegers,
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
    return {key: assess_context(parameters[key], integers, current, item_limit=item_limit,
                                byte_limit=byte_limit, scope='current') for key in sorted(selected)}
