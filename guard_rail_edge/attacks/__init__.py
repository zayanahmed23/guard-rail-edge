"""Built-in attack library pack management and loader."""

import json
from importlib import resources
from typing import Literal

from guard_rail_edge.schemas import AttackModel, AttackPackModel

SEVERITY_LEVELS: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
}

AVAILABLE_PACKS: list[str] = [
    "prompt-extraction",
    "instruction-override",
    "persona-hijack",
    "format-evasion",
    "obfuscation",
    "multilingual",
    "indirect-injection",
    "secret-exfiltration",
]


def list_available_packs() -> list[str]:
    """Return the list of standard available attack pack names."""
    return sorted(AVAILABLE_PACKS)


def load_pack(pack_name: str) -> AttackPackModel:
    """Load an individual attack pack JSON from package resources."""
    valid_packs = list_available_packs()
    if pack_name not in valid_packs:
        raise ValueError(
            f"Unknown attack pack '{pack_name}'. Available packs: {', '.join(valid_packs)}"
        )

    ref = resources.files("guard_rail_edge.attacks").joinpath(f"{pack_name}.json")
    if not ref.is_file():
        raise FileNotFoundError(f"Attack pack file '{pack_name}.json' not found in package data.")

    content = ref.read_text(encoding="utf-8")
    data = json.loads(content)
    return AttackPackModel.model_validate(data)


def load_attacks(
    packs: list[str] | None = None,
    exclude: list[str] | None = None,
    min_severity: Literal["low", "medium", "high"] | str = "low",
) -> list[AttackModel]:
    """Load and filter attacks from specified packs."""
    if not packs:
        return []

    # Resolve "all"
    target_packs: set[str] = set()
    for p in packs:
        if p.strip().lower() == "all":
            target_packs.update(list_available_packs())
        else:
            target_packs.add(p.strip())

    min_lvl = SEVERITY_LEVELS.get(min_severity.lower(), 1)
    exclude_set = {x.strip().upper() for x in (exclude or [])}

    attacks: list[AttackModel] = []
    seen_ids: set[str] = set()

    for p in sorted(target_packs):
        pack_model = load_pack(p)
        for atk in pack_model.attacks:
            if atk.id.upper() in exclude_set:
                continue
            if atk.id.upper() in seen_ids:
                continue
            atk_lvl = SEVERITY_LEVELS.get(atk.severity.lower(), 1)
            if atk_lvl < min_lvl:
                continue
            seen_ids.add(atk.id.upper())
            attacks.append(atk)

    return attacks
