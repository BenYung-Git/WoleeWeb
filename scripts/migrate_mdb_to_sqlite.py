"""
將 Access .mdb/.accdb 批次轉換為 SQLite（最小可行遷移工具）。

用途：
- 在 Windows（已安裝 Microsoft Access ODBC Driver）執行。
- 產出 user_data.sqlite / sys_data.sqlite / *.sqlite，供 Linux 端 Web 使用。

執行範例：
  python scripts/migrate_mdb_to_sqlite.py
  python scripts/migrate_mdb_to_sqlite.py --source-dir . --overwrite
  python scripts/migrate_mdb_to_sqlite.py --only user_data.mdb sys_data.mdb GS.MDB
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path
from typing import Iterable, List, Sequence

import pyodbc


ACCESS_DRIVER = "Microsoft Access Driver (*.mdb, *.accdb)"
ROOT = Path(__file__).resolve().parents[1]
CHUNK_SIZE = 1000


def _q_ident(name: str) -> str:
    return '"' + (name or "").replace('"', '""') + '"'


def _access_connect(mdb_path: Path) -> pyodbc.Connection:
    conn_str = (
        rf"DRIVER={{{ACCESS_DRIVER}}};"
        rf"DBQ={str(mdb_path)};"
    )
    return pyodbc.connect(conn_str)


def _list_access_tables(cur: pyodbc.Cursor) -> List[str]:
    out: List[str] = []
    for row in cur.tables(tableType="TABLE"):
        name = str(getattr(row, "table_name", "") or "").strip()
        if not name:
            continue
        if name.upper().startswith("MSYS"):
            continue
        if name not in out:
            out.append(name)
    return out


def _column_names(cur: pyodbc.Cursor, table_name: str) -> List[str]:
    cols: List[str] = []
    for row in cur.columns(table=table_name):
        col = str(getattr(row, "column_name", "") or "").strip()
        if col:
            cols.append(col)
    if cols:
        return cols
    cur.execute(f"SELECT * FROM [{table_name}]")
    return [d[0] for d in (cur.description or [])]


def _create_sqlite_table(
    sqlite_conn: sqlite3.Connection,
    table_name: str,
    columns: Sequence[str],
) -> None:
    sqlite_conn.execute(f"DROP TABLE IF EXISTS {_q_ident(table_name)}")
    if not columns:
        sqlite_conn.execute(f"CREATE TABLE {_q_ident(table_name)} (_DUMMY TEXT)")
        return
    defs = ", ".join(f"{_q_ident(c)} TEXT" for c in columns)
    sqlite_conn.execute(f"CREATE TABLE {_q_ident(table_name)} ({defs})")


def _insert_rows(
    sqlite_conn: sqlite3.Connection,
    table_name: str,
    columns: Sequence[str],
    rows: Iterable[Sequence[object]],
) -> int:
    if not columns:
        return 0
    placeholders = ", ".join("?" for _ in columns)
    col_sql = ", ".join(_q_ident(c) for c in columns)
    sql = f"INSERT INTO {_q_ident(table_name)} ({col_sql}) VALUES ({placeholders})"
    total = 0
    buf: List[Sequence[object]] = []
    for row in rows:
        norm = tuple("" if v is None else str(v) for v in row)
        buf.append(norm)
        if len(buf) >= CHUNK_SIZE:
            sqlite_conn.executemany(sql, buf)
            total += len(buf)
            buf.clear()
    if buf:
        sqlite_conn.executemany(sql, buf)
        total += len(buf)
    return total


def migrate_one(mdb_path: Path, sqlite_path: Path, overwrite: bool = False) -> None:
    if not mdb_path.is_file():
        raise FileNotFoundError(f"找不到來源檔：{mdb_path}")
    if sqlite_path.exists() and not overwrite:
        raise FileExistsError(f"目標已存在（未開啟 --overwrite）：{sqlite_path}")
    if sqlite_path.exists():
        sqlite_path.unlink()

    print(f"\n=== 轉換：{mdb_path.name} -> {sqlite_path.name} ===")
    access_conn = _access_connect(mdb_path)
    sqlite_conn = sqlite3.connect(str(sqlite_path))
    try:
        sqlite_conn.execute("PRAGMA journal_mode=WAL")
        sqlite_conn.execute("PRAGMA synchronous=NORMAL")
        cur = access_conn.cursor()
        tables = _list_access_tables(cur)
        if not tables:
            print("未找到可轉換資料表。")
            return

        for idx, tbl in enumerate(tables, start=1):
            cols = _column_names(cur, tbl)
            _create_sqlite_table(sqlite_conn, tbl, cols)
            cur.execute(f"SELECT * FROM [{tbl}]")
            inserted = _insert_rows(sqlite_conn, tbl, cols, cur)
            sqlite_conn.commit()
            print(f"[{idx}/{len(tables)}] {tbl}: {inserted} rows")
    finally:
        access_conn.close()
        sqlite_conn.close()


def _discover_default_sources(source_dir: Path) -> List[Path]:
    preferred = [
        source_dir / "user_data.mdb",
        source_dir / "USER_DATA.mdb",
        source_dir / "sys_data.mdb",
        source_dir / "SYS_DATA.mdb",
    ]
    out: List[Path] = []
    seen = set()
    for p in preferred:
        if p.is_file():
            rp = p.resolve()
            if rp not in seen:
                seen.add(rp)
                out.append(p)
    for p in sorted(source_dir.glob("*.MDB")):
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    for p in sorted(source_dir.glob("*.mdb")):
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            out.append(p)
    return out


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="將 Access .mdb/.accdb 批次轉為 SQLite")
    p.add_argument(
        "--source-dir",
        default=str(ROOT),
        help="來源目錄（預設專案根目錄）",
    )
    p.add_argument(
        "--only",
        nargs="*",
        default=[],
        help="僅轉指定檔名，例如 user_data.mdb sys_data.mdb GS.MDB",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="若目標 .sqlite 已存在則覆蓋",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    source_dir = Path(args.source_dir).resolve()
    if not source_dir.is_dir():
        print(f"來源目錄不存在：{source_dir}")
        return 2

    if args.only:
        sources = [source_dir / name for name in args.only]
    else:
        sources = _discover_default_sources(source_dir)

    if not sources:
        print("找不到可轉換的 .mdb/.accdb 檔案。")
        return 2

    print(f"來源目錄：{source_dir}")
    print(f"待轉檔案：{len(sources)}")
    failed = 0
    for src in sources:
        dst = src.with_suffix(".sqlite")
        try:
            migrate_one(src, dst, overwrite=args.overwrite)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"[失敗] {src.name}: {exc}")

    if failed:
        print(f"\n完成（含失敗）：{len(sources) - failed} 成功 / {failed} 失敗")
        return 1
    print(f"\n全部完成：{len(sources)} 成功")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
