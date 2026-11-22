"""Single evidence archive per batch.

The archive has exactly one row per physical source record, so opening and
re-counting the file never changes the source line count.  Risky cells
(formula-like text) are stored so both goals hold at once:

* ``original_b64`` – a ``base64:`` document holding the exact uploaded text of
  every risky field, byte for byte, so the original can always be recovered;
* ``rendered`` – the apostrophe-prefixed text that is safe to display in a
  spreadsheet.

``evidence`` carries the full record JSON.  Every generated cell starts with a
character that spreadsheet software never treats as a formula, so the file can
be opened without executing uploaded text.
"""

import csv,io,json,hashlib

from app.errors import DomainError
from app.reasons import REASONS
from app.lineage import placement
from app import textsafe

HEADER=["run_id","input_sha256","rule_version","kind","source_line","source_span","disposition","text_count","text_codes","original_b64","rendered","evidence"]
KIND_LABELS={"accepted":"采纳","quarantine":"隔离","duplicate":"重复行","blank":"空白行","repeated_header":"分段表头","unplaced":"未着落"}


def _evidence(row):
    return json.dumps(row,ensure_ascii=False,sort_keys=True,default=str,separators=(",",":"))


def _span(item):
    start=item.get("start",item["line"]);end=item.get("end",item["line"])
    if not isinstance(start,int) or not isinstance(end,int): return ""
    return str(start) if start==end else f"{start}-{end}"


def _disposition(kind,row):
    if kind=="quarantine":
        code=row.get("reason") or ""
        detail=row.get("detail") or ""
        label=REASONS.get(code,code)
        text=label if detail in ("",label) else f"{label}：{detail}"
        text=f"{code} {text}".strip()
    else:
        text=KIND_LABELS.get(kind,kind)
    # Never let an uploaded value (or a description built from it) become a formula.
    return textsafe.render(text)


def archive_entries(run):
    """Return ``(lineage_item, kind, row)`` in source-line order, or refuse."""
    stages=run.get("stages") or []
    if not stages: raise DomainError("NOT_SEALABLE","批次缺少阶段结果",409)
    last=stages[-1]
    lineage=last.get("lineage")
    unplaced,complete=placement(lineage)
    if not lineage or not complete:
        raise DomainError("LINEAGE_GAP","来源行尚未逐行着落，不能封存",409)
    meta={"run_id":run["run_id"],"input_sha256":run["manifest"]["input_sha256"],"rule_version":run["manifest"]["rule_version"]}
    known={}
    for row in last.get("rows",[]): known.setdefault(row.get("_line"),("accepted",row))
    for row in last.get("cumulative_quarantine",[]): known.setdefault(row.get("_line"),("quarantine",row))
    entries=[]
    for item in lineage:
        line=item["line"]
        kind,row=known.get(line,(item.get("disposition","unplaced"),{"_line":line}))
        row=dict(row);row["_line"]=line
        if "raw" in item and not row.get("_raw"): row["_raw"]=item["raw"]
        entries.append((item,kind,row))
    return entries,meta


def _record(item,kind,row,meta):
    findings=textsafe.findings(row)
    originals=[{"field":f["field"],"original":f["original"]} for f in findings]
    original_json=json.dumps(originals,ensure_ascii=False,sort_keys=True,separators=(",",":")) if findings else ""
    return [meta["run_id"],meta["input_sha256"],meta["rule_version"],kind,
            item["line"],_span(item),_disposition(kind,row),
            len(findings),
            "; ".join(f'{f["field"]}:{f["code"]}' for f in findings),
            textsafe.encode_original(original_json) if original_json else "",
            textsafe.summary(findings),
            _evidence(row)]


def build_archive(run):
    """Return ``(csv_text, sha256)`` for the single safe evidence export."""
    entries,meta=archive_entries(run)
    stream=io.StringIO(newline="");writer=csv.writer(stream)
    writer.writerow(HEADER)
    for item,kind,row in entries:
        writer.writerow(_record(item,kind,row,meta))
    content="﻿"+stream.getvalue()
    return content,hashlib.sha256(content.encode("utf-8")).hexdigest()
