"""The external acceptance checker rejects unverified distributions before execution."""

import pytest

from tools.epubcheck import check


def test_changed_distribution_is_rejected_before_java(tmp_path, monkeypatch):
    import tools.epubcheck as acceptance

    archive = tmp_path / "modified.zip"
    archive.write_bytes(b"unverified distribution")

    def forbidden(*args, **kwargs):
        pytest.fail("Unverified distribution must not launch Java")

    monkeypatch.setattr(acceptance.subprocess, "run", forbidden)
    with pytest.raises(ValueError, match="digest mismatch"):
        check(archive, "java", tmp_path / "workspace")
    assert not (tmp_path / "workspace").exists()
