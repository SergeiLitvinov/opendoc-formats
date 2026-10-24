"""Physical OPC graph audit over bounded inventories; no conformance or fidelity certificate."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.native.opc import RELATIONSHIPS, RELATIONSHIPS_TYPE, relationship_owner, resolve_target
from opendoc_formats.support.cancellation import cancellable_items, checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import BinaryItem, OpcAudit


def audit_package(items: Iterable[BinaryItem], overrides: Mapping[str, str]) -> OpcAudit:
    """Audit every physical relationship part, including disconnected components and cycles."""
    from opendoc_formats.anatomy import OpcAudit, OpcFinding, OpcRelationship

    physical = {item.locator.removeprefix('zip:'): item for item in cancellable_items(items) if item.kind == 'zip-member'}
    rels = {name for name, item in cancellable_items(physical.items()) if relationship_owner(name) is not None
            or dict(item.details).get('content_type') == RELATIONSHIPS_TYPE}
    parts = set(physical)-rels-{'/[Content_Types].xml'}
    edges: list[OpcRelationship] = []
    findings: list[OpcFinding] = []
    adjacency: dict[str, list[str]] = {}

    def finding(code: str, location: str, message: str) -> None:
        findings.append(OpcFinding('opc.'+code, location, message))

    for name in sorted(overrides):
        checkpoint()
        if name not in physical:
            finding('override-target-missing', 'zip:/[Content_Types].xml', f'Override targets a missing part: {name}')
    for name, item in sorted(physical.items()):
        checkpoint()
        declared = dict(item.details).get('content_type')
        if name != '/[Content_Types].xml' and declared is None:
            finding('content-type-missing', item.locator, 'Physical part has no declared content type')
        if name not in rels:
            continue
        owner = relationship_owner(name)
        if owner is None:
            finding('owner-address-invalid', item.locator, 'Relationship part has no recognized owner address')
        elif owner != '/' and owner not in parts:
            finding('owner-missing', item.locator, f'Relationship owner is not a physical data part: {owner}')
        if declared != RELATIONSHIPS_TYPE:
            finding('relationship-content-type', item.locator, 'Relationship content type is missing or outside the profile')
        nodes = item.xml_nodes
        if not nodes:
            finding('relationship-uninspected', item.locator, 'Relationship XML was not inspected')
            continue
        if nodes[0].tag != RELATIONSHIPS+'Relationships':
            finding('relationship-root', item.locator, 'Expected OPC Relationships root')
            continue
        if nodes[0].attributes:
            finding('relationship-extension', item.locator+'#xml:0', 'Root attributes are outside the relationship profile')
        seen = set()
        for node in nodes[1:]:
            checkpoint()
            location = item.locator+'#xml:'+node.path
            if node.path.count('/') != 1 or node.tag != RELATIONSHIPS+'Relationship':
                finding('relationship-extension', location, 'Markup is outside the direct Relationship profile')
                continue
            attributes = dict(node.attributes)
            identifier, kind, value = attributes.get('Id'), attributes.get('Type'), attributes.get('Target')
            mode = attributes.get('TargetMode', 'Internal')
            status, target = 'rejected', None
            valid = bool(identifier and kind and value and identifier not in seen)
            if not valid:
                finding('relationship-attributes', location, 'Missing required attribute or duplicate relationship Id')
            if identifier:
                seen.add(identifier)
            if attributes.keys()-{'Id', 'Type', 'Target', 'TargetMode'}:
                finding('relationship-extension', location, 'Attributes are outside the relationship profile')
            if valid and mode == 'External':
                status = 'external'  # retained literally; no URL, filesystem or network access
            elif valid and mode == 'Internal':
                if owner is not None:
                    try:
                        target = resolve_target(owner, value or '')
                    except InvalidDocumentError as error:
                        finding('target-invalid', location, str(error))
                    else:
                        if target not in parts:
                            finding('target-missing-or-infrastructure', location,
                                    f'Target is not a physical data part: {target}')
                        elif owner == '/' or owner in parts:
                            status = 'internal'
                            adjacency.setdefault(owner, []).append(target)
            elif valid:
                finding('target-mode', location, f'Unsupported TargetMode: {mode!r}')
            edges.append(OpcRelationship(location, name, owner, node.attributes, target, status))
    if '/_rels/.rels' not in physical:
        finding('root-unavailable', 'zip:/_rels/.rels', 'No package relationship entry point was inspected')
    reached, pending = set(), ['/']
    while pending:
        checkpoint()
        source = pending.pop()
        for target in adjacency.get(source, ()):
            checkpoint()
            if target not in reached:
                reached.add(target)
                pending.append(target)
    unreached = tuple(sorted(parts-reached))
    complete = not findings
    return OpcAudit(tuple(edges), tuple(findings), tuple(sorted(reached)), unreached,
                    unreached if complete else (), complete)
