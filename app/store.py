import sqlite3, json, os
from pathlib import Path
from app.errors import DomainError
def connection():
    path=Path(os.environ.get('APP_DB','data/runs.sqlite3'));path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, decision TEXT NOT NULL DEFAULT "待复核")')
    db.execute('''CREATE TABLE IF NOT EXISTS declarations(
        id TEXT PRIMARY KEY, run_id TEXT NOT NULL, line_no INTEGER NOT NULL, cert TEXT NOT NULL,
        verdict TEXT NOT NULL, reason_code TEXT NOT NULL, record TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT "有效", superseded_by TEXT, created_at TEXT NOT NULL,
        recalculated_at TEXT)''')
    return db
def save(result):
    with connection() as db:
        ident=result['manifest']['run_id'];row=db.execute('SELECT payload,revision,decision FROM runs WHERE id=?',(ident,)).fetchone()
        if row: return {**json.loads(row['payload']), 'revision':row['revision'], 'decision':row['decision'], 'reused':True}
        db.execute('INSERT INTO runs(id,payload) VALUES (?,?)',(ident,json.dumps(result,ensure_ascii=False)))
        registered=register_declarations(db, result)
    return {**result,'revision':1,'decision':'待复核','reused':False,'declarations_registered':registered}
def get_run(ident):
    with connection() as db: row=db.execute('SELECT payload,revision,decision FROM runs WHERE id=?',(ident,)).fetchone()
    if row is None: raise DomainError('NOT_FOUND','批次不存在',404)
    return {**json.loads(row['payload']),'revision':row['revision'],'decision':row['decision']}
def latest():
    with connection() as db: row=db.execute('SELECT payload,revision,decision FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()
    return {**json.loads(row['payload']),'revision':row['revision'],'decision':row['decision']} if row else None
def history():
    with connection() as db: return [dict(r) for r in db.execute('SELECT id,revision,decision FROM runs ORDER BY rowid DESC')]
def review(ident, revision, decision):
    if decision not in ('通过','退回'): raise DomainError('DECISION','复核动作无效')
    with connection() as db:
        changed=db.execute('UPDATE runs SET revision=revision+1,decision=? WHERE id=? AND revision=?',(decision,ident,revision)).rowcount
        if not changed: raise DomainError('VERSION','版本已变化，请重新载入',409)
    return {'revision':revision+1,'decision':decision}
def register_declarations(db, result):
    """登记本批出具的声明。

    声明ID由 运行幂等键+原始行号 确定性生成：重跑同一批不会产生第二份声明；
    上游记录更新后内容摘要变化，形成新运行，同业务位置的旧声明被标记“已重算”。
    停止出具/无法判定之外的阻断项本身没有声明编号，不进入登记表。
    """
    import time
    now=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    count=0
    for record in result.get('declarations',[]):
        ident=record['declaration_id']
        existing=db.execute('SELECT id FROM declarations WHERE id=?',(ident,)).fetchone()
        if existing:continue  # 同批重跑：幂等，不新增第二份
        # 同证书+同原始行的旧声明（上游变更后的新版本）置为已重算
        db.execute('''UPDATE declarations SET status='已重算', superseded_by=?, recalculated_at=?
                      WHERE cert=? AND line_no=? AND status='有效' ''',(ident,now,record['cert'],record['line_no']))
        db.execute('INSERT INTO declarations(id,run_id,line_no,cert,verdict,reason_code,record,created_at) VALUES (?,?,?,?,?,?,?,?)',
                   (ident,record['run_id'],record['line_no'],record['cert'],record['verdict'],record['reason_code'],json.dumps(record,ensure_ascii=False),now))
        count+=1
    return count
def list_declarations(run_id=None, status=None):
    sql='SELECT id,run_id,line_no,cert,verdict,reason_code,status,superseded_by,created_at,recalculated_at,record FROM declarations'
    clauses=[];params=[]
    if run_id:clauses.append('run_id=?');params.append(run_id)
    if status:clauses.append('status=?');params.append(status)
    if clauses:sql+=' WHERE '+' AND '.join(clauses)
    sql+=' ORDER BY rowid DESC'
    with connection() as db:
        out=[]
        for r in db.execute(sql,params):
            item={k:r[k] for k in r.keys() if k!='record'}
            item['record']=json.loads(r['record'])
            out.append(item)
        return out
