"""Merge a list of skills into resume_xray/data/skills.toml.

    python tools/merge_skills.py new.toml "Section title"            # report only
    python tools/merge_skills.py new.toml "Section title" --write    # also apply

The input uses the dictionary's own format (`key = ["Wording", ...]`). For every entry:

- A wording that is already in the dictionary (same matching key) means the entry is that
  existing skill: its other wordings are added to the existing entry instead of making a new one.
- An entry whose wordings belong to two different existing skills would merge them, and a wording
  that stems like another skill's wording would make jobs ambiguous: both are reported and left out.
- Everything else becomes a new entry under the given section title.

Nothing is decided silently; the report lists every action.
"""

import re
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resume_xray.match import analyze  # noqa: E402

DICTIONARY = Path(__file__).resolve().parents[1] / "resume_xray" / "data" / "skills.toml"


def keys(wording: str) -> tuple[str, str]:
    tokens = analyze(wording, "en")
    return " ".join(t.surface for t in tokens), " ".join(t.stem for t in tokens)


def main(args: list[str]) -> int:
    source, section, write = Path(args[0]), args[1], "--write" in args
    new = tomllib.loads(source.read_text(encoding="utf-8"))
    current = tomllib.loads(DICTIONARY.read_text(encoding="utf-8"))
    by_surface = {keys(w)[0]: k for k, ws in current.items() for w in ws}
    by_stem = {keys(w)[1]: k for k, ws in current.items() for w in ws}

    extend: dict[str, list[str]] = {}
    added: dict[str, list[str]] = {}
    rejected: list[str] = []
    for key, wordings in new.items():
        owners = {by_surface[keys(w)[0]] for w in wordings if keys(w)[0] in by_surface}
        if len(owners) > 1:
            rejected.append(f"{key}: would merge existing skills {sorted(owners)}")
            continue
        target = owners.pop() if owners else None
        fresh = [w for w in wordings if keys(w)[0] not in by_surface]
        clashes = [w for w in fresh if keys(w)[1] in by_stem and by_stem[keys(w)[1]] != target]
        if clashes:
            rejected.append(f"{key}: {clashes} stem like {sorted({by_stem[keys(w)[1]] for w in clashes})}")
            continue
        if not fresh:
            continue
        name = target or (key if key not in current else f"{key}_2")
        (extend if target else added)[name] = fresh
        for w in fresh:
            by_surface[keys(w)[0]] = name
            by_stem[keys(w)[1]] = name

    for name, wordings in extend.items():
        print(f"extend {name}: + {wordings}")
    for name, wordings in added.items():
        print(f"new    {name}: {wordings}")
    for line in rejected:
        print(f"skip   {line}")
    print(f"\n{len(added)} new, {len(extend)} extended, {len(rejected)} skipped, "
          f"{len(new) - len(added) - len(extend) - len(rejected)} already complete")

    if write:
        text = DICTIONARY.read_text(encoding="utf-8")
        for name, wordings in extend.items():
            line = re.search(rf"^{re.escape(name)} = \[(.*)\]$", text, re.M)
            text = text[: line.end(1)] + ", " + ", ".join(f'"{w}"' for w in wordings) + text[line.end(1):]
        if added:
            text = text.rstrip("\n") + f"\n\n# {section}\n" + "".join(
                f"{name} = [{', '.join(chr(34) + w + chr(34) for w in ws)}]\n" for name, ws in added.items()
            )
        DICTIONARY.write_text(text, encoding="utf-8")
        print("written to", DICTIONARY)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
