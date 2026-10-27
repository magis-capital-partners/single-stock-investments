import sqlite3
from pathlib import Path

from _system.scripts.prune_cloudflare_d1 import prune_realized_generations, table_names


def test_pruning_versions_preserves_active_full_history_and_original_evidence():
    db = sqlite3.connect(":memory:")
    root = Path(__file__).resolve().parents[3]
    db.executescript((root / "dashboard/cloudflare/migrations/0024_sleeve_realized.sql").read_text())
    db.executescript((root / "dashboard/cloudflare/migrations/0025_sleeve_realized_pages.sql").read_text())
    for number in range(6):
        gen = str(number)
        db.execute("INSERT INTO sleeve_realized_generations VALUES (?,?,?,'complete','{}',?,?)", (
            gen, "TEST", "2000-01-01", f"2000-01-0{number + 1}", f"2000-01-0{number + 1}"))
        db.execute("INSERT INTO sleeve_realized_records VALUES (?,?,'drew','1999-01-01',NULL,'unknown','TEST','{}')", (gen, "historic-trade"))
        db.execute("INSERT INTO sleeve_realized_pages VALUES (?,1,1,'1999-01-01','1999-01-01','','','[]','[]')", (gen,))
        db.execute("INSERT INTO sleeve_realized_batches VALUES (?,0,?,1)", (gen, gen))
    db.execute("INSERT INTO sleeve_realized_current(account,generation_id,through_date,published_at) VALUES ('TEST','0','2000-01-01','2000-01-01')")
    db.execute("INSERT INTO sleeve_realized_archive_parts VALUES ('TEST','report',0,'sha',100)")
    db.execute("INSERT INTO sleeve_realized_pages VALUES ('shared',1,1,'1999-01-01','1999-01-01','','','[]','[]')")
    db.execute("INSERT INTO sleeve_realized_pages VALUES ('orphan',1,1,'1999-01-01','1999-01-01','','','[]','[]')")
    db.execute("INSERT INTO sleeve_realized_batches VALUES ('1',1,'shared',1)")
    db.execute("INSERT INTO sleeve_realized_batches VALUES ('5',1,'shared',1)")

    def execute(sql):
        db.execute(sql)
        return db.execute("SELECT changes()").fetchone()[0]

    prune_realized_generations(execute, table_names(db), batch_size=1)
    assert {row[0] for row in db.execute("SELECT generation_id FROM sleeve_realized_generations")} == {"0", "3", "4", "5"}
    assert db.execute("SELECT count(*) FROM sleeve_realized_records WHERE generation_id='0'").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM sleeve_realized_archive_parts").fetchone()[0] == 1
    assert {row[0] for row in db.execute("SELECT content_sha FROM sleeve_realized_pages")} == {"0", "3", "4", "5", "shared"}
