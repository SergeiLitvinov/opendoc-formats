"""Physical PDF filter pipelines with shared work quotas and explicit stage coordinates."""

from __future__ import annotations

import hashlib
from typing import Any

from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.pdf_byte_filters import BYTE_DECODERS
from opendoc_formats.native.pdf_flate import inflate
from opendoc_formats.native.pdf_predictors import layout, shape, undo_png, undo_tiff
from opendoc_formats.native.pdf_syntax import Name, SyntaxBudget
from opendoc_formats.support.cancellation import checkpoint


def _plan(encoding: Any, parameters: Any, location: str, budget: SyntaxBudget) -> list[tuple[str, dict[str, Any]]]:
    if encoding is None or encoding == []:
        if parameters not in (None, {}, []):
            if (not isinstance(parameters, dict) or set(parameters)-{'Predictor'}
                    or type(parameters.get('Predictor', 1)) is not int or parameters.get('Predictor', 1) != 1):
                raise UnsupportedDocumentError(location+'raw stream parameters outside supported profile')
        return []
    names = encoding if isinstance(encoding, list) else [encoding]
    if isinstance(parameters, list):
        if len(parameters) != len(names):
            raise InvalidDocumentError(location+'DecodeParms array length disagrees with Filter')
    elif parameters is not None and (len(names) != 1 or not isinstance(parameters, dict)):
        raise UnsupportedDocumentError(location+'filter parameters require aligned direct dictionaries/null')
    result = []
    for index, name in enumerate(names):
        checkpoint()
        budget.tokens += 1
        if budget.tokens > budget.maximum:
            raise ResourceLimitError(location+'max_pdf_tokens exceeded by filter stages')
        if not isinstance(name, Name) or name.value not in ('FlateDecode', *BYTE_DECODERS):
            raise UnsupportedDocumentError(location+f'filter[{index}] outside Flate/RunLength/ASCII profile')
        options = parameters[index] if isinstance(parameters, list) else parameters
        if options is None:
            options = {}
        if not isinstance(options, dict):
            raise UnsupportedDocumentError(location+f'filter[{index}] requires direct dictionary/null parameters')
        if name.value in BYTE_DECODERS:
            if options:
                raise UnsupportedDocumentError(location+name.value+' has no supported decoding parameters')
        else:
            if set(options)-{'Predictor', 'Colors', 'BitsPerComponent', 'Columns', 'EarlyChange'}:
                raise UnsupportedDocumentError(location+'unknown Flate decoding parameter')
            shape(options, location+f'filter[{index}]: ')
        result.append((name.value, options))
    return result


def decode(raw: memoryview, encoding: Any, parameters: Any, *, source_start: int, part_limit: int,
           byte_limit: int, location: str, budget: SyntaxBudget,
           expected: int | None = None) -> tuple[bytearray, dict[str, Any]]:
    plan = _plan(encoding, parameters, location, budget)
    if not plan:
        if len(raw) > part_limit or len(raw) > byte_limit:
            raise ResourceLimitError(location+'raw decoded stream exceeds byte budget')
        if expected is not None and len(raw) != expected:
            raise InvalidDocumentError(location+'raw stream length disagrees with declared decoded size')
        return bytearray(raw), {'filter': None, 'filter_chain': [], 'decode_stages': [],
                                'decode_work_bytes': len(raw), 'predictor': 1}
    final_work = expected
    if expected is not None and plan[-1][0] == 'FlateDecode':
        final_work = layout(plan[-1][1], expected, location)[3]
    if final_work is not None and (final_work > part_limit or final_work > byte_limit):
        raise ResourceLimitError(location+'decoded stream/PNG row tags exceed max_part_bytes/max_total_bytes')
    current = raw
    work = 0
    stages: list[dict[str, Any]] = []
    first_eod: dict[str, Any] = {}
    output = bytearray()
    for index, (name, options) in enumerate(plan):
        checkpoint()
        here = location+f'filter[{index}]={name}: '
        last = index == len(plan)-1
        exact = expected if last else None
        reserved = (final_work or 0) if not last else 0
        maximum = min(part_limit, byte_limit-work-reserved)
        if maximum < 0:
            raise ResourceLimitError(here+'no remaining intermediate decoded byte budget')
        predictor, row_bytes, stride = shape(options, here) if name == 'FlateDecode' else (1, 1, 1)
        before_prediction = exact
        if exact is not None and name == 'FlateDecode':
            before_prediction = layout(options, exact, here)[3]
        if before_prediction is not None and before_prediction > maximum:
            raise ResourceLimitError(here+'decoded stream/PNG row tags exceed byte budget')
        consumed = len(current)
        if name == 'FlateDecode':
            output = inflate(current, maximum, here, expected=before_prediction)
        else:
            output, consumed = BYTE_DECODERS[name](current, maximum, here, expected=exact)
            if index == 0:
                first_eod = {'encoded_data_end': source_start+consumed, 'trailing_encoded_bytes': len(current)-consumed}
        stage_work = len(output)
        work += stage_work
        if predictor == 2:
            undo_tiff(output, options.get('Colors', 1), options.get('BitsPerComponent', 8), options.get('Columns', 1), here)
        elif predictor >= 10:
            if len(output) % (row_bytes+1):
                raise InvalidDocumentError(here+'incomplete PNG predictor row')
            undo_png(output, row_bytes, stride, here)
        if exact is not None and len(output) != exact:
            raise InvalidDocumentError(here+'decoded length disagrees with declared size')
        checkpoint()
        stages.append({'stage': index, 'filter': name, 'predictor': predictor, 'input_bytes': len(current),
                       'input_space': 'source' if index == 0 else f'stage[{index-1}]-output',
                       'input_data_end': source_start+consumed if index == 0 else consumed,
                       'trailing_input_bytes': len(current)-consumed, 'decoded_bytes': len(output),
                       'decode_work_bytes': stage_work, 'decoded_sha256': hashlib.sha256(output).hexdigest()})
        current = memoryview(output)
    names = [name for name, _ in plan]
    return output, {'filter': names[0] if len(names) == 1 else names, 'filter_chain': names, 'decode_stages': stages,
                    'decode_work_bytes': work, 'predictor': stages[-1]['predictor'], **first_eod}
