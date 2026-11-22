"""Source-line lineage.

Every physical line of an uploaded CSV must end up in exactly one
disposition before the batch may be sealed:

* ``accepted``   – the record survived every stage;
* ``quarantine`` – the record was isolated with a reason;
* ``duplicate``  – identical repeat of an earlier business key;
* ``blank``      – empty line;
* ``repeated_header`` – a repeated header line inside the file;
* ``unplaced``   – no stage accounts for this line (a lineage gap).

Intake (M1) numbers the lines from the CSV parser, where a record ending in a
quoted newline spans several physical lines.  ``start``..``end`` therefore
describes the physical span of one record; the spans of a well-formed file
tile ``2 .. physical_lines`` without gaps or overlaps.
"""

from app.errors import DomainError

EXCLUDED = ("duplicate", "blank", "repeated_header")


def merge(intake_ledger, accepted_lines, rejected_lines, include_raw=True):
    """Return ``(lineage, metrics)`` for the current stage outcomes."""
    accepted = set(accepted_lines)
    rejected = set(rejected_lines)
    overlap = accepted & rejected
    if overlap:
        raise DomainError("LINEAGE_OVERLAP", "同一来源行被重复裁决")

    lineage = []
    if intake_ledger:
        placed = set()
        for entry in intake_ledger:
            line = entry["line"]
            if line in placed:
                raise DomainError("LINEAGE_DUPLICATE", "来源行编号重复")
            placed.add(line)
            disposition = entry["disposition"]
            if line in rejected:
                disposition = "quarantine"
            elif line in accepted:
                disposition = "accepted"
            elif disposition not in EXCLUDED:
                disposition = "unplaced"
            item = {
                "line": line,
                "start": entry.get("start", line),
                "end": entry.get("end", line),
                "disposition": disposition,
            }
            if include_raw and "raw" in entry and disposition != "accepted":
                item["raw"] = entry["raw"]
            lineage.append(item)
        for line in sorted((accepted | rejected) - placed):
            lineage.append({"line": line, "start": line, "end": line, "disposition": "unplaced"})
    else:
        # No intake ledger: report what this stage knows, but never claim
        # completeness – sealing requires the ledger.
        for line in sorted(accepted):
            lineage.append({"line": line, "start": line, "end": line, "disposition": "accepted"})
        for line in sorted(rejected):
            lineage.append({"line": line, "start": line, "end": line, "disposition": "quarantine"})

    lineage.sort(key=lambda item: (item["start"], item["line"]))
    before=sum(item["disposition"]=="unplaced" for item in lineage)
    gaps=_gaps(lineage)
    missing=sum(end-start+1 for start,end in gaps)
    exhausted=sum(item["disposition"] in EXCLUDED for item in lineage)
    metrics={
        "source_lines":len(lineage)+missing,
        "unplaced":before+missing,
        "gaps":gaps,
        "excluded_lines":exhausted,
        "accepted_lines":sum(item["disposition"]=="accepted" for item in lineage),
        "quarantine_lines":sum(item["disposition"]=="quarantine" for item in lineage),
        "lineage_complete":bool(intake_ledger) and before==0 and not gaps,
    }
    if gaps:
        for start,end in gaps:
            for line in range(start,end+1):
                lineage.append({"line":line,"start":line,"end":line,"disposition":"unplaced"})
        lineage.sort(key=lambda item: (item["start"],item["line"]))
    return lineage,metrics


def _gaps(lineage):
    """Physical lines covered by no record, assuming a contiguous file."""
    if not lineage:
        return []
    ordered = sorted((item["start"], item["end"]) for item in lineage)
    gaps = []
    cursor = 2  # line 1 is the header
    for start, end in ordered:
        if start > cursor:
            gaps.append((cursor, start - 1))
        cursor = max(cursor, end + 1)
    return gaps


def placement(lineage):
    """Return ``(unplaced, complete)`` for a stored lineage."""
    if not lineage:
        return None, False
    unplaced = [item for item in lineage if item.get("disposition") == "unplaced"]
    complete = not unplaced and bool(lineage)
    return unplaced, complete
