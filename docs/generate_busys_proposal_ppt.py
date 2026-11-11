#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""產生必思 BuSys ERP 高層推介簡報（.pptx）。"""
from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "必思BuSys_ERP_高層推介.pptx"

NAVY = RGBColor(0x1B, 0x4F, 0x72)
GOLD = RGBColor(0xB9, 0x77, 0x0E)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK = RGBColor(0x2C, 0x3E, 0x50)
GRAY = RGBColor(0x5D, 0x6D, 0x7E)
ACCENT = RGBColor(0x11, 0x7A, 0x65)
LIGHT_BLUE = RGBColor(0xEB, 0xF5, 0xFB)
PALE = RGBColor(0xD6, 0xEA, 0xF8)

FONT = "Microsoft JhengHei"
BLANK = 6


def _font(run, size: int, bold: bool = False, color: RGBColor | None = None):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = FONT
    if color:
        run.font.color.rgb = color


def blank_slide(prs: Presentation):
    return prs.slides.add_slide(prs.slide_layouts[BLANK])


def title_bar(slide, title: str, subtitle: str = ""):
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(1.05)
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = NAVY
    bar.line.fill.background()
    box = slide.shapes.add_textbox(Inches(0.5), Inches(0.12), Inches(12.3), Inches(0.85))
    tf = box.text_frame
    tf.clear()
    r = tf.paragraphs[0].add_run()
    r.text = title
    _font(r, 28, True, WHITE)
    if subtitle:
        p2 = tf.add_paragraph()
        r2 = p2.add_run()
        r2.text = subtitle
        _font(r2, 14, False, PALE)


def bullets(slide, items: list[str], top=1.35, size=18, left=0.55, width=12.2):
    box = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(5.9))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    for i, text in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(8)
        r = p.add_run()
        r.text = text
        _font(r, size, False, DARK)


def section_slide(prs, part: str, title: str):
    slide = blank_slide(prs)
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(7.5)
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = NAVY
    bg.line.fill.background()
    box = slide.shapes.add_textbox(Inches(0.85), Inches(2.35), Inches(11.5), Inches(2.8))
    tf = box.text_frame
    r = tf.paragraphs[0].add_run()
    r.text = part
    _font(r, 22, False, GOLD)
    p2 = tf.add_paragraph()
    r2 = p2.add_run()
    r2.text = title
    _font(r2, 40, True, WHITE)


def table_on_slide(slide, top: float, headers: list[str], rows: list[list[str]], col_inches: list[float]):
    nrows = 1 + len(rows)
    ncols = len(headers)
    height = min(5.5, 0.42 * nrows + 0.25)
    tbl = slide.shapes.add_table(
        nrows, ncols, Inches(0.45), Inches(top), Inches(12.45), Inches(height)
    ).table
    for ci, w in enumerate(col_inches):
        tbl.columns[ci].width = Inches(w)
    for ci, h in enumerate(headers):
        c = tbl.cell(0, ci)
        c.text = h
        c.fill.solid()
        c.fill.fore_color.rgb = NAVY
        for p in c.text_frame.paragraphs:
            for run in p.runs:
                _font(run, 14, True, WHITE)
    for ri, row in enumerate(rows, 1):
        for ci, val in enumerate(row):
            c = tbl.cell(ri, ci)
            c.text = val
            for p in c.text_frame.paragraphs:
                for run in p.runs:
                    _font(run, 12 if len(val) > 40 else 13, ci == 0, DARK)
            if ri % 2 == 0:
                c.fill.solid()
                c.fill.fore_color.rgb = LIGHT_BLUE


def flow_steps(slide, steps: list[tuple[str, str]], top=1.45):
    n = len(steps)
    slot = 12.0 / n
    w = slot - 0.12
    for i, (label, detail) in enumerate(steps):
        left = 0.48 + i * slot
        sh = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(w), Inches(0.52)
        )
        sh.fill.solid()
        sh.fill.fore_color.rgb = ACCENT if i % 2 else NAVY
        sh.line.fill.background()
        tb = slide.shapes.add_textbox(Inches(left), Inches(top + 0.1), Inches(w), Inches(0.4))
        p = tb.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = label
        _font(r, 12, True, WHITE)
        tb2 = slide.shapes.add_textbox(Inches(left), Inches(top + 0.58), Inches(w), Inches(1.15))
        tf2 = tb2.text_frame
        tf2.word_wrap = True
        p2 = tf2.paragraphs[0]
        p2.alignment = PP_ALIGN.CENTER
        r2 = p2.add_run()
        r2.text = detail
        _font(r2, 10, False, GRAY)
        if i < n - 1:
            ar = slide.shapes.add_textbox(
                Inches(left + w + 0.02), Inches(top + 0.08), Inches(0.2), Inches(0.35)
            )
            r3 = ar.text_frame.paragraphs[0].add_run()
            r3.text = "›"
            _font(r3, 22, True, GOLD)


