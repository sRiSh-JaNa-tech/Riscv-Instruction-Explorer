"""
tests/test_parser.py
====================
Unit tests for the RISC-V Instruction Set Explorer.

Run with:
    pytest tests/ -v
"""

import sys
import os

# Make the project root importable regardless of where pytest is invoked from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from utils import normalize_extension, load_instr_dict
from main import tier1_parser


# ─────────────────────────────────────────────────────────────────────────────
# Tests for normalize_extension
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizeExtension:

    def test_rv_prefix_stripped(self):
        assert normalize_extension("rv_zba") == "Zba"

    def test_rv32_prefix_stripped(self):
        assert normalize_extension("rv32_zba") == "Zba"

    def test_rv64_prefix_stripped(self):
        assert normalize_extension("rv64_zba") == "Zba"

    def test_single_letter_uppercase(self):
        assert normalize_extension("m") == "M"
        assert normalize_extension("M") == "M"
        assert normalize_extension("rv_m") == "M"

    def test_z_extension_capitalised(self):
        assert normalize_extension("zicsr") == "Zicsr"
        assert normalize_extension("Zicsr") == "Zicsr"

    def test_s_extension_capitalised(self):
        assert normalize_extension("svinval") == "Svinval"
        assert normalize_extension("Svinval") == "Svinval"

    def test_already_normalised_unchanged(self):
        assert normalize_extension("Zba") == "Zba"

    def test_empty_string_returns_empty(self):
        assert normalize_extension("") == ""

    def test_underscore_variant(self):
        # z_ba style (rare but should collapse to Zba)
        assert normalize_extension("z_ba") == "Zba"

    def test_rv_i_normalises_to_I(self):
        # rv_i is the base integer extension
        assert normalize_extension("rv_i") == "I"


# ─────────────────────────────────────────────────────────────────────────────
# Tests for tier1_parser
# ─────────────────────────────────────────────────────────────────────────────

MINIMAL_DATA = {
    "add":    {"extension": ["rv_i"]},
    "mul":    {"extension": ["rv_m"]},
    "addw":   {"extension": ["rv_i", "rv64_i"]},     # multi-extension
    "sh1add": {"extension": ["rv_zba", "rv64_zba"]}, # multi-extension
    "sub":    {"extension": ["rv_i"]},
}


class TestTier1Parser:

    def setup_method(self):
        """Run the parser once; reuse results across tests in this class."""
        self.ext_to_instrs, self.instr_to_exts, self.overlaps = tier1_parser(
            MINIMAL_DATA
        )

    # ── Grouping ─────────────────────────────────────────────────────────────

    def test_groups_instructions_by_extension(self):
        assert "rv_i" in self.ext_to_instrs
        assert "add" in self.ext_to_instrs["rv_i"]
        assert "sub" in self.ext_to_instrs["rv_i"]

    def test_each_extension_has_correct_count(self):
        # rv_i: add, addw, sub  → 3
        assert len(self.ext_to_instrs["rv_i"]) == 3
        # rv_m: mul → 1
        assert len(self.ext_to_instrs["rv_m"]) == 1

    def test_instr_to_exts_mapping(self):
        assert self.instr_to_exts["add"] == ["rv_i"]
        assert set(self.instr_to_exts["addw"]) == {"rv_i", "rv64_i"}

    # ── Multi-extension overlap ───────────────────────────────────────────────

    def test_overlap_count(self):
        # addw and sh1add each belong to >1 extension
        assert len(self.overlaps) == 2

    def test_overlap_mnemonic_correct(self):
        overlap_mnemonics = {m for m, _ in self.overlaps}
        assert "addw" in overlap_mnemonics
        assert "sh1add" in overlap_mnemonics

    def test_single_extension_not_in_overlaps(self):
        overlap_mnemonics = {m for m, _ in self.overlaps}
        assert "add" not in overlap_mnemonics
        assert "mul" not in overlap_mnemonics

    # ── Edge cases ───────────────────────────────────────────────────────────

    def test_empty_data(self):
        ext_map, instr_map, overlaps = tier1_parser({})
        assert ext_map == {}
        assert instr_map == {}
        assert overlaps == []

    def test_instruction_with_no_extension_field(self):
        data = {"nop": {}}   # no "extension" key at all
        ext_map, instr_map, overlaps = tier1_parser(data)
        assert instr_map["nop"] == []
        assert overlaps == []

    def test_example_mnemonic_exists(self):
        for ext, instrs in self.ext_to_instrs.items():
            assert len(instrs) >= 1, f"Extension {ext!r} has no instructions"


# ─────────────────────────────────────────────────────────────────────────────
# Tests for load_instr_dict
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadInstrDict:

    def test_loads_real_file(self):
        """Verify that the real instr_dict.json loads and has expected shape."""
        path = os.path.join(os.path.dirname(__file__), "..", "data", "instr_dict.json")
        if not os.path.exists(path):
            pytest.skip("data/instr_dict.json not present")

        data = load_instr_dict(path)
        assert isinstance(data, dict)
        assert len(data) > 0

        # Every entry should have an 'extension' list
        for mnemonic, info in data.items():
            assert "extension" in info, f"Missing 'extension' key for {mnemonic!r}"
            assert isinstance(info["extension"], list)

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_instr_dict("nonexistent_path/instr_dict.json")
