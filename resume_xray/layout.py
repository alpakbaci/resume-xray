"""Column gutter detection and column-aware reading order (ALGORITHM.md §2.0, §2.3)."""

from resume_xray.models import Gutter, Line


def find_gutter(lines: list[Line], page_width: float, weights: dict) -> Gutter | None:
    """The widest vertical whitespace channel that separates two columns, if any."""
    boxes = [line.bbox for line in lines if line.bbox]
    if len(boxes) < 2:
        return None
    start, end = (page_width * f for f in weights["gutter_x_range"])
    limit = weights["gutter_max_coverage"] * len(boxes)

    best: Gutter | None = None
    run_start = None
    x = start
    while x <= end + 1:
        empty = x <= end and sum(1 for b in boxes if b[0] < x + 1 and b[2] > x) <= limit
        if empty and run_start is None:
            run_start = x
        elif not empty and run_start is not None:
            if x - run_start >= weights["gutter_min_width_pt"] and (
                best is None or x - run_start > best.x1 - best.x0
            ):
                best = Gutter(run_start, x)
            run_start = None
        x += 1
    if best is None:
        return None

    left = [b for b in boxes if b[2] <= best.x0]
    right = [b for b in boxes if b[0] >= best.x1]
    text_height = max(b[3] for b in boxes) - min(b[1] for b in boxes)
    if not left or not right or text_height <= 0:
        return None
    for side in (left, right):
        if (max(b[3] for b in side) - min(b[1] for b in side)) < weights["gutter_min_height"] * text_height:
            return None
    return best


def column_order(lines: list[Line], gutter: Gutter | None) -> str:
    """Text read column by column. Lines crossing the gutter split the page into blocks; inside a
    block the left column is read before the right one, but only when both sides hold at least two
    rows. Otherwise (e.g. a contact row with items on both sides) the block is read row by row."""
    if gutter is None:
        return _join_rows(lines)
    out: list[str] = []
    block: list[Line] = []
    for line in sorted(lines, key=lambda l: (l.row, l.bbox[0])):
        if line.bbox[0] < gutter.center < line.bbox[2]:
            out += [_read_block(block, gutter), line.text]
            block = []
        else:
            block.append(line)
    out.append(_read_block(block, gutter))
    return "\n".join(part for part in out if part)


def _read_block(lines: list[Line], gutter: Gutter) -> str:
    left = [l for l in lines if l.bbox[2] <= gutter.center]
    right = [l for l in lines if l.bbox[0] >= gutter.center]
    if len({l.row for l in left}) < 2 or len({l.row for l in right}) < 2:
        return _join_rows(lines)
    return "\n".join(part for part in (_join_rows(left), _join_rows(right)) if part)


def _join_rows(lines: list[Line]) -> str:
    rows: dict[int, list[Line]] = {}
    for line in lines:
        rows.setdefault(line.row, []).append(line)
    return "\n".join(
        " ".join(l.text for l in sorted(row, key=lambda l: l.bbox[0])) for _, row in sorted(rows.items())
    )
