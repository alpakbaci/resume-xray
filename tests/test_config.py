"""weights.toml and ALGORITHM.md must name the same constants with the same values."""

import re
import tomllib
from pathlib import Path

from ats_checker.config import load_weights

ALGORITHM = Path(__file__).resolve().parents[1] / "ALGORITHM.md"
# Matches inline code like `garbled_warn = 0.02` or `gutter_x_range = [0.2, 0.8]`.
CONSTANT = re.compile(r"`([a-z_]+) = ([^`]+)`")


def documented_constants() -> dict[str, object]:
    text = ALGORITHM.read_text(encoding="utf-8")
    return {name: tomllib.loads(f"v = {value}")["v"] for name, value in CONSTANT.findall(text)}


def configured_constants() -> dict[str, object]:
    return {name: value for section in load_weights().values() for name, value in section.items()}


def test_algorithm_doc_names_constants():
    assert documented_constants(), "no constants found in ALGORITHM.md"


def test_weights_match_algorithm_doc():
    assert configured_constants() == documented_constants()
