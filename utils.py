"""
utils.py — Shared helpers for the RISC-V Instruction Set Explorer.
"""

import json
import re


# ─────────────────────────────────────────────────────────────────────────────
# Extension Name Normalisation
# ─────────────────────────────────────────────────────────────────────────────

# Prefixes used in instr_dict.json that should be stripped before comparison
_PREFIX_RE = re.compile(r'^(rv(?:32|64|128)?_)', re.IGNORECASE)


def normalize_extension(ext: str) -> str:
    """
    Normalise an extension name so that variants from different sources
    compare equal.

    Examples
    --------
    >>> normalize_extension("rv_zba")
    'Zba'
    >>> normalize_extension("rv64_zba")
    'Zba'
    >>> normalize_extension("Zba")
    'Zba'
    >>> normalize_extension("M")
    'M'
    >>> normalize_extension("zicsr")
    'Zicsr'
    >>> normalize_extension("Svinval")
    'Svinval'
    """
    if not ext:
        return ""

    ext = ext.strip()
    # Strip rv_  /  rv32_  /  rv64_  /  rv128_  prefixes (case-insensitive)
    ext = _PREFIX_RE.sub("", ext)

    # Collapse underscore variants like z_ba → zba
    ext = re.sub(r'^([zs])_', r'\1', ext, flags=re.IGNORECASE)

    # Single capital letter → keep uppercase (M, A, F, D, C, V …)
    if len(ext) == 1 and ext.isalpha():
        return ext.upper()

    # Capitalise the first letter; lowercase the rest (Zba, Zicsr, Svinval …)
    return ext[0].upper() + ext[1:].lower()


# ─────────────────────────────────────────────────────────────────────────────
# JSON Loader
# ─────────────────────────────────────────────────────────────────────────────

def load_instr_dict(path: str = "data/instr_dict.json") -> dict:
    """
    Load and return the instruction dictionary JSON as a plain Python dict.

    Parameters
    ----------
    path : str
        Path to the instr_dict.json file.

    Raises
    ------
    FileNotFoundError
        If the file does not exist at *path*.
    json.JSONDecodeError
        If the file content is not valid JSON.
    """
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)