import base64,csv,io,json
import pytest
from app import store
from app.archive import HEADER,build_archive
from app.errors import DomainError
from app.lineage import merge
from app.modules.m1_taps.rules import evaluate as intake
from app.modules.m6_clearing.rules import evaluate as clearing
from app.modules.m7_settlement.rules import evaluate as settlement
from app.pipeline import calculate,execute,load_sample
from app import textsafe

RISKY=("event_id,card,route,event_time,result,reported,note\r\n"
"0001,=0001,1路,2026-11-16T08:00:00+08:00,success,2.50,\"@早班\n换乘\"\r\n"
"0002,0002,02,2026-11-16T08:15:00+08:00,success,2.50,+换乘站\r\n").encode()

def archive_rows(run):
    body,digest=build_archive(run)
    return list(csv.reader(io.StringIO(body.lstrip("﻿")))),digest

def test_formula_like_cells_are_classified():
    for value in ["=1+2","+02","-1","@SUM(A1)"," =1+1","\t=1"]:
        assert textsafe.classify(value)=="FORMULA_PREFIX" or textsafe.classify(value)=="CONTROL_PREFIX"
        assert textsafe.render(value).startswith("'")
    for value in ["0010","1路","常规","—已扣"]:
        assert textsafe.classify(value) is None and textsafe.render(value)==value

def test_intake_keeps_formula_text_verbatim():
    r=intake(RISKY)
    assert r["metrics"]["accepted"]==2 and r["quarantine"]==[]
    row=r["rows"][0]
    assert row["card"]=="=0001" and row["note"]=="@早班\n换乘"
    assert r["line_metrics"]["lineage_complete"] is True

def test_archive_renders_safe_and_recovers_original():
    rows,digest=archive_rows(calculate(RISKY))
    assert rows[0]==HEADER
    assert len(digest)==64
    risky=[r for r in rows[1:] if int(r[7])]
    assert risky
    for row in risky:
        assert row[9].startswith("base64:")
        originals=json.loads(base64.b64decode(row[9][len("base64:"):]).decode("utf-8"))
        assert len(originals)==int(row[7])
        assert any(item["original"] and item["original"][0] in "=+-@" for item in originals)
        assert row[10] and "='" in row[10]
    # No published cell begins with a formula trigger without the marker.
    for row in rows[1:]:
        for cell in row:
            assert not cell.startswith(("=","+","-","@","\t","\r"))

def test_archive_keeps_every_source_line():
    raw=("event_id,card,route,event_time,result,reported,note\r\n"
    "0001,0001,1路,2026-11-16T08:00:00+08:00,success,2.50,常规\r\n"
    "\r\n"
    "event_id,card,route,event_time,result,reported,note\r\n"
    "0001,0001,1路,2026-11-16T08:00:00+08:00,success,2.50,常规\r\n"
    "0009,0009,+99,2026-11-16T08:10:00+08:00,success,2.50,冲突\r\n").encode()
    run=calculate(raw)
    rows=archive_rows(run)[0]
    kinds={}
    for row in rows[1:]:
        kinds.setdefault(row[3],set()).add(int(row[4]))
    assert kinds["accepted"]=={2}
    assert kinds["blank"]=={3}
    assert kinds["repeated_header"]=={4}
    assert kinds["duplicate"]=={5}
    assert kinds["quarantine"]=={6}
    assert set(range(2,7))==set().union(*kinds.values())
    assert run["stages"][-1]["line_metrics"]["lineage_complete"] is True

def test_quoted_newline_span_recorded():
    run=calculate(RISKY)
    first=run["stages"][0]["lineage"][0]
    assert (first["start"],first["end"])==(2,3)

def test_rerun_does_not_add_records(sample):
    a=execute(sample);b=execute(sample)
    assert a["run_id"]==b["run_id"]
    assert len(store.history())==1