def icon_cards(slide, cards: list[tuple[str, str]], top=1.35):
    """2x3 卡片。"""
    cw, ch = 3.95, 1.75
    gap_x, gap_y = 0.25, 0.22
    for idx, (title, body) in enumerate(cards):
        row, col = divmod(idx, 3)
        left = 0.45 + col * (cw + gap_x)
        t = top + row * (ch + gap_y)
        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(t), Inches(cw), Inches(ch)
        )
        card.fill.solid()
        card.fill.fore_color.rgb = LIGHT_BLUE
        card.line.color.rgb = NAVY
        tb = slide.shapes.add_textbox(Inches(left + 0.15), Inches(t + 0.12), Inches(cw - 0.3), Inches(ch - 0.2))
        tf = tb.text_frame
        tf.word_wrap = True
        r0 = tf.paragraphs[0].add_run()
        r0.text = title
        _font(r0, 15, True, NAVY)
        p1 = tf.add_paragraph()
        r1 = p1.add_run()
        r1.text = body
        _font(r1, 11, False, DARK)


def architecture_diagram(slide):
    title_bar(slide, "整體架構一覽", "使用者 · 介面 · 業務核心 · 資料")
    layers = [
        ("使用者層", "前線同仁 · 會計倉務 · 主管 · CEO", NAVY),
        ("介面層", "Windows 桌面 BuSys ｜ Web 瀏覽器（免安裝）", ACCENT),
        ("應用層", "Web API ＋ 共用業務核心（桌面／Web 同一邏輯）", RGBColor(0x5B, 0x2C, 0x6F)),
        ("資料層", "登入庫 · 系統設定庫 · 公司營運庫 · 附件／報表模板", GOLD),
    ]
    y = 1.35
    for label, desc, color in layers:
        sh = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(y), Inches(10.9), Inches(0.95)
        )
        sh.fill.solid()
        sh.fill.fore_color.rgb = color
        sh.line.fill.background()
        tb = slide.shapes.add_textbox(Inches(1.45), Inches(y + 0.12), Inches(10.4), Inches(0.75))
        tf = tb.text_frame
        r = tf.paragraphs[0].add_run()
        r.text = label
        _font(r, 16, True, WHITE)
        p2 = tf.add_paragraph()
        r2 = p2.add_run()
        r2.text = desc
        _font(r2, 13, False, PALE)
        if y < 4.5:
            arr = slide.shapes.add_textbox(Inches(6.2), Inches(y + 1.0), Inches(0.5), Inches(0.35))
            r3 = arr.text_frame.paragraphs[0].add_run()
            r3.text = "▼"
            _font(r3, 14, True, GRAY)
        y += 1.15
    note = slide.shapes.add_textbox(Inches(0.55), Inches(6.15), Inches(12.2), Inches(0.9))
    r = note.text_frame.paragraphs[0].add_run()
    r.text = "建議：含 .mdb 資料庫之 Windows 主機提供 Web 服務；其他據點以瀏覽器連線即可。"
    _font(r, 13, False, GRAY)


