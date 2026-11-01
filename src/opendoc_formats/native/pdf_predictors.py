"""PDF PNG predictor rows, decoded in place without image/PDF dependencies."""

from __future__ import annotations

from typing import Any

from opendoc_formats.errors import InvalidDocumentError, UnsupportedDocumentError
from opendoc_formats.support.cancellation import checkpoint


def layout(parameters: dict[str, Any], expected: int, location: str) -> tuple[int, int, int, int]:
    """Return Predictor, row bytes, byte stride and size before undoing prediction."""
    predictor = parameters.get('Predictor', 1)
    if type(predictor) is not int or predictor not in (1, 10, 11, 12, 13, 14, 15):
        raise UnsupportedDocumentError(location+'xref predictor outside no-prediction/PNG profile')
    if predictor == 1:
        return 1, expected, 1, expected
    colors, bits, columns = (parameters.get(key, default)
                            for key, default in (('Colors', 1), ('BitsPerComponent', 8), ('Columns', 1)))
    if any(type(value) is not int or value <= 0 for value in (colors, bits, columns)) or bits not in (1, 2, 4, 8, 16):
        raise InvalidDocumentError(location+'invalid PNG Colors/BitsPerComponent/Columns')
    row_bytes = (colors*bits*columns+7)//8
    stride = (colors*bits+7)//8
    if expected % row_bytes:
        raise InvalidDocumentError(location+'PNG rows do not divide xref W/Index byte length')
    return predictor, row_bytes, stride, expected+expected//row_bytes


def undo_png(data: bytearray, row_bytes: int, stride: int, location: str) -> None:
    """Use decoded left/up neighbours; compact tags away without a second output buffer."""
    rows = len(data)//(row_bytes+1)
    for row in range(rows):
        checkpoint()
        source, target = row*(row_bytes+1), row*row_bytes
        algorithm = data[source]
        if algorithm > 4:
            raise InvalidDocumentError(location+'invalid PNG predictor row tag')
        for column in range(row_bytes):
            if column % 4096 == 0:
                checkpoint()
            position = target+column
            left = data[position-stride] if column >= stride else 0
            up = data[position-row_bytes] if row else 0
            upper_left = data[position-row_bytes-stride] if row and column >= stride else 0
            if algorithm == 0:
                predicted = 0
            elif algorithm == 1:
                predicted = left
            elif algorithm == 2:
                predicted = up
            elif algorithm == 3:
                predicted = (left+up)//2
            else:
                estimate = left+up-upper_left
                dl, du, dul = abs(estimate-left), abs(estimate-up), abs(estimate-upper_left)
                predicted = left if dl <= du and dl <= dul else up if du <= dul else upper_left
            data[position] = (data[source+1+column]+predicted) & 255
    del data[rows*row_bytes:]
