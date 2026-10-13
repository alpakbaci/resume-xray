"""Loads the thresholds and weights defined in weights.toml."""

import tomllib
from functools import cache
from importlib.resources import files
from typing import Any


@cache
def load_weights() -> dict[str, dict[str, Any]]:
    """Return weights.toml as {section: {name: value}}."""
    text = files(__package__).joinpath("weights.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)
