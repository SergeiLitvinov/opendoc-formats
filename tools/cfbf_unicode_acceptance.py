"""Compare every UTF-16 code unit with an independently supplied UnicodeData release."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path

from opendoc_formats.native.cfbf_names import _uppercase_unit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unicode-data', required=True, type=Path)
    parser.add_argument('--unicode-version', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    assert args.unicode_version == unicodedata.unidata_version, 'Oracle and runtime Unicode versions must match'
    source = args.unicode_data.read_bytes()
    expected = {}
    for line in source.decode('utf-8').splitlines():
        fields = line.split(';')
        if fields[12]:
            expected[int(fields[0], 16)] = int(fields[12], 16)
    observed = bytearray()
    for unit in range(65536):
        value = _uppercase_unit(unit)
        assert value == expected.get(unit, unit), f'Simple uppercase mismatch U+{unit:04X}'
        observed.extend(value.to_bytes(2, 'little'))
    args.output.write_text(json.dumps({
        'scope': 'All 65536 UTF-16 units; simple uppercase only, not complete CFBF tree acceptance',
        'python': sys.version.split()[0], 'unicode_version': unicodedata.unidata_version,
        'unicode_data_url': f'https://www.unicode.org/Public/{args.unicode_version}/ucd/UnicodeData.txt',
        'unicode_data_sha256': hashlib.sha256(source).hexdigest(),
        'verified_units': 65536, 'mismatches': 0, 'mapping_sha256': hashlib.sha256(observed).hexdigest(),
        'consumer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }, indent=2)+'\n', encoding='utf-8')
    print('All 65536 UTF-16 units match UnicodeData simple uppercase mappings')


if __name__ == '__main__':
    main()
