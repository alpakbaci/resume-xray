"""Column gutter detection and column-aware reading order (ALGORITHM.md §2.0, §2.3)."""

from resume_xray.models import Gutter, Line


def find_gutter(lines: list[Line], page_width: float, weights: dict) -> Gutter | None:
    """The widest empty vertical channel between two columns, if any (ALGORITHM.md §2.3).

    A channel is a run of 1 pt slices, at least gutter_min_width_pt wide, in which one vertical
    stretch of at least gutter_min_height of the text height is crossed by no line. It separates
    two columns when each side holds a column of left-aligned text within that stretch."""
    placed = [line for line in lines if line.bbox]
    if len(placed) < 4:
        return None
    top = min(l.bbox[1] for l in placed)
    bottom = max(l.bbox[3] for l in placed)
    need = weights["gutter_min_height"] * (bottom - top)
    if need <= 0:
        return None
    start, end = (page_width * f for f in weights["gutter_x_range"])

    def free(x: float) -> list[tuple[float, float]]:
        covered = sorted((l.bbox[1], l.bbox[3]) for l in placed if l.bbox[0] < x + 1 and l.bbox[2] > x)
        gaps, cursor = [], top
        for y0, y1 in covered:
            if y0 > cursor:
                gaps.append((cursor, y0))
            cursor = max(cursor, y1)
        if bottom > cursor:
            gaps.append((cursor, bottom))
        return [g for g in gaps if g[1] - g[0] >= need]

    def common(a, b):
        out = [(max(a0, b0), min(a1, b1)) for a0, a1 in a for b0, b1 in b]
        return [g for g in out if g[1] - g[0] >= need]

    def is_column(side: list[Line]) -> bool:
        """Running text: at least three lines stacked like a paragraph, each starting less than its
        own height below the previous one. Right-aligned dates on a single-column page are single
        lines spread between the bullets they head, so they never form such a stack."""
        stack = sorted(side, key=lambda l: l.bbox[1])
        run = 1
        for above, below in zip(stack, stack[1:]):
            height = above.bbox[3] - above.bbox[1]
            run = run + 1 if below.bbox[1] - above.bbox[3] < height else 1
            if run >= 3:
                return True
        return False

    def separates(g: Gutter) -> bool:
        # A column's text may run above or below the empty stretch (a sidebar's name, a heading),
        # so every line on that side of the channel counts.
        return is_column([l for l in placed if side(l, g) == "left"]) and is_column([l for l in placed if side(l, g) == "right"])

    candidates: list[Gutter] = []
    run_x0, run_free = None, []
    x = start
    while x <= end + 1:
        here = free(x) if x <= end else []
        if run_x0 is not None:
            kept = common(run_free, here)
            if kept != run_free and x - run_x0 >= weights["gutter_min_width_pt"]:
                # The empty stretch shrinks here: keep the taller, narrower channel found so far.
                candidates += [Gutter(run_x0, x, y0, y1) for y0, y1 in run_free]
            if kept:
                run_free = kept
            else:
                run_x0 = None
        if run_x0 is None and here:
            run_x0, run_free = x, here
        x += 1
    valid = [g for g in candidates if separates(g)]
    return max(valid, key=lambda g: (g.x1 - g.x0, g.y1 - g.y0), default=None)


def side(line: Line, gutter: Gutter) -> str | None:
    """"left" or "right" of the gutter, or None for a line that spans it from one column into the
    other. A line reaching into the gutter without crossing it still belongs to its column. The gutter's vertical
    stretch is only used to find it: a sidebar's name or a column's first heading may sit above the
    empty stretch and still belong to its column."""
    if line.bbox[2] <= gutter.x1:
        return "left"
    if line.bbox[0] >= gutter.x0:
        return "right"
    return None


def column_order(lines: list[Line], gutter: Gutter | None) -> str:
    """Text read column by column (see reading_order)."""
    return "\n".join(" ".join(line.text for line in row) for row in reading_order(lines, gutter))


def reading_order(lines: list[Line], gutter: Gutter | None) -> list[list[Line]]:
    """Visual rows in column-aware order. Lines outside the columns (see side) split the page into blocks;
    inside a block the left column is read before the right one, but only when both sides hold at
    least two rows. Otherwise (e.g. a contact row with items on both sides) the block is read row by
    row."""
    if gutter is None:
        return _rows(lines)
    rows: list[list[Line]] = []
    block: list[Line] = []
    for line in sorted(lines, key=lambda l: (l.row, l.bbox[0])):
        if side(line, gutter) is None:
            rows += _block_rows(block, gutter) + [[line]]
            block = []
        else:
            block.append(line)
    return rows + _block_rows(block, gutter)


def _block_rows(lines: list[Line], gutter: Gutter) -> list[list[Line]]:
    left = [l for l in lines if side(l, gutter) == "left"]
    right = [l for l in lines if side(l, gutter) == "right"]
    if len({l.row for l in left}) < 2 or len({l.row for l in right}) < 2:
        return _rows(lines)
    return _rows(left) + _rows(right)


def _rows(lines: list[Line]) -> list[list[Line]]:
    rows: dict[int, list[Line]] = {}
    for line in lines:
        rows.setdefault(line.row, []).append(line)
    return [sorted(row, key=lambda l: l.bbox[0]) for _, row in sorted(rows.items())]
