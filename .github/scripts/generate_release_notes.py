#!/usr/bin/env python3
"""Generate bilingual release notes from conventional commits."""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone


CATEGORIES = [
    ("Features / 新功能", {"feat", "feature"}),
    ("Fixes / 修复", {"fix", "bugfix"}),
    ("Performance / 性能", {"perf"}),
    ("Documentation / 文档", {"docs"}),
    ("Refactoring / 重构", {"refactor"}),
    ("Tests and CI / 测试与 CI", {"test", "ci", "build"}),
    ("Maintenance / 维护", {"chore", "style", "revert"}),
]
CONVENTIONAL = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\([^)]+\))?!?:\s*(?P<description>.+)$")
VERSION_COMMIT = re.compile(r"^(release|version|prepare|bump)\b", re.IGNORECASE)


def _run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _tag_exists(tag: str) -> bool:
    return subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", tag],
        capture_output=True,
        text=True,
    ).returncode == 0


def _tag_candidates(version: str) -> tuple[str, ...]:
    if not version or version == "none":
        return ()
    if version.startswith("v"):
        return (version, version[1:])
    return (f"v{version}", version)


def _resolve_tag(version: str) -> str | None:
    for candidate in _tag_candidates(version):
        if _tag_exists(candidate):
            return candidate
    return None


def _release_tag(version: str) -> str:
    return version if version.startswith("v") else f"v{version}"


def _commits(old_version: str) -> list[tuple[str, str]]:
    args = ["log", "--no-merges", "--pretty=format:%s%x09%h"]
    old_tag = _resolve_tag(old_version)
    if old_tag:
        args.append(f"{old_tag}..HEAD")
    else:
        args.extend(["-20", "HEAD"])

    commits = []
    for line in _run_git(*args).splitlines():
        subject, _, commit_hash = line.partition("\t")
        if subject and commit_hash:
            commits.append((subject.strip(), commit_hash))
    return commits


def _category_for(subject: str) -> tuple[str, str] | None:
    match = CONVENTIONAL.match(subject)
    if not match:
        return "Other Changes / 其他变更", subject

    commit_type = match.group("type").lower()
    description = match.group("description").strip()
    if commit_type == "chore" and VERSION_COMMIT.match(description):
        return None

    for title, types in CATEGORIES:
        if commit_type in types:
            return title, description
    return "Other Changes / 其他变更", description


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: generate_release_notes.py <version> <old_version> <owner/repo>"
        )

    version, old_version, repository = sys.argv[1:]
    new_tag = _release_tag(version)
    grouped: dict[str, list[tuple[str, str]]] = {}
    for subject, commit_hash in _commits(old_version):
        categorized = _category_for(subject)
        if categorized is None:
            continue
        title, description = categorized
        grouped.setdefault(title, []).append((description, commit_hash))

    lines = [
        f"## Mnemosyne {new_tag}",
        "",
        f"_Release date / 发布日期: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}_",
        "",
        "### 更新内容 / Changes",
        "",
    ]

    category_titles = [title for title, _ in CATEGORIES] + ["Other Changes / 其他变更"]
    has_changes = False
    for title in category_titles:
        entries = grouped.get(title, [])
        if not entries:
            continue
        has_changes = True
        lines.extend([f"#### {title}", ""])
        lines.extend(
            f"- {description} (`{commit_hash}`)" for description, commit_hash in entries
        )
        lines.append("")

    if not has_changes:
        lines.extend(["- No user-facing changes recorded. / 暂无记录的变更。", ""])

    old_tag = _resolve_tag(old_version)
    if old_tag:
        compare_url = (
            f"https://github.com/{repository}/compare/{old_tag}...{new_tag}"
        )
        lines.extend(
            [
                "### 完整变更 / Full Changelog",
                "",
                f"[{old_tag}...{new_tag}]({compare_url})",
            ]
        )

    print("\n".join(lines).rstrip() + "\n")


if __name__ == "__main__":
    main()
