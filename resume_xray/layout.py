"""Column gutter detection and column-aware reading order (ALGORITHM.md §2.0, §2.3)."""

from resume_xray.models import Gutter, Line


def find_gutter(lines: list[Line], page_width: float, weights: dict) -> Gutter | None:
    """The widest vertical whitespace channel with a column of text on each side, if any."""
    boxes = [line.bbox for line in lines if line.bbox]
    if len(boxes) < 2:
        return None
    start, end = (page_width * f for f in weights["gutter_x_range"])
    limit = weights["gutter_max_coverage"] * len(boxes)
    text_height = max(b[3] for b in boxes) - min(b[1] for b in boxes)
    if text_height <= 0:
        return None

    def is_column(side) -> bool:
        return bool(side) and max(b[3] for b in side) - min(b[1] for b in side) >= weights["gutter_min_height"] * text_height

    def separates(run: Gutter) -> bool:
        left = [b for b in boxes if b[2] <= run.x0]
        right = [b for b in boxes if b[0] >= run.x1]
        return is_column(left) and is_column(right)

    runs: list[Gutter] = []
    run_start = None
    x = start
    while x <= end + 1:
        empty = x <= end and sum(1 for b in boxes if b[0] < x + 1 and b[2] > x) <= limit
        if empty and run_start is None:
            run_start = x
        elif not empty and run_start is not None:
            if x - run_start >= weights["gutter_min_width_pt"]:
                runs.append(Gutter(run_start, x))
            run_start = None
        x += 1
    valid = [run for run in runs if separates(run)]
    return max(valid, key=lambda g: g.x1 - g.x0, default=None)


def column_order(lines: list[Line], gutter: Gutter | None) -> str:
    """Text read column by column (see reading_order)."""
    return "\n".join(" ".join(line.text for line in row) for row in reading_order(lines, gutter))


def reading_order(lines: list[Line], gutter: Gutter | None) -> list[list[Line]]:
    """Visual rows in column-aware order. Lines crossing the gutter split the page into blocks;
    inside a block the left column is read before the right one, but only when both sides hold at
    least two rows. Otherwise (e.g. a contact row with items on both sides) the block is read row by
    row."""
    if gutter is None:
        return _rows(lines)
    rows: list[list[Line]] = []
    block: list[Line] = []
    for line in sorted(lines, key=lambda l: (l.row, l.bbox[0])):
        if line.bbox[0] < gutter.center < line.bbox[2]:
            rows += _block_rows(block, gutter) + [[line]]
            block = []
        else:
            block.append(line)
    return rows + _block_rows(block, gutter)


def _block_rows(lines: list[Line], gutter: Gutter) -> list[list[Line]]:
    left = [l for l in lines if l.bbox[2] <= gutter.center]
    right = [l for l in lines if l.bbox[0] >= gutter.center]
    if len({l.row for l in left}) < 2 or len({l.row for l in right}) < 2:
        return _rows(lines)
    return _rows(left) + _rows(right)


def _rows(lines: list[Line]) -> list[list[Line]]:
    rows: dict[int, list[Line]] = {}
    for line in lines:
        rows.setdefault(line.row, []).append(line)
    return [sorted(row, key=lambda l: l.bbox[0]) for _, row in sorted(rows.items())]
