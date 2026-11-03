"""Ensure unreviewed dependency changes block the documentation publication gate."""

import json

import pytest

from tools import dependency_licenses


@pytest.fixture
def review_workspace(tmp_path, monkeypatch):
    root = dependency_licenses.ROOT
    for name in ("uv.lock", "pyproject.toml"):
        (tmp_path / name).write_bytes((root / name).read_bytes())
    evidence = tmp_path / "licenses.json"
    evidence.write_bytes(dependency_licenses.EVIDENCE.read_bytes())
    monkeypatch.setattr(dependency_licenses, "ROOT", tmp_path)
    monkeypatch.setattr(dependency_licenses, "EVIDENCE", evidence)
    return tmp_path, evidence


def test_review_survives_checkout_line_endings(review_workspace):
    root, _ = review_workspace
    lock = root / "uv.lock"
    content = lock.read_bytes().replace(b"\r\n", b"\n")
    lock.write_bytes(content)
    count = len(dependency_licenses.reviewed_inventory()["packages"])
    lock.write_bytes(content.replace(b"\n", b"\r\n"))
    assert len(dependency_licenses.reviewed_inventory()["packages"]) == count


@pytest.mark.parametrize("change", ("omitted-package", "wrong-artifact", "changed-config", "changed-lock"))
def test_unreviewed_changes_are_rejected(review_workspace, change):
    root, evidence = review_workspace
    data = json.loads(evidence.read_text(encoding="utf-8"))
    if change == "omitted-package":
        data["packages"].pop()
    elif change == "wrong-artifact":
        data["packages"][0]["artifacts"][0]["expected_sha256"] = "0" * 64
    elif change == "changed-config":
        config = root / "pyproject.toml"
        config.write_text(config.read_text(encoding="utf-8").replace('"setuptools>=77"', '"setuptools>=78"'), encoding="utf-8")
    else:
        with (root / "uv.lock").open("a", encoding="utf-8") as stream:
            stream.write("\n# unreviewed lock change\n")
    evidence.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        dependency_licenses.reviewed_inventory()
