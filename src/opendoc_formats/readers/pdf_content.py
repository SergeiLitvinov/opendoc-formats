"""Disposable native content view without interactive appearances or stale caches."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from opendoc_model import ArtifactLimitError

from opendoc_formats.support.cancellation import check_cancelled


@contextmanager
def content_only_pdf(path: str | Path, *, cancelled: Callable[[], bool] | None = None) -> Iterator[Any]:
    check_cancelled(cancelled, 'PDF content view')
    import pymupdf

    if Path(path).stat().st_size > 128 * 1024 * 1024:
        raise ArtifactLimitError('PDF content view exceeds 128 MiB source limit')
    with pymupdf.open(path) as source:
        count = 0
        changed = False
        for page in source:
            check_cancelled(cancelled, 'PDF content page')
            for accessor, delete in ((page.annots, page.delete_annot), (page.widgets, page.delete_widget)):
                for annotation in accessor() or ():
                    check_cancelled(cancelled, 'PDF content interaction')
                    count += 1
                    if count > 10_000:
                        raise ArtifactLimitError('PDF interaction objects exceed 10000')
                    delete(annotation)
                    changed = True
        if not changed:
            check_cancelled(cancelled, 'PDF content view')
            yield source
            return
        # Reopening also clears native page/link/appearance caches. reload_page is
        # insufficient when the backend holds references from cross-page links.
        data = source.tobytes()
        check_cancelled(cancelled, 'PDF content snapshot')
        if len(data) > 256 * 1024 * 1024:
            raise ArtifactLimitError('PDF content view exceeds 256 MiB snapshot limit')
        with pymupdf.open(stream=data, filetype='pdf') as content:
            yield content
