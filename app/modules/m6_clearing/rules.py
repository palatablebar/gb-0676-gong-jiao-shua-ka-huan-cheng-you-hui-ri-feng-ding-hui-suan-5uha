from decimal import Decimal
from app.reasons import sources
from app.errors import DomainError
from app.lineage import merge
def evaluate(rows,context):
    intake=context.get("intake")
    bad=context.get("quarantine",[])
    accepted=set(x for row in rows for x in sources(row))
    rejected=set(x for row in bad for x in sources(row))
    if accepted & rejected: raise DomainError("LINEAGE_OVERLAP","同一来源行被重复裁决")
    ledger=context.get("intake_ledger")
    lineage,line_metrics=(merge(ledger,accepted,rejected,include_raw=False) if ledger is not None else (context.get("lineage",[]),context.get("line_metrics") or {}))
    m={"accepted_inputs":len(accepted),"quarantine_inputs":len(rejected),"output_records":len(rows),"source_lines":line_metrics.get("source_lines",0),"unplaced":line_metrics.get("unplaced",0),"lineage_complete":line_metrics.get("lineage_complete",False)}
    if intake:
        excluded=intake["duplicate"]+intake["blank"]+intake["repeated_headers"]
        m.update(input=intake["input"],excluded=excluded,balanced=intake["input"]==len(accepted)+len(rejected)+excluded)
    else:m.update(input=len(accepted)+len(rejected),excluded=0,balanced=True)
    if intake and m["balanced"] and ledger is not None and not m["lineage_complete"]:
        raise DomainError("LINEAGE_GAP","来源行未能逐行着落")
    output=[]
    for row in rows:
        expected=Decimal(str(row.get("expected","0")));reported=Decimal(str(row.get("reported","0")))
        output.append({**row,"difference":str(expected-reported),"status":"通过" if expected==reported else "差异"})
    m.update(expected_total=str(sum((Decimal(str(r.get("expected","0"))) for r in rows),Decimal(0))),reported_total=str(sum((Decimal(str(r.get("reported","0"))) for r in rows),Decimal(0))),differences=sum(r["status"]=="差异" for r in output))
    return {"rows":output,"quarantine":[],"lineage":lineage,"line_metrics":line_metrics,"metrics":m}
