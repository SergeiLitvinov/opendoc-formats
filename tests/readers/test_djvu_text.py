"""DjVu process contracts, including real optional DjVuLibre fixtures."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from opendoc_formats.api import read_document
from opendoc_formats.errors import ExtractError, InvalidDocumentError, OperationCancelledError, ResourceLimitError
from opendoc_formats.readers.txt import read_djvu


def backend(monkeypatch, tmp_path, script):
    source = tmp_path / "input.djvu"
    source.write_bytes(b"test")
    launch = subprocess.Popen
    processes = []

    def start(args, **kwargs):
        process = launch([sys.executable, "-c", script], **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", start)
    return source, processes


def test_utf8_independent_of_locale(monkeypatch, tmp_path):
    text = "Русский — café, Straße, Ελληνικά\n\f"
    source, _ = backend(monkeypatch, tmp_path, f"import sys; sys.stdout.buffer.write({text.encode()!r})")
    monkeypatch.setattr("locale.getencoding", lambda: "cp1251")
    assert read_djvu(source).plain == text


@pytest.mark.parametrize("payload", [b"", b" \r\n\f\t\f"])
def test_empty_layer_fails_registry(monkeypatch, tmp_path, payload):
    source, _ = backend(monkeypatch, tmp_path, f"import sys; sys.stdout.buffer.write({payload!r})")
    result = read_djvu(source)
    assert not result and result.warnings
    with pytest.raises(ExtractError, match="hidden text"):
        read_document(source)


def test_invalid_utf8(monkeypatch, tmp_path):
    source, _ = backend(monkeypatch, tmp_path, "import sys; sys.stdout.buffer.write(b'\\xff')")
    with pytest.raises(InvalidDocumentError, match="UTF-8"):
        read_djvu(source)


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_bounded_output(monkeypatch, tmp_path, stream):
    source, processes = backend(
        monkeypatch, tmp_path, f"import sys,time; sys.{stream}.buffer.write(b'x'*100000); time.sleep(10)",
    )
    with pytest.raises(ResourceLimitError):
        read_djvu(source, max_output_bytes=100)
    assert processes[0].poll() is not None


def test_timeout_and_cancellation_stop_process(monkeypatch, tmp_path):
    source, processes = backend(monkeypatch, tmp_path, "import time; time.sleep(10)")
    assert "timeout" in read_djvu(source, timeout=0.1).warnings[0]
    assert processes[-1].poll() is not None
    started = time.monotonic()
    with pytest.raises(OperationCancelledError):
        read_djvu(source, cancelled=lambda: time.monotonic() - started > 0.1)
    assert processes[-1].poll() is not None
    assert time.monotonic() - started < 3


def test_cancelled_before_start(monkeypatch, tmp_path):
    source, processes = backend(monkeypatch, tmp_path, "raise AssertionError('must not run')")
    with pytest.raises(OperationCancelledError):
        read_djvu(source, cancelled=lambda: True)
    assert not processes


def test_missing_backend_and_bad_exit(monkeypatch, tmp_path):
    source, _ = backend(monkeypatch, tmp_path, "raise SystemExit(7)")
    assert read_djvu(source).warnings == ["djvutxt rc=7"]

    def absent(*args, **kwargs):
        raise FileNotFoundError("djvutxt")

    monkeypatch.setattr(subprocess, "Popen", absent)
    assert "not found" in read_djvu(source).warnings[0]


@pytest.mark.parametrize("with_text", [True, False])
def test_real_djvulibre(tmp_path: Path, with_text: bool):
    if any(shutil.which(tool) is None for tool in ("c44", "djvused", "djvm", "djvutxt")):
        pytest.skip("optional external DjVuLibre tools unavailable")
    texts = ("Страница №1 — проверка", "Résumé: café, Straße, Ελληνικά")
    image = tmp_path / "page.ppm"
    image.write_bytes(b"P6\n320 180\n255\n" + b"\xff\xff\xff" * (320 * 180))
    pages = []
    for index, text in enumerate(texts):
        page = tmp_path / f"page-{index}.djvu"
        subprocess.run(["c44", str(image), str(page)], check=True, capture_output=True, timeout=30)
        if with_text:
            layer = tmp_path / f"layer-{index}.sexp"
            layer.write_text(f"(page 0 0 320 180 {json.dumps(text, ensure_ascii=False)})\n", encoding="utf-8")
            script = tmp_path / f"layer-{index}.script"
            script.write_text(f'select 1\nset-txt "{layer.as_posix()}"\nsave\n', encoding="utf-8")
            subprocess.run(["djvused", str(page), "-f", str(script)], check=True, capture_output=True, timeout=30)
        pages.append(str(page))
    source = tmp_path / "combined.djvu"
    subprocess.run(["djvm", "-c", str(source), *pages], check=True, capture_output=True, timeout=30)
    result = read_djvu(source)
    if with_text:
        assert all(text in result.plain for text in texts)
        assert result.plain.index(texts[0]) < result.plain.index(texts[1])
        assert read_document(source).success
    else:
        assert not result
        with pytest.raises(ExtractError):
            read_document(source)
