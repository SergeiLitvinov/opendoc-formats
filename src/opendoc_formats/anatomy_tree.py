"""Bounded physical ZIP/CFBF/Ole10Native nesting and PNG leaves; no object activation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from opendoc_formats.anatomy import AnatomyLimits, BinarySnapshot, compare_snapshots, inspect_binary
from opendoc_formats.errors import InvalidDocumentError, ResourceLimitError, UnsupportedDocumentError
from opendoc_formats.native.cfbf import SIGNATURE
from opendoc_formats.native.common import Source, positive_int, read_source
from opendoc_formats.native.png import SIGNATURE as PNG_SIGNATURE
from opendoc_formats.support.cancellation import cancellation_scope, checkpoint


@dataclass(frozen=True)
class ContainerOccurrence:
    """A container reached through exact native item addresses, never disk paths."""

    location: tuple[str, ...]
    snapshot: BinarySnapshot


@dataclass(frozen=True)
class ContainerTree:
    occurrences: tuple[ContainerOccurrence, ...]
    charged_items: int
    charged_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            'format': 'opendoc-formats.container-tree', 'version': 1,
            'assessment_complete': False,
            'selection_policy': 'initial-signature or named CFBF Ole10Native envelope; complete streams only; XML opaque',
            'charged_items': self.charged_items, 'charged_bytes': self.charged_bytes,
            'containers': [{'location': list(entry.location), 'inventory': entry.snapshot.to_dict()}
                           for entry in self.occurrences],
        }


def _profile(data: bytes) -> str | None:
    if data.startswith(SIGNATURE):
        return 'cfbf'
    if data.startswith(PNG_SIGNATURE):
        return 'png'
    return 'zip' if data.startswith((b'PK\x03\x04', b'PK\x05\x06')) else None


def inspect_container_tree(
    source: Source, *, limits: AnatomyLimits = AnatomyLimits(), max_depth: int = 8,
    max_containers: int = 128, capture: bool = False, cancelled: Callable[[], bool] | None = None,
) -> ContainerTree:
    """Inspect complete ZIP/CFBF streams, named Ole10Native envelopes and PNG leaves.

    Root depth is zero. Anatomy max_items/max_total_bytes are shared across all
    occurrences. Each inventory charges at least one item (or the CFBF directory
    slot count, if larger) and one byte; original
    container bytes are charged in addition to inventory payload bytes. Unknown
    streams stay opaque. A recognized but invalid child aborts the whole operation.
    XML is opaque in this physical profile, including package control XML.
    """
    if not isinstance(limits, AnatomyLimits) or type(capture) is not bool:
        raise TypeError('Expected AnatomyLimits and boolean capture')
    positive_int(max_depth, 'max_depth', zero=True)
    positive_int(max_containers, 'max_containers')
    if max_depth > 64:
        raise ValueError('max_depth must be at most 64')
    occurrences: list[ContainerOccurrence] = []
    charged_items = charged_bytes = 0

    def visit(data: bytes, location: tuple[str, ...], profile: str | None = None) -> None:
        nonlocal charged_items, charged_bytes
        checkpoint()
        address = repr(location)
        if len(location) > max_depth:
            raise ResourceLimitError(f'{address}: container max_depth exceeded')
        if len(occurrences) >= max_containers:
            raise ResourceLimitError(f'{address}: max_containers exceeded')
        profile = profile or _profile(data)
        if profile is None:
            raise UnsupportedDocumentError(f'{address}: expected initial ZIP or CFBF signature, or PNG signature')
        remaining_items = limits.max_items - charged_items
        remaining_bytes = limits.max_total_bytes - charged_bytes - len(data)
        if remaining_items < 1 or remaining_bytes < 1:
            raise ResourceLimitError(f'{address}: shared max_items/max_total_bytes exceeded')
        selected = replace(limits, max_items=remaining_items, max_total_bytes=remaining_bytes,
                           max_part_bytes=min(limits.max_part_bytes, remaining_bytes))
        # This API selects the initial signature explicitly. A ZIP stream inside
        # valid CFBF can otherwise look like a self-extracting ZIP to auto detection.
        try:
            snapshot = inspect_binary(data, container=profile, limits=selected, parse_xml=False, capture=True)
        except ResourceLimitError as error:
            message = (f'{address}: remaining max_items={remaining_items}, max_total_bytes={remaining_bytes}, '
                       f'max_part_bytes={selected.max_part_bytes}: {error}')
            raise ResourceLimitError(message) from error
        except (InvalidDocumentError, UnsupportedDocumentError) as error:
            raise type(error)(f'{address}: {error}') from error
        slots = int(dict(snapshot.details).get('directory_slots', 0))
        charged_items += max(1, len(snapshot.items), slots)
        charged_bytes += len(data) + max(1, sum(item.size for item in snapshot.items))
        if charged_items > limits.max_items or charged_bytes > limits.max_total_bytes:
            raise ResourceLimitError(f'{address}: shared max_items/max_total_bytes exceeded')
        retained = snapshot if capture else replace(snapshot, items=tuple(replace(item, payload=None) for item in snapshot.items))
        occurrences.append(ContainerOccurrence(location, retained))
        for item in snapshot.items:
            checkpoint()
            # Physical sectors and the root mini-stream alias logical stream bytes;
            # traversing them would invent extra objects and parse stream fragments.
            if item.payload is None:
                continue
            if item.kind == 'cfbf-stream' and dict(item.details).get('name') == '\x01Ole10Native':
                visit(item.payload, (*location, item.locator), 'ole-native')
            elif item.kind in ('zip-member', 'cfbf-stream', 'ole-native-data') and _profile(item.payload) is not None:
                visit(item.payload, (*location, item.locator))

    with cancellation_scope(cancelled, 'Container tree inspection', inherit=True):
        checkpoint()
        data = read_source(source, min(limits.max_input_bytes, limits.max_total_bytes), None)
        visit(data, ())
        checkpoint()
    return ContainerTree(tuple(occurrences), charged_items, charged_bytes)


def compare_container_trees(before: ContainerTree, after: ContainerTree) -> dict[str, Any]:
    """Literal occurrence-address comparison; no semantic correspondence is inferred."""
    old = {entry.location: entry.snapshot for entry in before.occurrences}
    new = {entry.location: entry.snapshot for entry in after.occurrences}
    if len(old) != len(before.occurrences) or len(new) != len(after.occurrences):
        raise ValueError('Container occurrences must have unique locations')
    shared = old.keys() & new.keys()
    changed_profiles = {location for location in shared if old[location].container != new[location].container}
    return {
        'assessment_complete': False,
        'added': [list(location) for location in sorted(new.keys() - old.keys())],
        'removed': [list(location) for location in sorted(old.keys() - new.keys())],
        'profile_changed': [{'location': list(location), 'before': old[location].container,
                             'after': new[location].container} for location in sorted(changed_profiles)],
        'shared': [{'location': list(location), 'comparison': compare_snapshots(old[location], new[location])}
                   for location in sorted(shared - changed_profiles)],
    }


__all__ = ['ContainerOccurrence', 'ContainerTree', 'compare_container_trees', 'inspect_container_tree']
