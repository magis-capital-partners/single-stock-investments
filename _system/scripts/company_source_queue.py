"""Durable, revision-specific source work. SQLite is private and contains no credentials."""
from __future__ import annotations

import json
import hashlib
import os
import sqlite3
import time
from pathlib import Path


class SourceQueue:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, timeout=60)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS jobs (
          key TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
          priority INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
          attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0,
          lease_until REAL NOT NULL DEFAULT 0, updated_at REAL NOT NULL DEFAULT 0,
          error TEXT, result TEXT)''')
        self.db.execute('CREATE INDEX IF NOT EXISTS work_due ON jobs(kind,status,retry_at,priority)')
        self.db.execute('CREATE INDEX IF NOT EXISTS work_order ON jobs(kind,status,attempts,priority DESC,updated_at,key)')
        self.db.commit()
        if not self.db.execute('SELECT 1 FROM jobs LIMIT 1').fetchone():
            self.restore(Path(path).parent/'queue-checkpoints')

    def enqueue(self, jobs):
        self.db.executemany('''INSERT INTO jobs(key,kind,payload,priority,updated_at)
          VALUES(?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET payload=excluded.payload,
          priority=MAX(jobs.priority,excluded.priority)''', [(j['key'], j['kind'], json.dumps(j['payload']), j.get('priority', 0), time.time()) for j in jobs])
        self.db.commit()

    def claim(self, kinds=None, lease_seconds=600, statuses=('pending','retry','running')):
        now = time.time()
        self.db.execute('BEGIN IMMEDIATE')
        try:
            candidates=[]
            for kind in kinds or [r[0] for r in self.db.execute('SELECT DISTINCT kind FROM jobs')]:
                for state in statuses:
                    due='lease_until' if state=='running' else 'retry_at'
                    item=self.db.execute('SELECT * FROM jobs INDEXED BY work_order WHERE kind=? AND status=? AND '+due+'<=? ORDER BY attempts,priority DESC,updated_at,key LIMIT 1',(kind,state,now)).fetchone()
                    if item:candidates.append(item)
            row=min(candidates,key=lambda r:(r['attempts'],-r['priority'],r['updated_at'],r['key'])) if candidates else None
            if row:
                self.db.execute("UPDATE jobs SET status='running',attempts=attempts+1,lease_until=?,updated_at=? WHERE key=?", (now+lease_seconds, now, row['key']))
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        if not row:
            return None
        result = dict(row)
        result['payload'] = json.loads(result['payload'])
        result['attempts'] += 1
        return result

    def finish(self, key, status, *, result=None, error=None):
        if status not in {'indexed','needs_ocr','needs_transcript','access_unavailable','unsupported','empty_source','retry','failed'}:
            raise ValueError('Unknown source outcome: '+status)
        row = self.db.execute('SELECT attempts FROM jobs WHERE key=?', (key,)).fetchone()
        delay = min(86400, 60 * 2**min(row['attempts'], 10)) if status == 'retry' else 86400 if status!='indexed' and row['attempts']>1 else 0
        self.db.execute('UPDATE jobs SET status=?,result=?,error=?,retry_at=?,lease_until=0,updated_at=? WHERE key=?',
                        (status, json.dumps(result or {}), error, time.time()+delay, time.time(), key))
        self.db.commit()

    def reset(self, statuses, kinds=None):
        condition="status IN ("+','.join('?' for _ in statuses)+')'
        values=list(statuses)
        if kinds:
            condition+=' AND kind IN ('+','.join('?' for _ in kinds)+')';values.extend(kinds)
        self.db.execute("UPDATE jobs SET status='pending',retry_at=0 WHERE "+condition,values)
        self.db.commit()

    def checkpoint(self, directory):
        """Portable private shards; never commit a live SQLite/WAL file."""
        directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
        groups={}
        for row in self.db.execute('SELECT * FROM jobs ORDER BY key'):
            key=hashlib.sha256(row['key'].encode()).hexdigest()[:2]
            groups.setdefault(key,[]).append(dict(row))
        for key,rows in groups.items():
            target=directory/(key+'.json')
            body=json.dumps(rows,ensure_ascii=False,separators=(',',':'))+'\n'
            if target.exists() and target.read_text(encoding='utf-8')==body:continue
            temp=target.with_suffix('.'+str(os.getpid())+'.tmp')
            temp.write_text(body,encoding='utf-8')
            for attempt in range(10):
                try:
                    temp.replace(target);break
                except PermissionError:
                    if attempt==9:raise
                    time.sleep(.05*(attempt+1))

    def restore(self, directory):
        for path in Path(directory).glob('*.json'):
            for row in json.loads(path.read_text(encoding='utf-8')):
                if row['status']=='running':row.update(status='pending',lease_until=0)
                keys=list(row)
                self.db.execute('INSERT OR IGNORE INTO jobs ('+','.join(keys)+') VALUES ('+','.join('?' for _ in keys)+')',[row[k] for k in keys])
        self.db.commit()

    def report(self):
        return {'jobs': self.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],
                'by_kind': {kind: dict(self.db.execute('SELECT status,COUNT(*) FROM jobs WHERE kind=? GROUP BY status', (kind,)).fetchall())
                            for (kind,) in self.db.execute('SELECT DISTINCT kind FROM jobs').fetchall()},
                'unresolved': self.db.execute("SELECT COUNT(*) FROM jobs WHERE status!='indexed'").fetchone()[0]}

    def close(self):
        self.db.close()
