"""SVG geometry for the console dashboard charts.

Views compute the series; these helpers turn them into coordinates the template can
draw without arithmetic. Every chart shares one plot box (viewBox 500x200) so the
cards line up, and an empty series renders as an empty state, never a flat line that
reads as "zero happened".
"""

import math
from datetime import date, timedelta

WIDTH, LEFT, RIGHT = 500, 40, 480
TOP, BOTTOM = 20, 160
LABELS = 6
DONUT_RADIUS = 38
DONUT_CIRCUMFERENCE = 2 * math.pi * DONUT_RADIUS
PALETTE = ["blue", "green", "amber", "purple", "cyan", "orange", "teal", "red"]


def granularity(days):
    return "day" if days <= 31 else "week" if days <= 120 else "month"


def bucket_of(day, unit):
    if unit == "week":
        return day - timedelta(days=day.weekday())
    if unit == "month":
        return day.replace(day=1)
    return day


def buckets(start, end, unit):
    """Every bucket from start to end inclusive, so quiet days show as zero rather than
    being skipped and silently stretching the axis."""
    current, out = bucket_of(start, unit), []
    while current <= end:
        out.append(current)
        if unit == "month":
            current = date(current.year + current.month // 12, current.month % 12 + 1, 1)
        else:
            current += timedelta(days=7 if unit == "week" else 1)
    return out


def label(day, unit):
    return f"{day:%b %Y}" if unit == "month" else f"{day:%b} {day.day}"


def nice_ceiling(value):
    """The smallest 1/2/5 x 10^k step that covers value in four gridlines."""
    if value <= 0:
        return 4, 1
    raw = value / 4
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 5, 10) if m * magnitude >= raw)
    if step < 1:
        step = 1
    return step * 4, step


def _y(value, ceiling):
    return round(BOTTOM - (value / ceiling) * (BOTTOM - TOP), 1)


def _axis(ceiling, step, money=False):
    ticks = []
    for index in range(5):
        value = step * index
        text = f"${value:,.0f}" if money else f"{value:,.0f}"
        ticks.append({"y": _y(value, ceiling), "text": text})
    return ticks


def _x_labels(xs, texts):
    if not xs:
        return []
    every = max(1, math.ceil(len(xs) / LABELS))
    picked = list(range(0, len(xs), every))
    if picked[-1] != len(xs) - 1 and len(xs) - 1 - picked[-1] >= every / 2:
        picked.append(len(xs) - 1)
    return [{"x": xs[i], "text": texts[i]} for i in picked]


def _slots(count):
    if count == 1:
        return [(LEFT + RIGHT) / 2]
    span = (RIGHT - LEFT) / (count - 1)
    return [round(LEFT + i * span, 1) for i in range(count)]


def line_chart(points, *, money=False):
    """points: [(label, value)]. Returns path data, dots with hover titles and axes."""
    values = [float(value) for _, value in points]  # money arrives as Decimal
    if not points or not any(values):
        return {"empty": True, "total": 0}
    ceiling, step = nice_ceiling(max(values))
    xs = _slots(len(points))
    coords = [(x, _y(value, ceiling)) for x, value in zip(xs, values, strict=True)]
    line = "M " + " L ".join(f"{x} {y}" for x, y in coords)
    return {
        "empty": False,
        "total": sum(value for _, value in points),  # keep ints as ints for display
        "line": line,
        "area": f"{line} L {coords[-1][0]} {BOTTOM} L {coords[0][0]} {BOTTOM} Z",
        "dots": [
            {
                "x": x,
                "y": y,
                "title": f"{text}: {f'${value:,.2f}' if money else f'{value:,}'}",
            }
            for (x, y), (text, value) in zip(coords, points, strict=True)
        ],
        "y_ticks": _axis(ceiling, step, money),
        "x_labels": _x_labels(xs, [text for text, _ in points]),
    }


def bar_chart(points):
    """points: [(label, first, second)] drawn as paired bars (first left, second right)."""
    peak = max((max(a, b) for _, a, b in points), default=0)
    if not peak:
        return {"empty": True, "totals": [0, 0]}
    ceiling, step = nice_ceiling(peak)
    slot = (RIGHT - LEFT) / len(points)
    width = round(max(1.5, min(9, slot * 0.36)), 1)
    bars, centres = [], []
    for index, (text, first, second) in enumerate(points):
        centre = round(LEFT + slot * (index + 0.5), 1)
        centres.append(centre)
        for offset, value, series in ((-width, first, 0), (0, second, 1)):
            if value:
                y = _y(value, ceiling)
                bars.append(
                    {
                        "x": round(centre + offset, 1),
                        "y": y,
                        "width": width,
                        "height": round(BOTTOM - y, 1),
                        "series": series,
                        "title": f"{text}: {value:,}",
                    }
                )
    return {
        "empty": False,
        "totals": [sum(a for _, a, _ in points), sum(b for _, _, b in points)],
        "bars": bars,
        "y_ticks": _axis(ceiling, step),
        "x_labels": _x_labels(centres, [text for text, _, _ in points]),
    }


def donut(rows, *, limit=8):
    """rows: [(name, count)], largest first. Anything past `limit` folds into "Other"
    so the legend stays readable; percentages always add back to the real total."""
    rows = [(name, count) for name, count in rows if count]
    total = sum(count for _, count in rows)
    if not total:
        return {"empty": True, "total": 0}
    if len(rows) > limit:
        rows = rows[: limit - 1] + [("Other", sum(count for _, count in rows[limit - 1 :]))]
    segments, travelled = [], 0.0
    for index, (name, count) in enumerate(rows):
        length = DONUT_CIRCUMFERENCE * count / total
        segments.append(
            {
                "name": name,
                "count": count,
                "percent": f"{count * 100 / total:.0f}%" if count * 100 / total >= 1 else "<1%",
                "colour": "text-faint" if name == "Other" else PALETTE[index % len(PALETTE)],
                "dash": f"{length:.2f} {DONUT_CIRCUMFERENCE - length:.2f}",
                "offset": f"{-travelled:.2f}",
            }
        )
        travelled += length
    return {"empty": False, "total": total, "segments": segments}
