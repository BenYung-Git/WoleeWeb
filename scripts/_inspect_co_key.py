import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
con = sqlite3.connect(os.path.join(base, "sys_data.sqlite"))
cols = [r[1] for r in con.execute("PRAGMA table_info(program)")]
print("program columns:", cols)
for r in con.execute(
    "SELECT DO_PROC, WORK_FILE, WORK_DB, PRG_CO FROM program ORDER BY DO_PROC"
):
    print(r)

print("\nsqlite company dbs:")
for f in sorted(os.listdir(base)):
    if f.upper().endswith((".SQLITE", ".MDB")) and f.lower() not in (
        "sys_data.sqlite",
        "user_data.sqlite",
    ):
        print(" ", f)
