"""Managed LibreOffice conversion into validated PDF with atomic publication."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, fields
from hashlib import sha256
from pathlib import Path

from opendoc_formats.errors import BackendUnavailableError, InvalidDocumentError, OfficeTimeoutError, UnsupportedDocumentError
from opendoc_formats.native.common import Cancellation, backend, check_cancel, positive_int, positive_number, publish, read_source
from opendoc_formats.pdf import PdfDocument, PdfLimits

_CANDIDATES = (
    Path(r"C:\Program Files\LibreOffice\program\soffice.com"),
    Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.com"),
    Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
    Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
    Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
    Path("/usr/bin/libreoffice"),
    Path("/usr/bin/soffice"),
    Path("/usr/local/bin/soffice"),
    Path("/opt/libreoffice/program/soffice"),
)
_EXTENSIONS = {".doc", ".docx", ".dotx", ".odt", ".rtf", ".ppt", ".pptx", ".odp", ".xls", ".xlsx", ".ods"}
_PROFILE = """<?xml version="1.0" encoding="UTF-8"?>
<oor:items xmlns:oor="http://openoffice.org/2001/registry">
<item oor:path="/org.openoffice.Office.Common/Security/Scripting">
<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>
<prop oor:name="DisableActiveContent" oor:op="fuse"><value>true</value></prop>
<prop oor:name="MacroSecurityLevel" oor:op="fuse"><value>3</value></prop>
</item></oor:items>"""


@dataclass(frozen=True)
class OfficeLimits:
    max_input_bytes: int = 100 * 1024 * 1024
    max_output_bytes: int = 128 * 1024 * 1024
    max_pages: int = 10_000

    def __post_init__(self) -> None:
        for item in fields(self):
            positive_int(getattr(self, item.name), item.name)


@dataclass(frozen=True)
class OfficeConversionResult:
    output: Path
    page_count: int
    bytes_written: int
    sha256: str


def find_libreoffice() -> Path | None:
    """Locate an existing executable; never install or launch it."""
    located = shutil.which("soffice") or shutil.which("libreoffice")
    if located is not None:
        return Path(located)
    return next((path for path in _CANDIDATES if path.is_file()), None)


def _kill_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
        if process.poll() is None:
            process.kill()
    else:
        try:
            getattr(os, "killpg")(process.pid, getattr(signal, "SIGKILL"))
        except ProcessLookupError:
            pass
    process.wait()


def convert_office_to_pdf(
    source: str | Path,
    output: str | Path,
    *,
    executable: str | Path | None = None,
    timeout: float = 180,
    limits: OfficeLimits = OfficeLimits(),
    cancelled: Cancellation | None = None,
) -> OfficeConversionResult:
    """Convert trusted office input; the external engine is not a filesystem/network sandbox.

    An isolated profile disables macros. The managed subprocess is terminated on timeout/cancellation.
    Input/output bounds are checked before launch/after conversion, not inside LibreOffice allocations.
    """
    if not isinstance(limits, OfficeLimits):
        raise TypeError("limits must be OfficeLimits")
    if cancelled is not None and not callable(cancelled):
        raise TypeError("cancelled must be callable")
    timeout = positive_number(timeout, "timeout")
    source_path = Path(source)
    if source_path.suffix.lower() not in _EXTENSIONS:
        raise UnsupportedDocumentError("Unsupported office input extension")
    data = read_source(source_path, limits.max_input_bytes, cancelled)
    program = Path(executable) if executable is not None else find_libreoffice()
    if program is None or not program.is_file():
        raise BackendUnavailableError("LibreOffice executable is unavailable")
    backend("pymupdf", "pdf")  # Fail before launching when staged PDF validation cannot be performed.
    with tempfile.TemporaryDirectory(prefix="opendoc-formats-office-") as directory:
        work = Path(directory)
        profile = work / "profile"
        (profile / "user").mkdir(parents=True)
        (profile / "user/registrymodifications.xcu").write_text(_PROFILE, encoding="utf-8")
        staged_input = work / ("input" + source_path.suffix.lower())
        staged_input.write_bytes(data)
        args = [
            str(program.resolve()),
            "--headless",
            "--nologo",
            "--nodefault",
            "--norestore",
            f"-env:UserInstallation={profile.resolve().as_uri()}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(work),
            str(staged_input),
        ]
        check_cancel(cancelled)
        started = time.monotonic()
        try:
            process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=(
                    int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) | int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
                    if os.name == "nt"
                    else 0
                ),
                start_new_session=os.name != "nt",
            )
        except OSError as error:
            raise BackendUnavailableError(f"Cannot launch LibreOffice: {error}") from error
        try:
            while process.poll() is None:
                check_cancel(cancelled)
                if time.monotonic() - started >= timeout:
                    raise OfficeTimeoutError(f"LibreOffice exceeded {timeout:g} seconds")
                time.sleep(0.05)
            check_cancel(cancelled)
            if process.returncode != 0:
                raise InvalidDocumentError(f"LibreOffice conversion failed with exit code {process.returncode}")
        finally:
            _kill_process_tree(process)
        produced = work / "input.pdf"
        result_data = read_source(produced, limits.max_output_bytes, cancelled)
        with PdfDocument(
            result_data,
            limits=PdfLimits(max_input_bytes=limits.max_output_bytes, max_pages=limits.max_pages),
            cancelled=cancelled,
        ) as pdf:
            page_count = pdf.page_count
        target = publish(result_data, output, limits.max_output_bytes, cancelled)
        return OfficeConversionResult(target, page_count, len(result_data), sha256(result_data).hexdigest())


__all__ = ["find_libreoffice", "convert_office_to_pdf", "OfficeLimits", "OfficeConversionResult"]
