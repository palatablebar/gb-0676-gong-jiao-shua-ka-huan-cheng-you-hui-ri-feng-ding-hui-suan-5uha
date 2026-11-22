"""Evidence text safety.

Uploaded CSV cells (card numbers, route names, notes and quarantine
descriptions) are untrusted.  Spreadsheet programs evaluate a cell whose
first non-space character is one of ``= + - @`` (and a cell whose first
character is a tab or carriage return) as a formula.  Such text is kept
verbatim in the intake records, but every export renders it with a leading
apostrophe so the file can be opened safely.  The original value is carried
alongside the rendered one in the archive, therefore nothing is lost and the
source line count is untouched.
"""

import base64

from app.config import COLUMNS
from app.reasons import TEXT_REASONS

# Fields that carry uploaded free text.  ``event_time`` and ``reported`` are
# parsed and validated separately, so a leading minus there is a number, not a
# formula.
TEXT_FIELDS = ("event_id", "card", "route", "result", "note", "reason", "detail", "status")
FIELD_LABELS = {
    "event_id": "事件",
    "card": "卡号",
    "route": "线路",
    "result": "刷卡状态",
    "note": "备注",
    "reason": "隔离代码",
    "detail": "隔离说明",
    "status": "结论",
}
_CONTROL = ("\t", "\r", "\n")
_FORMULA = ("=", "+", "-", "@")
FIELD_ORDER = {name: index for index, name in enumerate(TEXT_FIELDS)}


def classify(value):
    """Return the disposition code for a risky cell, or ``None``."""
    if not isinstance(value, str) or value == "":
        return None
    if value[0] in _CONTROL:
        return "CONTROL_PREFIX"
    probe = value.lstrip(" \t\r\n")
    if probe and probe[0] in _FORMULA:
        return "FORMULA_PREFIX"
    return None


def render(value):
    """Return the value that is safe to put in a spreadsheet cell."""
    if classify(value):
        # An apostrophe makes spreadsheet software treat the rest as text.
        return "'" + value
    return value


def encode_original(value):
    """Exact original text, base64 and marked so it is never a formula."""
    return "base64:" + base64.b64encode(value.encode("utf-8")).decode("ascii")


def summary(findings):
    """Flat, formula-free rendering of all risky cells in one record."""
    return " ; ".join(f'{item["field_label"]}={item["rendered"]}' for item in findings)


def _uploaded(row, field):
    """Return the uploaded cell text when the raw record is available."""
    raw = row.get("_raw")
    if isinstance(raw, list) and field in COLUMNS:
        index = COLUMNS.index(field)
        if index < len(raw):
            return raw[index]
    return row.get(field)


def findings(row):
    """Return one finding per risky field in a row (parsed or raw CSV cells)."""
    values = []
    for field in TEXT_FIELDS:
        value = _uploaded(row, field)
        if isinstance(value, str):
            values.append((field, value))
    result = []
    seen = set()
    for field, value in values:
        code = classify(value)
        if not code:
            continue
        marker = (field, value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append({
            "line": _first_line(row),
            "field": field,
            "field_label": FIELD_LABELS.get(field, field),
            "original": value,
            "rendered": render(value),
            "code": code,
            "reason": TEXT_REASONS[code],
        })
    result.sort(key=lambda item: (FIELD_ORDER.get(item["field"], 99), item["original"]))
    return result


def _lines(row):
    value = row.get("_sources")
    if isinstance(value, list) and value:
        return [x for x in value if isinstance(x, int)]
    line = row.get("_line")
    return [line] if isinstance(line, int) else []


def _first_line(row):
    lines = _lines(row)
    return lines[0] if lines else 0


