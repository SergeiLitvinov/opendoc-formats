"""Dissect ZIP/OOXML/EPUB, PDF, CFBF or sfnt into an inventory and captured native payloads."""

from __future__ import annotations

import argparse
import json
from dataclasses import fields
from pathlib import Path

from opendoc_formats.anatomy import AnatomyLimits, BinarySnapshot, compare_snapshots, inspect_binary


def save_dissection(snapshot: BinarySnapshot, output: Path, comparison: dict | None = None) -> None:
    """Create a new flat directory, never deriving disk paths from archive member names."""
    output.mkdir(parents=True, exist_ok=False)
    created: list[Path] = []
    complete = False

    def write(name: str, payload: bytes) -> None:
        path = output/name
        with path.open('xb') as stream:
            created.append(path)
            stream.write(payload)

    try:
        manifest = snapshot.to_dict()
        for index, item in enumerate(snapshot.items):
            if item.payload is not None:
                name = f'part-{index:06d}'+('.xml' if item.xml_nodes else '.bin')
                write(name, item.payload)
                manifest['items'][index]['payload_file'] = name
            dictionary = dict(item.details).get('dictionary')
            if dictionary is not None:
                name = f'part-{index:06d}.pdf-object.txt'
                write(name, dictionary.encode('utf-8'))
                manifest['items'][index]['dictionary_file'] = name
        if comparison is not None:
            manifest['comparison'] = comparison
        write('inventory.json', (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode('utf-8'))
        complete = True
    finally:
        if not complete:
            for path in reversed(created):
                path.unlink(missing_ok=True)
            output.rmdir()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New directory; existing directories are never replaced')
    parser.add_argument('--compare', type=Path, help='Optional result file, compared by literal native addresses')
    parser.add_argument('--container', choices=('zip', 'pdf', 'cfbf', 'sfnt'))
    parser.add_argument('--opaque-xml', action='store_true', help='Keep XML bytes without parsing DTDs or other markup')
    parser.add_argument('--no-payloads', action='store_true', help='Write only the inventory and PDF dictionaries')
    parser.add_argument('--sfnt-checksums', action='store_true', help='Audit standalone sfnt checksums without repairing bytes')
    parser.add_argument('--sfnt-face-index', type=int, help='Select a zero-based TTC/OTC face; original collection is retained')
    parser.add_argument('--sfnt-structure', action='store_true',
                        help='Audit directory order, search fields, padding and overlaps')
    parser.add_argument('--pdf-source', action='store_true', help='Inspect physical xref/trailer links without a PDF backend')
    defaults = AnatomyLimits()
    for definition in fields(defaults):
        parser.add_argument('--'+definition.name.replace('_', '-'), type=int, default=getattr(defaults, definition.name))
    args = parser.parse_args()
    limits = AnatomyLimits(**{definition.name: getattr(args, definition.name) for definition in fields(defaults)})
    snapshot = inspect_binary(args.source, container=args.container, parse_xml=not args.opaque_xml,
                              capture=not args.no_payloads, sfnt_checksums=args.sfnt_checksums,
                              sfnt_face_index=args.sfnt_face_index, sfnt_structure=args.sfnt_structure,
                              pdf_source=args.pdf_source, limits=limits)
    comparison = None
    if args.compare is not None:
        result = inspect_binary(args.compare, container=args.container, parse_xml=not args.opaque_xml,
                                sfnt_checksums=args.sfnt_checksums, sfnt_face_index=args.sfnt_face_index,
                                sfnt_structure=args.sfnt_structure, pdf_source=args.pdf_source, limits=limits)
        comparison = compare_snapshots(snapshot, result)
    save_dissection(snapshot, args.output, comparison)
    print(f'Dissected {snapshot.container}: {len(snapshot.items)} items; {args.output / "inventory.json"}')


if __name__ == '__main__':
    main()
