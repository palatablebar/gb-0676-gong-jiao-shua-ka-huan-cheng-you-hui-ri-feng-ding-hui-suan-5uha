import csv,io
from app.config import COLUMNS
from app.errors import DomainError
from app.reasons import reject
from app.lineage import merge
def decode(raw):
    for encoding in ("utf-8-sig","gb18030"):
        try: return raw.decode(encoding),encoding
        except UnicodeDecodeError: continue
    raise DomainError("ENCODING","无法识别文件编码")
def evaluate(raw,context=None):
    text,encoding=decode(raw)
    if not text: raise DomainError("EMPTY_FILE","文件为空")
    if not text.strip(): raise DomainError("BLANK_ONLY","全部为空行")
    stream=csv.reader(io.StringIO(text,newline=""));header=next(stream,None)
    if header!=COLUMNS: raise DomainError("BAD_HEADER","表头不匹配")
    rows=[];bad=[];seen={};duplicate=blank=repeated=count=0;ledger=[];cursor=2
    try:
        for cells in stream:
            count+=1;line=stream.line_num
            entry={"line":line,"_line":line,"start":cursor,"end":line};cursor=line+1
            if not cells or not any(c.strip() for c in cells): blank+=1;ledger.append({**entry,"disposition":"blank","raw":cells});continue
            if cells==header: repeated+=1;ledger.append({**entry,"disposition":"repeated_header","raw":cells});continue
            row={"_line":line,"_sources":[line],"_raw":cells}
            if len(cells)!=len(header): bad.append(reject(row,"BAD_COLUMNS","列数不匹配"));ledger.append({**entry,"disposition":"quarantine","raw":cells});continue
            row.update(dict(zip(header,[x.strip() for x in cells])))
            if not row[header[0]]: bad.append(reject(row,"EMPTY_VALUE","业务键为空"));ledger.append({**entry,"disposition":"quarantine","raw":cells});continue
            key=row[header[0]]
            if key in seen:
                previous=seen[key]
                if cells==previous["_raw"]: duplicate+=1;ledger.append({**entry,"disposition":"duplicate","raw":cells})
                else: bad.append(reject(row,"DUPLICATE_CONFLICT","同键不同值"));ledger.append({**entry,"disposition":"quarantine","raw":cells})
                continue
            seen[key]=row;rows.append(row);ledger.append({**entry,"disposition":"accepted","raw":cells})
    except csv.Error: raise DomainError("BAD_CSV","引号未闭合或文件损坏")
    if count==0: raise DomainError("HEADER_ONLY","仅有表头")
    if not rows and not bad: raise DomainError("BLANK_ONLY","全部为空行")
    lineage,line_metrics=merge(ledger,[r["_line"] for r in rows],[r["_line"] for r in bad])
    if line_metrics["unplaced"]:
        raise DomainError("LINEAGE_GAP","来源行未能逐行着落")
    return {"rows":rows,"quarantine":bad,"lineage":lineage,"line_metrics":line_metrics,"metrics":{"input":count,"accepted":len(rows),"quarantine":len(bad),"duplicate":duplicate,"blank":blank,"repeated_headers":repeated,"encoding":encoding,"source_lines":line_metrics["source_lines"]}}
