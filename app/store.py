import sqlite3,json
from pathlib import Path
from datetime import datetime,timezone
from app.config import DATA_DIR
from app.errors import DomainError
def connect():
    DATA_DIR.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA_DIR/"records.db",timeout=20)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY,payload TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,decision TEXT NOT NULL DEFAULT '待复核')")
    db.execute("CREATE TABLE IF NOT EXISTS publications (run_id TEXT PRIMARY KEY,archive_version INTEGER NOT NULL,sha256 TEXT NOT NULL,body TEXT NOT NULL,published_at TEXT NOT NULL)")
    return db
def save(run_id,payload):
    # Same source + rule version yields the same id: reuse the batch row, but
    # refresh its payload so a re-run cannot leave an unsealable stale result.
    # Review state (version, decision) is deliberately left untouched.
    with connect() as db:
        db.execute("INSERT INTO runs(id,payload) VALUES (?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",(run_id,json.dumps(payload,ensure_ascii=False)))
    return get(run_id)
def get(run_id):
    with connect() as db: row=db.execute("SELECT payload,version,decision FROM runs WHERE id=?",(run_id,)).fetchone()
    if not row: raise DomainError("NOT_FOUND","批次不存在",404)
    return {**json.loads(row[0]),"version":row[1],"decision":row[2]}
def latest():
    with connect() as db: row=db.execute("SELECT id FROM runs ORDER BY rowid DESC LIMIT 1").fetchone()
    return get(row[0]) if row else None
def history():
    with connect() as db: return [{"run_id":i,"version":v,"decision":d} for i,v,d in db.execute("SELECT id,version,decision FROM runs ORDER BY rowid DESC")]
def review(run_id,version,decision):
    if decision not in {"已复核","退回复核"}: raise DomainError("BAD_DECISION","复核状态无效")
    with connect() as db:
        cursor=db.execute("UPDATE runs SET version=version+1,decision=? WHERE id=? AND version=?",(decision,run_id,version))
        if cursor.rowcount!=1:
            if not db.execute("SELECT 1 FROM runs WHERE id=?",(run_id,)).fetchone(): raise DomainError("NOT_FOUND","批次不存在",404)
            raise DomainError("STALE_VERSION","版本已更新，请刷新",409)
    return get(run_id)
def get_publication(run_id):
    with connect() as db:
        row=db.execute("SELECT archive_version,sha256,body,published_at FROM publications WHERE run_id=?",(run_id,)).fetchone()
    if not row: return None
    return {"archive_version":row[0],"sha256":row[1],"body":row[2],"published_at":row[3]}
def publish(run_id,builder):
    """Build and store the single archive for a run.

    The builder runs before the transaction, so a build failure leaves any
    earlier publication untouched.  The write itself is one transaction: a
    failure rolls back and the previous archive remains readable.  An archive
    with identical content is reused instead of appending a new version.
    """
    run=get(run_id)
    body,digest=builder(run)
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT archive_version,sha256,body,published_at FROM publications WHERE run_id=?",(run_id,)).fetchone()
        if row and row[1]==digest: return {"archive_version":row[0],"sha256":row[1],"body":row[2],"published_at":row[3]}
        version=(row[0]+1) if row else 1
        published=datetime.now(timezone.utc).isoformat()
        db.execute("INSERT INTO publications(run_id,archive_version,sha256,body,published_at) VALUES (?,?,?,?,?) ON CONFLICT(run_id) DO UPDATE SET archive_version=excluded.archive_version,sha256=excluded.sha256,body=excluded.body,published_at=excluded.published_at",(run_id,version,digest,body,published))
    return get_publication(run_id)
