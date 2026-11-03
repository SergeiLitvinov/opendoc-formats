"""Dissect nested ZIP/CFBF/Ole10Native and PNG leaves with shared budgets; objects remain inert."""

from __future__ import annotations

import argparse
import json
from dataclasses import fields
from pathlib import Path

from opendoc_formats.anatomy import AnatomyLimits
from opendoc_formats.anatomy_tree import ContainerTree, compare_container_trees, inspect_container_tree
from opendoc_formats.support.cancellation import checkpoint
from tools.document_anatomy import save_dissection


def save_tree(tree: ContainerTree, output: Path, comparison: dict | None = None) -> None:
    """Write generated names only, rolling back this call's files on publication failure."""
    output.mkdir(parents=True, exist_ok=False)
    created_files: list[Path] = []
    created_dirs: list[Path] = []
    try:
        manifest = tree.to_dict()
        records = []
        for index, occurrence in enumerate(tree.occurrences):
            checkpoint()
            directory = output / f'container-{index:06d}'
            save_dissection(occurrence.snapshot, directory)
            created_dirs.append(directory)
            created_files.extend(directory.iterdir())
            records.append({'location': list(occurrence.location),
                            'inventory_file': directory.name + '/inventory.json'})
        manifest['containers'] = records
        if comparison is not None:
            manifest['comparison'] = comparison
        checkpoint()
        path = output / 'inventory.json'
        with path.open('x', encoding='utf-8') as stream:
            created_files.append(path)
            stream.write(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    except BaseException:
        for path in reversed(created_files):
            path.unlink(missing_ok=True)
        for directory in reversed(created_dirs):
            directory.rmdir()
        output.rmdir()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New directory; never replace existing data')
    parser.add_argument('--compare', type=Path, help='Compare literal container/item addresses, not semantics')
    parser.add_argument('--max-depth', type=int, default=8, help='Container nesting; root is zero, maximum 64')
    parser.add_argument('--max-containers', type=int, default=128)
    parser.add_argument('--no-payloads', action='store_true')
    defaults = AnatomyLimits()
    for definition in fields(defaults):
        parser.add_argument('--' + definition.name.replace('_', '-'), type=int, default=getattr(defaults, definition.name))
    args = parser.parse_args()
    limits = AnatomyLimits(**{definition.name: getattr(args, definition.name) for definition in fields(defaults)})
    tree = inspect_container_tree(args.source, limits=limits, capture=not args.no_payloads,
                                  max_depth=args.max_depth, max_containers=args.max_containers)
    comparison = None
    if args.compare:
        other = inspect_container_tree(args.compare, limits=limits, max_depth=args.max_depth,
                                       max_containers=args.max_containers)
        comparison = compare_container_trees(tree, other)
    save_tree(tree, args.output, comparison)
    print(f'Dissected {len(tree.occurrences)} container occurrences; {args.output / "inventory.json"}')


if __name__ == '__main__':
    main()
