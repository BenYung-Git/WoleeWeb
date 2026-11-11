#!/usr/bin/env python3
"""Ubuntu 完整重新安裝（不受 Windows CRLF 影響，建議用此腳本）。"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REQUIRED_FILES = (
    "launcher.py",
    "requirements.txt",
    "api/server.py",
    "web/static/app.js",
    "web/static/index.html",
    "services/app_service.py",
    "core/data_dictionary.py",
)


def run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(cmd))
    subprocess.check_call(cmd, **kwargs)


def _remove_tree(path: str) -> None:
    try:
        shutil.rmtree(path)
    except PermissionError as exc:
        raise PermissionError(
            f"無法刪除 {path}（權限不足，常見於 Samba／Windows 建立的 .venv）。\n"
            "請改用本機 venv：\n"
            f"  python3 {os.path.join(_ROOT, 'scripts', 'install_ubuntu.py')} "
            f"--venv-dir ~/.wolee-venv\n"
            "或先修正權限後再試：\n"
            f"  sudo chown -R $(whoami):$(whoami) {path}\n"
            f"  rm -rf {path}"
        ) from exc


def _resolve_venv_dir(root: str, venv_arg: str) -> str:
    raw = (venv_arg or "").strip() or ".venv"
    if os.path.isabs(raw):
        return os.path.normpath(raw)
    return os.path.normpath(os.path.join(root, raw))


def main() -> int:
    parser = argparse.ArgumentParser(description="WoleeWeb Ubuntu 重新安裝")
    parser.add_argument(
        "--keep-venv",
        action="store_true",
        help="保留既有虛擬環境（僅升級 pip 與 requirements）",
    )
    parser.add_argument(
        "--venv-dir",
        default=".venv",
        help="虛擬環境目錄（預設專案內 .venv；Samba 共用建議 ~/.wolee-venv）",
    )
    parser.add_argument("--skip-verify", action="store_true", help="略過安裝後檢查")
    args = parser.parse_args()

    root = _ROOT
    os.chdir(root)
    print("=== WoleeWeb Ubuntu 重新安裝 ===")
    print("目錄:", root)
    print()

    py = sys.executable
    print("Python:", py, sys.version.split()[0])

    venv_dir = _resolve_venv_dir(root, args.venv_dir)
    print("虛擬環境:", venv_dir)
    if not args.keep_venv and os.path.isdir(venv_dir):
        print("移除舊虛擬環境 ...")
        _remove_tree(venv_dir)

    if not os.path.isdir(venv_dir):
        print("建立虛擬環境 ...")
        os.makedirs(os.path.dirname(venv_dir) or ".", exist_ok=True)
        run([py, "-m", "venv", venv_dir])

    if os.name == "nt":
        vpy = os.path.join(venv_dir, "Scripts", "python.exe")
    else:
        vpy = os.path.join(venv_dir, "bin", "python3")
    if not os.path.isfile(vpy):
        vpy = os.path.join(venv_dir, "bin", "python")

    print("升級 pip ...")
    run([vpy, "-m", "pip", "install", "--upgrade", "pip", "wheel"])

    req = os.path.join(root, "requirements.txt")
    print("安裝相依套件 (requirements.txt) ...")
    run([vpy, "-m", "pip", "install", "-r", req])

    print()
    print("=== 檢查必要檔案 ===")
    missing = [f for f in REQUIRED_FILES if not os.path.isfile(os.path.join(root, f))]
    for f in missing:
        print("  [缺少]", f)

    for name in ("sys_data.sqlite", "sys_data.mdb", "SYS_DATA.mdb"):
        if os.path.isfile(os.path.join(root, name)):
            break
    else:
        print("  [警告] 找不到 sys_data.sqlite / sys_data.mdb")

    for name in ("user_data.sqlite", "user_data.mdb"):
        if os.path.isfile(os.path.join(root, name)):
            break
    else:
        print("  [警告] 找不到 user_data.sqlite / user_data.mdb")

    if missing:
        print()
        print("[錯誤] 專案檔案不完整，請複製整個 WoleeWeb 資料夾後再執行。")
        return 1

    if not args.skip_verify:
        print()
        print("=== 程式版本檢查 ===")
        app_js = os.path.join(root, "web", "static", "app.js")
        with open(app_js, encoding="utf-8", errors="replace") as f:
            js = f.read()
        if "findMenuWorkActions" in js:
            print("  web/static/app.js: 含附件／其他按鈕邏輯 OK")
        else:
            print("  [警告] web/static/app.js 可能為舊版")

        with open(os.path.join(root, "web", "static", "index.html"), encoding="utf-8") as f:
            for line in f:
                if "app.js" in line:
                    print(" ", line.strip())
                    break

        server_py = os.path.join(root, "api", "server.py")
        with open(server_py, encoding="utf-8", errors="replace") as f:
            if "need_attach" in f.read():
                print("  api/server.py: 選單 need_attach OK")
            else:
                print("  [警告] api/server.py 可能為舊版")

        print()
        print("=== 資料庫旗標檢查 ===")
        check = (
            "import sys; sys.path.insert(0, %r); "
            "from core.auth import resolve_sys_data_path; "
            "from core.menu_loader import ProgramRepository; "
            "mdb = resolve_sys_data_path(%r); "
            "print('sys_data:', mdb); "
            "repo = ProgramRepository(mdb); repo.load(); "
            "na = sum(1 for p in repo._all_items if p.need_attach); "
            "no = sum(1 for p in repo._all_items if p.need_other); "
            "print('need_attach=', na, 'need_other=', no)"
        ) % (root, root)
        try:
            subprocess.check_call([vpy, "-c", check], cwd=root)
        except subprocess.CalledProcessError as exc:
            print("  [警告] 無法讀取 sys_data (exit", exc.returncode, ")")

    print()
    print("=== 安裝完成 ===")
    print()
    print("啟動 Web：")
    print(f"  cd {root}")
    if venv_dir == _resolve_venv_dir(root, ".venv"):
        print("  source .venv/bin/activate")
    else:
        print(f"  source {venv_dir}/bin/activate")
    print("  python3 launcher.py --mode web --headless --host 0.0.0.0 --port 8080")
    print()
    print("瀏覽器: http://<本機IP>:8080  （Ctrl+Shift+R 強制重新整理）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
