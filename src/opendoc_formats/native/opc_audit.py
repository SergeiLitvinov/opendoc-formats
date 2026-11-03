"""Physical OPC graph audit over bounded inventories; no conformance or fidelity certificate."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from opendoc_formats.errors import InvalidDocumentError
from opendoc_formats.native.opc import RELATIONSHIPS, RELATIONSHIPS_TYPE, relationship_owner, resolve_target
from opendoc_formats.support.cancellation import cancellable_items, checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import BinaryItem, OpcAudit

# XML 1.0 Fifth Edition NameStartChar/NameChar, excluding colon for NCName.
_START = (r'A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF'
          r'\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD'
          r'\U00010000-\U000EFFFF')
_NCNAME = re.compile('['+_START+']['+_START+r'\-.0-9\u00B7\u0300-\u036F\u203F-\u2040]*')
_URI_CHARACTERS = re.compile(r"[A-Za-z0-9._~!$&'()*+,;=:/?@%#-]+")
_BAD_PERCENT = re.compile(r'%(?![0-9A-Fa-f]{2})')
_SCHEME = re.compile(r'[A-Za-z][A-Za-z0-9+.-]*')


def _literal_id(value: str) -> bool:
    checkpoint()
    result = _NCNAME.fullmatch(value) is not None
    checkpoint()
    return result


def _literal_type(value: str) -> bool:
    """Finite ASCII URI syntax, without IRI/whitespace repair or IP-literal authorities."""
    checkpoint()
    if _URI_CHARACTERS.fullmatch(value) is None or _BAD_PERCENT.search(value) or value.count('#') > 1:
        checkpoint()
        return False
    scheme, separator, suffix = value.partition(':')
    authority = ''
    if suffix.startswith('//'):
        authority = suffix[2:]
        for delimiter in '/?#':
            checkpoint()
            authority = authority.partition(delimiter)[0]
    # Generic reg-name authority and optional userinfo/decimal port. Bracketed
    # IP literals are deliberately outside this inspection profile.
    host_port = authority.rsplit('@', 1)[-1].split(':')
    result = bool(separator and _SCHEME.fullmatch(scheme) and authority.count('@') <= 1 and len(host_port) <= 2
                  and (len(host_port) == 1 or all('0' <= char <= '9' for char in host_port[1])))
    checkpoint()
    return result


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
                if not _literal_id(identifier):
                    finding('relationship-id', location, 'Id is outside the literal XML NCName profile')
                    valid = False
            if kind and not _literal_type(kind):
                finding('relationship-type', location, 'Type is outside the inspected literal ASCII URI profile')
                valid = False
            if attributes.keys()-{'Id', 'Type', 'Target', 'TargetMode'}:
                finding('relationship-extension', location, 'Attributes are outside the relationship profile')
            checkpoint()
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