def build() -> Path:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # 封面
    s = blank_slide(prs)
    bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = NAVY
    bg.line.fill.background()
    strip = s.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(6.82), Inches(13.333), Inches(0.68)
    )
    strip.fill.solid()
    strip.fill.fore_color.rgb = GOLD
    strip.line.fill.background()
    for box, text, size, bold, top in [
        (Inches(0.85), "必思企業系統", 44, True, Inches(2.05)),
        (Inches(0.85), "BuSys ERP", 32, False, Inches(3.05)),
        (Inches(0.85), "高層推介簡報", 26, True, Inches(3.75)),
        (Inches(0.85), "資料驅動 · 桌面與 Web 並行 · 延續企業既有制度", 17, False, Inches(4.55)),
    ]:
        tb = s.shapes.add_textbox(box, top, Inches(11.5), Inches(0.85))
        r = tb.text_frame.paragraphs[0].add_run()
        r.text = text
        _font(r, size, bold, WHITE if size >= 26 else PALE)

    # 目錄
    s = blank_slide(prs)
    title_bar(s, "簡報大綱")
    bullets(
        s,
        [
            "一、系統定位與核心優點",
            "二、整體架構與運作流程",
            "三、功能與特性總覽",
            "四、部署模式與方案比較",
            "五、建議下一步",
        ],
        top=1.55,
        size=24,
    )

    section_slide(prs, "PART 01", "系統定位與核心優點")

    s = blank_slide(prs)
    title_bar(s, "Executive Summary", "給決策層的一頁摘要")
    table_on_slide(
        s,
        1.22,
        ["維度", "價值"],
        [
            ["業務", "主檔、交易、查詢、對帳、報表在同一套規則下運作，減少系統外 Excel"],
            ["管理", "依職級／群組控制可開功能；多公司、多帳套可切換"],
            ["IT", "新作業以選單與欄位設定驅動，不必每個畫面都重寫程式"],
            ["使用者", "桌面完整操作 ＋ 瀏覽器 Web；高層與外點免裝客戶端"],
            ["演進", "自 Access 世代平滑升級，可逐步導入 SQLite 與混合部署"],
        ],
        [1.6, 10.85],
    )

    s = blank_slide(prs)
    title_bar(s, "核心優點 ①", "投資保護 — 不是推倒重來")
    bullets(
        s,
        [
            "沿用 program、MAINMENU、columns 等「企業字典」，多年作業規則可延續。",
            "內建主檔＋明細（TX）、編號規則、Lookup、報表程序等 ERP 基本能力。",
            "降低換系統風險：升級的是載具與通道，不是推翻制度與資料。",
            "縮短上線與再訓練時間，利於分階段導入。",
        ],
        size=20,
    )

    s = blank_slide(prs)
    title_bar(s, "核心優點 ②", "桌面與 Web — 同一套業務大腦")
    bullets(
        s,
        [
            "桌面（PyQt）：適合大量鍵入、複雜作業、完整列印預覽。",
            "Web（瀏覽器）：登入、選單、Grid、表單、附件、報表匯出等。",
            "共用同一業務核心，避免「網頁版數字對不上桌面版」。",
            "同一真相來源（Single Source of Truth），兩種使用方式。",
        ],
        size=20,
    )

    s = blank_slide(prs)
    title_bar(s, "核心優點 ③", "可配置、可擴展的 ERP 平台")
    bullets(
        s,
        [
            "標準作業：選單新增 program → 主檔 Grid、明細、CRUD、搜尋、權限。",
            "專用作業模組：ARAP 銷帳、收付款、客戶／存貨／帳戶查詢、資料匯入、SQL 查詢、AI 助理。",
            "columns 控制欄位顯示、編輯、格式、附件按鈕 — IT 與顧問可分工。",
            "新單據類型以「配置為主、開發為輔」，加快回應業務。",
        ],
        size=19,
    )

    s = blank_slide(prs)
    title_bar(s, "核心優點 ④", "治理、體驗與現代化")
    bullets(
        s,
        [
            "登入與群組等級：依 GROUP_LEVEL 與 program 等級篩選功能。",
            "多公司：登入庫 ＋ 各公司營運資料庫，切換公司即切換帳套。",
            "Fusion 介面、多種淡色主題、中英切換；Web 五種主選單呈現。",
            "AI 助理：私人文件、意圖導向查詢，輔助管理層取得資訊。",
        ],
        size=19,
    )

    section_slide(prs, "PART 02", "整體架構與運作流程")

    s = blank_slide(prs)
    architecture_diagram(s)

    s = blank_slide(prs)
    title_bar(s, "日常運作流程", "登入到完成作業的五個步驟")
    flow_steps(
        s,
        [
            ("1 登入", "帳密、公司別\n記錄上次公司"),
            ("2 選單", "載入 MAINMENU\n依權限篩選"),
            ("3 開作業", "DO_PROC\n標準或專用"),
            ("4 處理", "CRUD、Lookup\n附件、列印"),
            ("5 完成", "登出或\nWeb session 結束"),
        ],
    )
    bullets(
        s,
        [
            "標準作業：主檔 Grid ＋ TX 明細 ＋ 表單編輯。",
            "專用作業：依程序代號進入 ARAP、匯入、查詢等模組。",
        ],
        top=3.35,
        size=16,
    )

    s = blank_slide(prs)
    title_bar(s, "作業分流邏輯", "標準 Grid 與專家模組並存")
    flow_steps(
        s,
        [
            ("登入", "UserSession"),
            ("載入", "sys_data\ncolumns"),
            ("選單", "program"),
            ("分支", "STD_PROC?"),
        ],
        top=1.4,
    )
    left = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.55), Inches(2.85), Inches(5.85), Inches(1.35)
    )
    left.fill.solid()
    left.fill.fore_color.rgb = LIGHT_BLUE
    left.line.color.rgb = NAVY
    tb = s.shapes.add_textbox(Inches(0.75), Inches(3.0), Inches(5.5), Inches(1.1))
    tf = tb.text_frame
    r = tf.paragraphs[0].add_run()
    r.text = "是 → 標準作業"
    _font(r, 16, True, NAVY)
    p = tf.add_paragraph()
    r2 = p.add_run()
    r2.text = "WorkPage：Grid、明細、新增／改／刪、列印"
    _font(r2, 13, False, DARK)
    right = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.85), Inches(2.85), Inches(5.85), Inches(1.35)
    )
    right.fill.solid()
    right.fill.fore_color.rgb = LIGHT_BLUE
    right.line.color.rgb = ACCENT
    tb2 = s.shapes.add_textbox(Inches(7.05), Inches(3.0), Inches(5.5), Inches(1.1))
    tf2 = tb2.text_frame
    r3 = tf2.paragraphs[0].add_run()
    r3.text = "否 → 專用作業"
    _font(r3, 16, True, ACCENT)
    p4 = tf2.add_paragraph()
    r4 = p4.add_run()
    r4.text = "ARAP、收付款、查詢、資料匯入、RUNQUERY、AI…"
    _font(r4, 13, False, DARK)
    db = s.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(3.2), Inches(4.55), Inches(6.9), Inches(0.75)
    )
    db.fill.solid()
    db.fill.fore_color.rgb = NAVY
    db.line.fill.background()
    tdb = s.shapes.add_textbox(Inches(3.4), Inches(4.68), Inches(6.5), Inches(0.5))
    rd = tdb.text_frame.paragraphs[0].add_run()
    rd.text = "公司營運資料庫（Access .mdb 或 SQLite）"
    _font(rd, 14, True, WHITE)

    section_slide(prs, "PART 03", "功能與特性總覽")

    s = blank_slide(prs)
    title_bar(s, "功能地圖", "六大能力區塊")
    icon_cards(
        s,
        [
            ("平台基礎", "登入、多公司、權限選單、中英、主題、字級"),
            ("標準 ERP", "主檔 Grid、TX 明細、CRUD、搜尋、排序、Lookup"),
            ("財務營運", "ARAP 銷帳、收付款、帳戶／客戶／存貨查詢"),
            ("資料整合", "資料匯入、RUNQUERY 查詢與 Excel 匯出"),
            ("輸出報表", "列印預覽、PDF／XLSX／DOCX、Invoice／Quotation 模板"),
            ("協作智能", "附件、電郵文字、AI 助理與私人文件"),
        ],
    )

    s = blank_slide(prs)
    title_bar(s, "特性 ①", "資料字典驅動使用者介面")
    bullets(
        s,
        [
            "columns：Grid 顯示（GRID_VIEW）、表單編輯（CTRL_EDIT）、日期格式、Combo、Lookup 回寫。",
            "program：工作表、明細表、編號規則、附件路徑、指定公司庫、報表程序（RPT_PROC）。",
            "效益：新欄位、新單據類型先配置、後上線，縮短 IT 排程。",
            "主選單 MAINMENU × program 決定功能群組與排序。",
        ],
        size=19,
    )

    s = blank_slide(prs)
    title_bar(s, "特性 ②", "專家模組 — 業務深度")
    table_on_slide(
        s,
        1.2,
        ["模組", "說明", "管理價值"],
        [
            ["ARAP 銷帳", "應收應付勾稽、自動分配、篩選", "加速月結對帳"],
            ["收付款", "與單據流程整合", "資金與單據一致"],
            ["多維查詢", "客戶／存貨／帳戶查詢", "主管即時掌握狀況"],
            ["資料匯入", "待匯清單、批次執行", "減少人工 key 入"],
            ["列印體系", "清單、財報、Excel 模板轉 PDF", "對外單據標準化"],
        ],
        [2.0, 5.2, 5.25],
    )

    s = blank_slide(prs)
    title_bar(s, "特性 ③", "高層與 Web 使用場景")
    bullets(
        s,
        [
            "CEO／董事：筆電、平板瀏覽器即可查詢、報表、附件 — 無需安裝客戶端。",
            "集中部署 Web 服務與資料庫，利於備份與權限管控。",
            "附件支援 Windows 路徑對應（Web／Linux 可設路徑映射表）。",
            "列印預覽、PDF 匯出等可在 Web 與桌面間選擇最適方式。",
        ],
        size=19,
    )

    section_slide(prs, "PART 04", "部署模式與方案比較")

    s = blank_slide(prs)
    title_bar(s, "部署模式", "依組織成熟度選擇")
    table_on_slide(
        s,
        1.18,
        ["模式", "說明", "適用情境"],
        [
            ["桌面為主", "各 PC 執行 BuSys，資料在本機或檔案伺服器", "工廠、門市、習慣桌面操作"],
            ["Web 為主", "Windows 主機提供 Web，使用者瀏覽器連線", "總部、CEO、外勤、分公司"],
            ["混合 both", "同時提供桌面與 Web", "過渡期、關鍵崗桌面＋管理層 Web"],
            ["Linux Web", "Ubuntu headless 提供 Web（需規劃列印等）", "機房標準化、Samba 共用"],
        ],
        [1.5, 5.5, 5.45],
    )

    s = blank_slide(prs)
    title_bar(s, "方案比較", "BuSys 的定位")
    table_on_slide(
        s,
        1.15,
        ["", "全新 SaaS ERP", "維持舊 Access 單機", "必思 BuSys ERP"],
        [
            ["上線時間", "長", "短但無 Web", "中短、可漸進"],
            ["流程契合", "需大量改流程", "高", "高（沿用設定）"],
            ["Web／移動", "有", "無", "有"],
            ["客製成本", "高", "中", "中低（配置為主）"],
            ["資料主權", "視合約", "完全自主", "完全自主、可地端"],
        ],
        [2.2, 3.1, 3.35, 3.8],
    )
    hl = s.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(9.05), Inches(1.12), Inches(3.95), Inches(5.35)
    )
    hl.fill.background()
    hl.line.color.rgb = GOLD
    hl.line.width = Pt(2.5)

    section_slide(prs, "PART 05", "建議下一步")

    s = blank_slide(prs)
    title_bar(s, "建議下一步", "可控風險的推進路徑")
    flow_steps(
        s,
        [
            ("PoC\n2 週", "1 公司\n3 支核心作業\n桌面＋Web"),
            ("Demo\n30 分鐘", "登入→選單\n查詢→報表\n附件"),
            ("決策", "試點部門\n部署模式\n預算與培訓"),
        ],
        top=1.55,
    )
    bullets(
        s,
        [
            "試點建議作業：銷售／採購／ARAP（可依貴司實際調整）。",
            "成功標準：同一筆資料桌面與 Web 一致、關鍵報表可 PDF 輸出。",
            "必思 BuSys — 讓既有 ERP 智慧化，讓管理層隨時在線。",
        ],
        top=3.55,
        size=18,
    )

    s = blank_slide(prs)
    title_bar(s, "謝謝", "Q & A")
    tb = s.shapes.add_textbox(Inches(0.8), Inches(2.8), Inches(11.5), Inches(2))
    r = tb.text_frame.paragraphs[0].add_run()
    r.text = "必思企業系統 BuSys ERP"
    _font(r, 36, True, NAVY)
    p2 = tb.text_frame.add_paragraph()
    r2 = p2.add_run()
    r2.text = "歡迎討論試點範圍與時程"
    _font(r2, 22, False, GRAY)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(OUT))
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"已產生：{path}")
