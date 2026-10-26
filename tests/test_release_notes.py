from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "scripts"
    / "generate_release_notes.py"
)
SPEC = importlib.util.spec_from_file_location("generate_release_notes", SCRIPT)
assert SPEC and SPEC.loader
release_notes = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_notes)


def test_resolve_tag_accepts_metadata_version(monkeypatch) -> None:
    monkeypatch.setattr(
        release_notes,
        "_tag_exists",
        lambda tag: tag == "v2.4.0",
    )

    assert release_notes._resolve_tag("2.4.0") == "v2.4.0"
    assert release_notes._resolve_tag("v2.4.0") == "v2.4.0"
    assert release_notes._release_tag("2.5.0") == "v2.5.0"


def test_commits_uses_resolved_release_tag(monkeypatch) -> None:
    calls: list[tuple[str, ...]] = []

    monkeypatch.setattr(release_notes, "_tag_exists", lambda tag: tag == "v2.4.0")

    def _run_git(*args: str) -> str:
        calls.append(args)
        return ""

    monkeypatch.setattr(release_notes, "_run_git", _run_git)

    assert release_notes._commits("2.4.0") == []
    assert calls == [
        (
            "log",
            "--no-merges",
            "--pretty=format:%s%x09%h",
            "v2.4.0..HEAD",
        )
    ]
