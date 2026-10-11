"""Located SDK quota failures, preserving unknown error text without guessed fields."""

from __future__ import annotations

import re

from opendoc_model import ArtifactLimitError, DiagnosticIssue, DocumentLimits, IssueSeverity


def limit_diagnostic(error: ArtifactLimitError, limits: DocumentLimits, source: str, code: str) -> DiagnosticIssue:
    message = str(error)
    measurement: dict[str, object] = {'limits': {
        'max_bytes': limits.max_bytes, 'max_depth': limits.max_depth,
        'max_nodes': limits.max_nodes, 'max_embedded_bytes': limits.max_embedded_bytes,
    }}
    location = source
    match = re.fullmatch(r'([^\r\n]+): ([\w ]+) quota exceeded \((\d+)\)', message)
    if match:
        location += '#' + match[1]
        measurement.update({'quota': match[2], 'maximum': int(match[3])})
    return DiagnosticIssue(code, IssueSeverity.ERROR, message, location, measurement, 'document-limit')
