"""Local EPUB paths and manifest inspection, without XHTML or Office backends."""

from __future__ import annotations

import posixpath
from collections.abc import Callable
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

from opendoc_formats.errors import InvalidDocumentError, UnsupportedDocumentError
from opendoc_formats.support.cancellation import checkpoint

if TYPE_CHECKING:
    from opendoc_formats.anatomy import EpubAudit, XmlNodeInfo

CONTAINER = '{urn:oasis:names:tc:opendocument:xmlns:container}'
OPF = '{http://www.idpf.org/2007/opf}'
PACKAGE_TYPE = 'application/oebps-package+xml'


def local_path(base: str, href: str) -> str:
    """Keep the existing EPUB reader's local URL policy; never access filesystem/network."""
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        raise ValueError('Remote EPUB package references are not supported')
    decoded = unquote(parsed.path)
    if not decoded or decoded.startswith('/') or '\\' in decoded or '\x00' in decoded:
        raise ValueError('Invalid EPUB package path')
    name = posixpath.normpath(posixpath.join(posixpath.dirname(base), decoded))
    if name in {'.', '..'} or name.startswith('../') or ':' in name.split('/')[0]:
        raise ValueError('EPUB package reference escapes the archive')
    return name


def _inspection_path(base: str, href: str, location: str) -> str:
    try:
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc:
            raise UnsupportedDocumentError(f'{location}: remote EPUB manifest reference is outside the inspection profile')
        return local_path(base, href)
    except UnsupportedDocumentError:
        raise
    except ValueError as error:
        raise InvalidDocumentError(f'{location}: {error}') from error


def _profile(nodes: tuple[XmlNodeInfo, ...], name: str, tag: str) -> None:
    if not nodes or nodes[0].tag != tag:
        raise InvalidDocumentError(f'zip:/{name}: unexpected EPUB control XML root')
    for node in nodes:
        checkpoint()
        if '{http://www.w3.org/XML/1998/namespace}base' in dict(node.attributes):
            raise UnsupportedDocumentError(f'zip:/{name}#xml:{node.path}: xml:base is outside the inspection profile')


def inspection_content_types(
    read_xml: Callable[[str], tuple[XmlNodeInfo, ...]],
) -> tuple[dict[str, str], tuple[str, ...], EpubAudit]:
    """Inspect every OPF rendition; retain external references without dereferencing them."""
    from opendoc_formats.anatomy import EpubAudit, EpubManifestReference

    container_name = 'META-INF/container.xml'
    nodes = read_xml(container_name)
    _profile(nodes, container_name, CONTAINER+'container')
    by_path = {node.path: node for node in nodes}
    rootfiles, seen_roots = [], set()
    for node in nodes:
        checkpoint()
        if node.tag != CONTAINER+'rootfile' or node.path.count('/') != 2:
            continue
        if by_path[node.path.rsplit('/', 1)[0]].tag != CONTAINER+'rootfiles':
            continue
        attributes = dict(node.attributes)
        if attributes.get('media-type') == PACKAGE_TYPE:
            name = _inspection_path('', attributes.get('full-path', ''), f'zip:/{container_name}#xml:{node.path}')
            if name in seen_roots:
                raise InvalidDocumentError(f'zip:/{container_name}: duplicate OPF rootfile')
            seen_roots.add(name)
            rootfiles.append(name)
    if not rootfiles:
        raise InvalidDocumentError(f'zip:/{container_name}: no OPF rootfile')
    types = {name: PACKAGE_TYPE for name in rootfiles}
    references = []
    for name in rootfiles:
        checkpoint()
        nodes = read_xml(name)
        _profile(nodes, name, OPF+'package')
        manifest = [node.path for node in nodes if node.tag == OPF+'manifest' and node.path.count('/') == 1]
        if len(manifest) != 1:
            raise InvalidDocumentError(f'zip:/{name}: expected one EPUB manifest')
        identifiers: set[str] = set()
        names: set[tuple[str, str]] = set()
        for node in nodes:
            checkpoint()
            if node.tag != OPF+'item' or node.path.rsplit('/', 1)[0] != manifest[0]:
                continue
            attributes = dict(node.attributes)
            identifier, media_type = attributes.get('id'), attributes.get('media-type')
            location = f'zip:/{name}#xml:{node.path}'
            href = attributes.get('href', '')
            if not identifier or not media_type or identifier in identifiers or not href:
                raise InvalidDocumentError(f'{location}: invalid/duplicate EPUB manifest item')
            try:
                parsed = urlsplit(href)
            except ValueError as error:
                raise InvalidDocumentError(f'{location}: invalid EPUB resource reference: {error}') from error
            external = bool(parsed.scheme or parsed.netloc)
            target = None if external else _inspection_path(name, href, location)
            key = ('external', href) if external else ('local', str(target))
            if target == container_name:
                raise UnsupportedDocumentError(f'zip:/{name}: container.xml as a manifest resource is outside the profile')
            if key in names:
                raise InvalidDocumentError(f'{location}: invalid/duplicate EPUB manifest item')
            if target is not None and target in types and types[target] != media_type:
                raise InvalidDocumentError(f'zip:/{name}#xml:{node.path}: conflicting resource media types: {target}')
            identifiers.add(identifier)
            names.add(key)
            if target is not None:
                types[target] = media_type
            references.append(EpubManifestReference(location, name, identifier, href, media_type, target,
                                                     'external-unassessed' if external else 'local', node.attributes))
    return types, tuple(rootfiles), EpubAudit(tuple(references))
