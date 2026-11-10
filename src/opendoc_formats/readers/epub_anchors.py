"""Import-local EPUB source identities; this is not a Model transport or general ID codec."""

from __future__ import annotations

import hashlib
import posixpath
import re
from collections.abc import Callable

from opendoc_model import ArtifactLimitError

from opendoc_formats.support.cancellation import check_cancelled


class EpubAnchors:
    def __init__(self, maximum: int, cancelled: Callable[[], bool] | None = None, *, root_directory: str = '') -> None:
        self.maximum, self.cancelled = maximum, cancelled
        self.root_directory = posixpath.normpath(root_directory or '.')
        self.ids: dict[tuple[str, str, int], str] = {}
        self.owners: dict[str, tuple[str, str, int]] = {}
        self.occurrences: dict[str, int] = {}
        self.current: tuple[str, int] | None = None
        self.serial = 0

    def _path(self, chapter: str) -> str:
        return (posixpath.normpath(chapter).lstrip('/') if chapter.startswith('/')
                else posixpath.normpath(posixpath.join(self.root_directory, chapter)))

    def begin_chapter(self, chapter: str) -> None:
        check_cancelled(self.cancelled, 'EPUB spine occurrence')
        path = self._path(chapter)
        occurrence = self.occurrences.get(path, 0) + 1
        self.occurrences[path] = occurrence
        self.current = path, occurrence

    def get(self, chapter: str, fragment: str = '') -> str:
        check_cancelled(self.cancelled, 'EPUB anchor identity')
        path = self._path(chapter)
        occurrence = self.current[1] if self.current is not None and self.current[0] == path else 1
        key = path, fragment, occurrence
        if key in self.ids:
            return self.ids[key]
        if len(self.ids) >= self.maximum:
            raise ArtifactLimitError('EPUB source anchor identities exceed staging limit',
                                     path=f'epub.anchors[{len(self.ids)}]', quota='anchor identities', maximum=self.maximum)
        value = posixpath.relpath(path, self.root_directory)+('--'+fragment if fragment else '')
        legacy = 'epub-'+re.sub(r'[^a-zA-Z0-9_.:-]+', '-', value).strip('-')
        if occurrence > 1:
            legacy += f'--spine-{occurrence}'
        candidate = legacy
        if candidate in self.owners:
            encoded_path = key[0].encode('utf-8')
            identity = len(encoded_path).to_bytes(8, 'big') + encoded_path + fragment.encode('utf-8')
            if occurrence > 1:
                identity += b'\0spine\0' + str(occurrence).encode('ascii')
            digest = hashlib.sha256(identity).hexdigest()
            candidate = legacy+'-'+digest[:12]
            while candidate in self.owners:
                check_cancelled(self.cancelled, 'EPUB anchor collision')
                self.serial += 1
                candidate = legacy+'-'+digest+'-'+str(self.serial)
        self.ids[key] = candidate
        self.owners[candidate] = key
        return candidate
