"""Unit tests for extract_changelog script."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from extract_changelog import extract_release_notes  # noqa: E402


def test_extract_release_notes_found(tmp_path: Path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        """# Changelog

## [0.2.0] - 2026-10-25

### Features
- Attack library shipped.

---

## [0.1.3] - 2026-10-25

### Fixes
- Retry temperature fixed.
""",
        encoding="utf-8",
    )

    notes = extract_release_notes(changelog, "v0.2.0")
    assert "### Features" in notes
    assert "Attack library shipped." in notes
    assert "Retry temperature fixed." not in notes


def test_extract_release_notes_fallback_when_missing(tmp_path: Path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changelog\n", encoding="utf-8")

    notes = extract_release_notes(changelog, "v9.9.9")
    assert notes == "Release v9.9.9"
