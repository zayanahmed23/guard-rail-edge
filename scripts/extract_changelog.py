"""Extract release notes for a specified version/tag from CHANGELOG.md."""

import re
import sys
from pathlib import Path


def extract_release_notes(changelog_path: Path, tag: str) -> str:
    """Extract release notes matching version tag from CHANGELOG.md."""
    clean_version = tag.lstrip("v")
    if not changelog_path.exists():
        return f"Release {tag}"

    content = changelog_path.read_text(encoding="utf-8")
    pattern = rf"## \[{re.escape(clean_version)}\][^\n]*\n(.*?)(?=\n---\n|\n## \[|$)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return f"Release {tag}"


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python extract_changelog.py <tag> [changelog_path]", file=sys.stderr)
        sys.exit(1)

    tag = sys.argv[1]
    changelog_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("CHANGELOG.md")
    notes = extract_release_notes(changelog_path, tag)
    print(notes)


if __name__ == "__main__":
    main()
