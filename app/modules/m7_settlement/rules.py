import hashlib,json
from decimal import Decimal
from app.errors import DomainError
from app.reasons import sources
from app.lineage import placement
def evaluate(rows,context):
    stages=[v for v in context.values() if isinstance(v,dict) and "metrics" in v]
    balances=[s["metrics"]["balanced"] for s in stages if "balanced" in s["metrics"]]
    if balances and not all(balances): raise DomainError("UNBALANCED","来源行未对平，不能归档")
    lineage=context.get("lineage")
    complete=True
    sourced="intake" in context or any("balanced" in s["metrics"] for s in stages)
    if lineage is not None:
        unplaced,complete=placement(lineage)
        if unplaced is not None and not complete:
            raise DomainError("LINEAGE_GAP","来源行尚未逐行着落，不能封存")
        if not lineage:
            raise DomainError("LINEAGE_GAP","缺少来源行台账，不能封存")
    elif sourced:
        raise DomainError("LINEAGE_GAP","缺少来源行台账，不能封存")
    ids=[str(r.get("event_id",r.get("_line",""))) for r in rows]
    if len(ids)!=len(set(ids)): raise DomainError("ARCHIVE_DUPLICATE","归档业务键重复")
    encoded=json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode()
    return {"rows":rows,"quarantine":[],"lineage":lineage or [],"metrics":{"records":len(rows),"source_lines":len(set(x for row in rows for x in sources(row))),"ledger_lines":len(lineage or []),"lineage_complete":complete,"sha256":hashlib.sha256(encoded).hexdigest(),"ready":True,"differences":sum(r.get("status")=="差异" for r in rows)}}
