from __future__ import annotations

import socket
from typing import List


def get_lan_ip_addresses() -> List[str]:
    """取得本機區域網路 IPv4 位址（供其他電腦連線用）。"""
    ips: List[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip.startswith("127."):
                continue
            if ip not in ips:
                ips.append(ip)
    except Exception:
        pass

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if not ip.startswith("127.") and ip not in ips:
            ips.insert(0, ip)
    except Exception:
        pass
    return ips


def web_access_urls(host: str, port: int) -> List[str]:
    """依綁定位址列出可存取的 Web URL。"""
    host = (host or "127.0.0.1").strip()
    if host in ("0.0.0.0", "::"):
        urls = [f"http://127.0.0.1:{port}/"]
        for ip in get_lan_ip_addresses():
            urls.append(f"http://{ip}:{port}/")
        return urls
    return [f"http://{host}:{port}/"]


def local_browser_url(host: str, port: int) -> str:
    """在本機開啟瀏覽器時使用的 URL。"""
    if (host or "").strip() in ("0.0.0.0", "::", ""):
        return f"http://127.0.0.1:{port}/"
    return f"http://{host}:{port}/"


def print_web_startup_banner(host: str, port: int) -> None:
    """啟動 Web 伺服器時印出所有可連線位址。"""
    urls = web_access_urls(host, port)
    print("")
    print("=" * 50)
    print("  Web 介面已啟動，請用瀏覽器開啟：")
    for u in urls:
        label = "本機" if "127.0.0.1" in u else "區域網路（其他電腦）"
        print(f"    [{label}] {u}")
    if host in ("0.0.0.0", "::"):
        print("")
        print("  其他電腦請用「區域網路」位址；若連不上請：")
        print("  1) 確認兩台電腦在同一 WiFi／網段（例如皆為 192.168.1.x）")
        print("  2) 勿使用 192.168.56.x（常為虛擬網卡，外機無法連）")
        print("  3) 以系統管理員執行 scripts\\open_web_firewall.bat 開放 TCP", port)
    print("=" * 50)
    print("")
