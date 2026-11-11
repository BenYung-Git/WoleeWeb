#!/usr/bin/env python3
"""除錯 NEED_ATTACH / NEED_OTHER 是否正確載入。"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from core.auth import resolve_sys_data_path
from core.menu_loader import ProgramRepository
from services.app_service import AppService, AppRuntime
from core.auth import UserSession


def main() -> None:
    base = _ROOT
    mdb = resolve_sys_data_path(base)
    print("sys_data:", mdb)

    repo = ProgramRepository(mdb)
    repo.load()
    attach_procs = [p for p in repo._all_items if p.need_attach]
    other_procs = [p for p in repo._all_items if p.need_other]
    print(f"program rows need_attach={len(attach_procs)} need_other={len(other_procs)}")
    for p in attach_procs[:5]:
        print("  ATTACH", p.do_proc, p.attach_path, p.attach_key)
    for p in other_procs[:5]:
        print("  OTHER", p.do_proc, p.other_title)

    if not attach_procs and not other_procs:
        from core.db_factory import get_backend_for_path

        b = get_backend_for_path(mdb)
        cols = b.list_columns("program")
        print("program columns:", cols)
        flag_cols = [c for c in cols if "ATTACH" in c.upper() or "OTHER" in c.upper()]
        print("flag-related:", flag_cols)

    svc = AppService(base)
    session = UserSession(
        user_no="TEST",
        group_no="1",
        group_level=99,
        company_key="GS",
        user_data_path=os.path.join(base, "user_data.sqlite"),
    )
    rt = AppRuntime(base_dir=base, session=session)
    rt.reload_metadata()

    samples = [p.do_proc for p in (attach_procs + other_procs)[:3]]
    if not samples and repo._all_items:
        samples = [repo._all_items[0].do_proc]

    for do_proc in samples:
        schema, err = svc.resolve_work(rt, do_proc, reload_program=True)
        if err or schema is None:
            print(do_proc, "ERR", err)
            continue
        wa = svc._work_actions_dict(schema.work_actions)
        print(do_proc, "work_actions=", wa)


if __name__ == "__main__":
    main()
