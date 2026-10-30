"""Tests verifying README, documentation integrity, link validity, and style constraints."""

import re
from pathlib import Path


def _slugify_heading(heading: str) -> str:
    """Convert heading text into GitHub markdown anchor format."""
    # Strip markdown formatting like backticks, links
    cleaned = re.sub(r"`([^`]+)`", r"\1", heading)
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    # Remove emojis and non-alphanumeric except spaces and hyphens
    cleaned = re.sub(r"[^\w\s-]", "", cleaned, flags=re.UNICODE)
    cleaned = cleaned.strip().lower()
    # Replace spaces with hyphens
    return re.sub(r"[-\s]+", "-", cleaned)


def test_readme_length() -> None:
    """Assert README.md is concise (<= 260 lines)."""
    readme_path = Path("README.md")
    assert readme_path.is_file(), "README.md not found"
    lines = readme_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 260, f"README.md exceeds 260 lines: {len(lines)}"


def test_quickstart_no_gemma() -> None:
    """Assert gemma:2b does not appear in the Quickstart section of README.md."""
    text = Path("README.md").read_text(encoding="utf-8")
    quickstart_match = re.search(r"## ⚡ Quickstart.*?(?=## |\Z)", text, re.DOTALL)
    assert quickstart_match is not None, "Quickstart section missing in README.md"
    quickstart_content = quickstart_match.group(0)
    assert "gemma:2b" not in quickstart_content, "gemma:2b must not be recommended in Quickstart"


def test_docs_minimum_lines() -> None:
    """Assert all files in docs/ have at least 30 lines."""
    docs_dir = Path("docs")
    assert docs_dir.is_dir()
    md_files = list(docs_dir.glob("*.md"))
    assert len(md_files) >= 5, "Expected at least 5 documentation files in docs/"

    for doc_path in md_files:
        lines = doc_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 30, f"{doc_path} has fewer than 30 lines ({len(lines)})"


def test_readme_relative_links_and_anchors() -> None:
    """Assert every relative link in README.md resolves to an existing file and heading anchor."""
    readme_path = Path("README.md")
    content = readme_path.read_text(encoding="utf-8")
    repo_root = Path(".")

    # Extract [text](target)
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    matches = link_pattern.findall(content)

    for text, link in matches:
        # Ignore external links, mailto, badges
        if link.startswith(("http://", "https://", "mailto:")):
            continue

        target_file_part = link
        anchor_part = None
        if "#" in link:
            target_file_part, anchor_part = link.split("#", 1)

        # Self-referential anchor within README.md
        if not target_file_part:
            target_file = readme_path
        else:
            target_file = repo_root / Path(target_file_part)

        assert target_file.exists(), f"Broken link in README: {link} -> {target_file} does not exist"

        if anchor_part and target_file.is_file():
            target_text = target_file.read_text(encoding="utf-8")
            headings = re.findall(r"^#+\s+(.+)$", target_text, re.MULTILINE)
            anchors = {_slugify_heading(h) for h in headings}
            assert anchor_part in anchors, f"Broken anchor #{anchor_part} in {link}. Available: {anchors}"
