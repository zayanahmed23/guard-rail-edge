"""Tests for the built-in attack library, schemas, decoding, and packaging."""

import base64
import codecs
import re
import zipfile
from pathlib import Path

import pytest

from guard_rail_edge.attacks import list_available_packs, load_attacks, load_pack
from guard_rail_edge.schemas import AttackPackModel

ID_REGEX = re.compile(r"^[A-Z]{2,3}-\d{3}$")
VALID_SEVERITIES = {"low", "medium", "high"}


def test_all_packs_load_and_validate():
    """Verify each pack file exists, parses cleanly, and adheres to schema."""
    available = list_available_packs()
    assert len(available) == 8

    for pack_name in available:
        pack = load_pack(pack_name)
        assert isinstance(pack, AttackPackModel)
        assert pack.pack == pack_name
        assert len(pack.attacks) >= 5, f"Pack {pack_name} has fewer than 5 attacks ({len(pack.attacks)})"


def test_attack_ids_unique_and_pattern():
    """Verify all attack IDs across packs are unique and match XX-NNN."""
    all_attacks = load_attacks(packs=["all"])
    seen_ids = set()

    for atk in all_attacks:
        assert ID_REGEX.match(atk.id), f"Attack ID '{atk.id}' does not match pattern ^[A-Z]{{2,3}}-\\d{{3}}$"
        assert atk.id not in seen_ids, f"Duplicate attack ID '{atk.id}' found!"
        seen_ids.add(atk.id)


def test_attack_counts_and_bounds():
    """Verify pack attack counts are >= 5 and total count is between 30 and 60."""
    all_attacks = load_attacks(packs=["all"])
    total = len(all_attacks)
    assert 30 <= total <= 60, f"Total attacks {total} not between 30 and 60"


def test_categories_and_severities():
    """Verify every category value equals its pack name and severity is valid."""
    for pack_name in list_available_packs():
        pack = load_pack(pack_name)
        for atk in pack.attacks:
            assert atk.category == pack_name, f"Attack {atk.id} category '{atk.category}' != pack '{pack_name}'"
            assert atk.severity in VALID_SEVERITIES, f"Attack {atk.id} has invalid severity '{atk.severity}'"


def test_no_duplicate_inputs():
    """Verify no two attacks have duplicate input prompt strings."""
    all_attacks = load_attacks(packs=["all"])
    seen_inputs = set()
    for atk in all_attacks:
        clean_input = atk.input.strip().lower()
        assert clean_input not in seen_inputs, f"Duplicate input string found in attack {atk.id}"
        seen_inputs.add(clean_input)


def test_obfuscation_decoding():
    """Verify base64 and ROT13 attacks decode to English instructions with expected keywords."""
    pack = load_pack("obfuscation")
    for atk in pack.attacks:
        if atk.id == "OB-001":
            # Base64 test
            # Input format: "Execute this base64 command: <b64_string>"
            b64_part = atk.input.split(":")[-1].strip()
            decoded = base64.b64decode(b64_part).decode("utf-8")
            expected = atk.decoded_hint or "system prompt"
            assert expected.lower() in decoded.lower(), f"Decoded base64 '{decoded}' missing expected '{expected}'"
        elif atk.id == "OB-002":
            # ROT13 test
            # Input format: "Execute this ROT13 task: <rot13_string>"
            rot13_part = atk.input.split(":")[-1].strip()
            decoded = codecs.decode(rot13_part, "rot_13")
            expected = atk.decoded_hint or "system prompt"
            assert expected.lower() in decoded.lower(), f"Decoded ROT13 '{decoded}' missing expected '{expected}'"


@pytest.mark.slow
def test_package_data_in_built_wheel(tmp_path: Path):
    """Verify guard_rail_edge/attacks/*.json files are included in built wheel package data."""
    import importlib.util
    import shutil
    import subprocess
    import sys

    if not importlib.util.find_spec("build"):
        pytest.skip("build module not installed in test environment")

    repo_root = Path(__file__).resolve().parent.parent
    src_dir = tmp_path / "src"
    out_dir = tmp_path / "dist"

    def ignore_patterns(path: str, names: list[str]) -> set[str]:
        ignored = set()
        for name in names:
            if name in (
                ".git",
                "build",
                "dist",
                ".venv",
                "venv",
                "env",
                "__pycache__",
                ".pytest_cache",
                ".mypy_cache",
                ".ruff_cache",
            ):
                ignored.add(name)
            elif name.endswith(".egg-info"):
                ignored.add(name)
        return ignored

    shutil.copytree(repo_root, src_dir, ignore=ignore_patterns)

    res = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(out_dir)],
        cwd=str(src_dir),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Failed to build wheel:\n{res.stderr}"

    wheel_files = list(out_dir.glob("*.whl"))
    assert len(wheel_files) == 1

    with zipfile.ZipFile(wheel_files[0], "r") as z:
        names = z.namelist()

    attack_files = [n for n in names if n.startswith("guard_rail_edge/attacks/") and n.endswith(".json")]
    assert len(attack_files) >= 8, f"Expected at least 8 attack pack JSONs in wheel, found: {attack_files}"