def test_publish_is_idempotent(client):
    p=client.post("/api/runs",json={"csv":RISKY.decode()}).get_json()
    url="/api/runs/"+p["run_id"]+"/archive"
    first=client.get(url);second=client.get(url)
    assert first.status_code==second.status_code==200
    assert first.data==second.data
    assert first.headers["X-Archive-Version"]==second.headers["X-Archive-Version"]=="1"
    assert first.headers["X-Archive-SHA256"]==second.headers["X-Archive-SHA256"]

def test_publish_failure_keeps_previous_archive(client,monkeypatch):
    p=client.post("/api/runs",json={"csv":RISKY.decode()}).get_json()
    url="/api/runs/"+p["run_id"]+"/archive"
    good=client.get(url)
    assert good.status_code==200
    import app.archive as archive_module
    monkeypatch.setattr(archive_module,"build_archive",lambda run:(_ for _ in ()).throw(DomainError("BROKEN","构建失败",500)))
    broken=client.get(url)
    assert broken.status_code==500
    stored=store.get_publication(p["run_id"])
    assert stored["body"]==good.data.decode("utf-8") and stored["archive_version"]==1

def test_unplaced_line_blocks_sealing():
    context={"lineage":[{"line":2,"start":2,"end":2,"disposition":"unplaced"}]}
    with pytest.raises(DomainError) as error:
        settlement([{"event_id":"1"}],context)
    assert error.value.code=="LINEAGE_GAP"

def test_missing_ledger_blocks_sealing():
    context={"intake":{"input":1,"duplicate":0,"blank":0,"repeated_headers":0}}
    with pytest.raises(DomainError) as error:
        settlement([{"event_id":"1"}],context)
    assert error.value.code=="LINEAGE_GAP"

def test_gap_is_detected_in_merge():
    ledger=[{"line":2,"start":2,"end":2,"disposition":"accepted"},{"line":5,"start":5,"end":5,"disposition":"accepted"}]
    lineage,metrics=merge(ledger,{2,5},{})
    assert metrics["gaps"]==[(3,4)]
    assert metrics["unplaced"]==2 and metrics["lineage_complete"] is False
    assert {item["line"] for item in lineage if item["disposition"]=="unplaced"}=={3,4}

def test_gap_in_physical_lines_is_counted():
    ledger=[{"line":2,"start":2,"end":2,"disposition":"accepted"},{"line":9,"start":9,"end":9,"disposition":"accepted"}]
    _,metrics=merge(ledger,{2,9},{})
    assert metrics["lineage_complete"] is False and metrics["unplaced"]==6

def test_clearing_refuses_unplaced():
    ledger=[{"line":2,"start":2,"end":2,"disposition":"accepted"},{"line":3,"start":3,"end":3,"disposition":"accepted"}]
    context={"intake":{"input":1,"duplicate":0,"blank":0,"repeated_headers":0},"intake_ledger":ledger,"quarantine":[]}
    with pytest.raises(DomainError) as error:
        clearing([{"_line":2,"event_id":"1"}],context)
    assert error.value.code=="LINEAGE_GAP"

def test_page_lists_original_rendered_reason(client):
    assert client.post("/api/runs",json={"csv":RISKY.decode()}).status_code==200
    page=client.get("/taps")
    assert page.status_code==200
    body=page.data.decode("utf-8")
    assert "来源行台账" in body
    assert "&#39;=0001" in body and "=0001" in body
    assert "公式样式文本" in body
    assert "来源行已逐行着落" in body

def test_archive_refuses_run_without_lineage(client):
    p=client.post("/api/runs",json={"csv":RISKY.decode()}).get_json()
    run=store.get(p["run_id"])
    for stage in run["stages"]:
        stage.pop("lineage",None)
        stage.pop("line_metrics",None)
    with store.connect() as db:
        db.execute("UPDATE runs SET payload=? WHERE id=?",(json.dumps(run,ensure_ascii=False),run["run_id"]))
    response=client.get("/api/runs/"+run["run_id"]+"/archive")
    assert response.status_code==409
    assert response.get_json()["code"]=="LINEAGE_GAP"
