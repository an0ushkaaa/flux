"""
tools/skills_loader.py

Loads trading strategy skill files from flux/skills/.
The active skill is selected via the ACTIVE_SKILL environment variable.
"""

import os
from pathlib import Path

# Skills directory is always relative to this file's location
_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


def load_skill(skill_name: str) -> str:
    """
    Load a trading strategy skill by name.

    Parameters
    ----------
    skill_name:
        Filename without extension, e.g. "aggressive_momentum" or
        "conservative_dip_buy".

    Returns
    -------
    Full text content of the skill file.

    Raises
    ------
    FileNotFoundError
        If no matching .txt file exists in the skills directory.
    """
    skill_path = _SKILLS_DIR / f"{skill_name}.txt"

    if not skill_path.exists():
        available = list_available_skills()
        available_str = ", ".join(available) if available else "(none found)"
        raise FileNotFoundError(
            f"Skill '{skill_name}' not found at '{skill_path}'.\n"
            f"Available skills: {available_str}"
        )

    return skill_path.read_text(encoding="utf-8")


def list_available_skills() -> list[str]:
    """
    Return the names of all skills in the skills directory.

    Returns
    -------
    Sorted list of skill names (filenames without the .txt extension).
    Empty list if the skills directory doesn't exist or contains no .txt files.
    """
    if not _SKILLS_DIR.exists():
        return []

    return sorted(p.stem for p in _SKILLS_DIR.glob("*.txt"))


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from config import ACTIVE_SKILL

    print("=" * 55)
    print("Available skills")
    print("=" * 55)
    for name in list_available_skills():
        marker = "  <-- active" if name == ACTIVE_SKILL else ""
        print(f"  {name}{marker}")

    print()
    print("=" * 55)
    print(f"Active skill: {ACTIVE_SKILL}")
    print("=" * 55)
    try:
        content = load_skill(ACTIVE_SKILL)
        print(content)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
