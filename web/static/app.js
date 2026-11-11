/**
 * 企業管理系統 Web 前端 — 對齊 Windows WorkPage / RecordDetailPage 工作流程
 */
(function () {
  "use strict";

  const TOKEN_KEY = "wolee_web_token";
  const USER_KEY = "wolee_web_user";
  const MENU_MODE_KEY = "wolee_menu_mode";
  const MENU_MODE_DEFAULT = "TREE";
  const THEME_KEY = "wolee_ui_theme";
  const THEME_DEFAULT = "fusion_blue";
  const FONT_PT_KEY = "wolee_ui_font_pt";
  const FONT_PT_DEFAULT = { gridCell: 10, gridHeader: 11, formLabel: 12, formEditor: 11 };
  const FONT_PT_MIN = 6;
  const FONT_PT_MAX = 28;
  const FORM_LAYOUT_KEY = "wolee_form_layout_mode";
  const FORM_LAYOUT_DEFAULT = "default";
  const FORM_LAYOUT_PLANNED = "planned";
  const TAB_TITLE_COLORS = [
    "#1B4F72",
    "#117A65",
    "#9A7D0A",
    "#922B21",
    "#5B2C6F",
    "#1A5276",
    "#B9770E",
    "#196F3D",
    "#6C3483",
    "#A04000",
  ];

  function tabTitleColor(index) {
    const i = Math.max(0, Number(index) || 0);
    return TAB_TITLE_COLORS[i % TAB_TITLE_COLORS.length];
  }
  const THEME_OPTIONS = [
    { id: "fusion_blue", labelChn: "Fusion 科技風（預設）", labelEng: "Fusion Blue (default)" },
    { id: "soft_green", labelChn: "柔和綠", labelEng: "Soft Green" },
    { id: "soft_purple", labelChn: "淡紫", labelEng: "Soft Purple" },
    { id: "warm_gray", labelChn: "暖灰", labelEng: "Warm Gray" },
    { id: "mint", labelChn: "薄荷綠", labelEng: "Mint" },
    { id: "daylight", labelChn: "日光", labelEng: "Daylight" },
  ];
  const MENU_MODE_OPTIONS = [
    { id: "TREE", labelChn: "樹狀 TreeView", labelEng: "TreeView" },
    { id: "ICON_GRID", labelChn: "圖示 ImageListView", labelEng: "ImageListView" },
    { id: "LIST", labelChn: "列表 ListMenu", labelEng: "ListMenu" },
    { id: "TOOLBOX", labelChn: "折疊 ToolBox", labelEng: "ToolBox" },
    { id: "TABS", labelChn: "分頁 TabsMenu", labelEng: "TabsMenu" },
  ];

  function loadFontPt() {
    try {
      const raw = JSON.parse(localStorage.getItem(FONT_PT_KEY) || "null");
      if (raw && typeof raw === "object") {
        return {
          gridCell: Number(raw.gridCell) || FONT_PT_DEFAULT.gridCell,
          gridHeader: Number(raw.gridHeader) || FONT_PT_DEFAULT.gridHeader,
          formLabel: Number(raw.formLabel) || FONT_PT_DEFAULT.formLabel,
          formEditor: Number(raw.formEditor) || FONT_PT_DEFAULT.formEditor,
        };
      }
    } catch (_) {}
    return { ...FONT_PT_DEFAULT };
  }

  function saveFontPt(s) {
    localStorage.setItem(FONT_PT_KEY, JSON.stringify(s));
  }

  function applyFontPtToDocument() {
    const s = loadFontPt();
    const root = document.documentElement.style;
    root.setProperty("--grid-cell-pt", String(s.gridCell));
    root.setProperty("--grid-header-pt", String(s.gridHeader));
    root.setProperty("--form-label-pt", String(s.formLabel));
    root.setProperty("--form-editor-pt", String(s.formEditor));
  }

  function clampFontPt(v, fallback) {
    const n = Number(v);
    if (!Number.isFinite(n)) return fallback;
    return Math.max(FONT_PT_MIN, Math.min(FONT_PT_MAX, Math.round(n)));
  }

  function bumpFontPt(kind, delta) {
    const s = loadFontPt();
    if (kind === "grid") {
      s.gridCell = clampFontPt(s.gridCell + delta, FONT_PT_DEFAULT.gridCell);
      s.gridHeader = clampFontPt(s.gridHeader + delta, FONT_PT_DEFAULT.gridHeader);
    } else {
      s.formLabel = clampFontPt(s.formLabel + delta, FONT_PT_DEFAULT.formLabel);
      s.formEditor = clampFontPt(s.formEditor + delta, FONT_PT_DEFAULT.formEditor);
    }
    saveFontPt(s);
    applyFontPtToDocument();
  }

  function getFormLayoutMode() {
    const v = String(localStorage.getItem(FORM_LAYOUT_KEY) || FORM_LAYOUT_DEFAULT).trim().toLowerCase();
    return v === FORM_LAYOUT_PLANNED ? FORM_LAYOUT_PLANNED : FORM_LAYOUT_DEFAULT;
  }

  function setFormLayoutMode(mode) {
    const m = String(mode || "").trim().toLowerCase() === FORM_LAYOUT_PLANNED
      ? FORM_LAYOUT_PLANNED
      : FORM_LAYOUT_DEFAULT;
    localStorage.setItem(FORM_LAYOUT_KEY, m);
    return m;
  }

  function loadTheme() {
    const v = (localStorage.getItem(THEME_KEY) || THEME_DEFAULT).trim();
    return THEME_OPTIONS.some((x) => x.id === v) ? v : THEME_DEFAULT;
  }

  function applyTheme(name) {
    const id = THEME_OPTIONS.some((x) => x.id === name) ? name : THEME_DEFAULT;
    localStorage.setItem(THEME_KEY, id);
    if (id === THEME_DEFAULT) document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", id);
  }

  function closeAllMenubarMenus() {
    document.querySelectorAll(".menubar-item.open").forEach((el) => el.classList.remove("open"));
  }

  function menubarDropdownHtml(actions) {
    return `<div class="menubar-dropdown" role="menu">${actions
      .map((a) => {
        if (a === "-") return `<div class="menubar-sep" role="separator"></div>`;
        const active = a.active ? " is-active" : "";
        const dis = a.disabled ? " disabled" : "";
        return `<button type="button" class="menubar-action${active}" role="menuitem"${dis} data-menu-act="${escapeHtml(
          a.act || ""
        )}" data-menu-arg="${escapeHtml(a.arg || "")}">${escapeHtml(a.label || "")}</button>`;
      })
      .join("")}</div>`;
  }

  function menubarItemHtml(label, actions) {
    return `<div class="menubar-item">
      <button type="button" class="menubar-btn" aria-haspopup="true" aria-expanded="false">${escapeHtml(label)}</button>
      ${menubarDropdownHtml(actions)}
    </div>`;
  }

  function buildMainMenubarHtml() {
    const mode = loadMenuMode();
    const theme = loadTheme();
    const langActs = [
      { act: "lang", arg: "CHN", label: "中文", active: currentLang === "CHN" },
      { act: "lang", arg: "ENG", label: "English", active: currentLang === "ENG" },
    ];
    const styleActs = MENU_MODE_OPTIONS.map((m) => ({
      act: "menu-mode",
      arg: m.id,
      label: currentLang === "CHN" ? m.labelChn : m.labelEng,
      active: mode === m.id,
    }));
    const themeActs = THEME_OPTIONS.map((th) => ({
      act: "theme",
      arg: th.id,
      label: currentLang === "CHN" ? th.labelChn : th.labelEng,
      active: theme === th.id,
    }));
    const viewActs =
      currentLang === "CHN"
        ? [
            { act: "font", arg: "grid-plus", label: "Grid 字體 +1pt（含標題列）" },
            { act: "font", arg: "grid-minus", label: "Grid 字體 -1pt（含標題列）" },
            "-",
            { act: "font", arg: "form-plus", label: "表單字體 +1pt" },
            { act: "font", arg: "form-minus", label: "表單字體 -1pt" },
          ]
        : [
            { act: "font", arg: "grid-plus", label: "Grid font +1pt (incl. header)" },
            { act: "font", arg: "grid-minus", label: "Grid font -1pt (incl. header)" },
            "-",
            { act: "font", arg: "form-plus", label: "Form font +1pt" },
            { act: "font", arg: "form-minus", label: "Form font -1pt" },
          ];
    const dbActs = [
      {
        act: "db-info",
        arg: "access",
        label: currentLang === "CHN" ? "使用 Access（由伺服器設定）" : "Use Access (server configured)",
      },
      {
        act: "db-info",
        arg: "sqlite",
        label: currentLang === "CHN" ? "使用 SQLite（由伺服器設定）" : "Use SQLite (server configured)",
      },
    ];
    const ifaceActs = [
      {
        act: "switch-desktop",
        arg: "",
        label: t("switchDesktop"),
      },
    ];
    return (
      menubarItemHtml(t("menuLang"), langActs) +
      menubarItemHtml(t("menuStyle"), styleActs) +
      menubarItemHtml(t("menuTheme"), themeActs) +
      menubarItemHtml(t("menuView"), viewActs) +
      menubarItemHtml(t("menuDatabase"), dbActs) +
      menubarItemHtml(t("menuInterface"), ifaceActs) +
      `<div class="menubar-item">
      <button type="button" class="menubar-btn menubar-direct" data-menu-act="open-ai" data-menu-arg="" title="${escapeHtml(
        t("aiOpen")
      )}">AI</button>
    </div>`
    );
  }

  async function handleMenubarAction(act, arg) {
    if (act === "lang") {
      if (!arg || arg === currentLang) return;
      currentLang = arg;
      refreshTopbarI18n();
      try {
        await api("/settings/language", {
          method: "POST",
          body: JSON.stringify({ lang: currentLang }),
        });
        await refreshMenu();
        for (const tab of openTabs.filter((x) => x.type === "work")) {
          await loadWorkData(tab, { asFilter: tab.filtered });
        }
        renderTabs();
      } catch (err) {
        showAlert(err.message);
      }
      return;
    }
    if (act === "menu-mode") {
      saveMenuMode(arg || MENU_MODE_DEFAULT);
      renderMenu();
      refreshTopbarI18n();
      return;
    }
    if (act === "theme") {
      applyTheme(arg || THEME_DEFAULT);
      refreshTopbarI18n();
      renderTabs();
      return;
    }
    if (act === "font") {
      const parts = String(arg || "").split("-");
      if (parts.length === 2) bumpFontPt(parts[0], parts[1] === "plus" ? 1 : -1);
      return;
    }
    if (act === "db-info") {
      showAlert(
        currentLang === "CHN"
          ? "Web 介面使用伺服器啟動時設定的資料庫，請在伺服器端切換 Access／SQLite。"
          : "Web uses the server-configured database. Switch Access/SQLite on the server."
      );
      return;
    }
    if (act === "open-ai") {
      openAiTab();
      return;
    }
    if (act === "switch-desktop") {
      try {
        const ui = await api("/settings/ui", { public: true });
        const msg =
          ui.can_switch_desktop && ui.switch_desktop_hint
            ? ui.switch_desktop_hint
            : ui.switch_desktop_hint || t("switchDesktopHint");
        showCopyableMessage(t("switchDesktop"), msg);
      } catch (_) {
        showCopyableMessage(t("switchDesktop"), t("switchDesktopHint"));
      }
    }
  }

  function bindMainMenubar() {
    const host = $("#menubar-menus");
    if (!host || host.dataset.bound === "1") return;
    host.dataset.bound = "1";
    host.addEventListener("click", (e) => {
      const actionBtn = e.target.closest(".menubar-action");
      if (actionBtn) {
        e.preventDefault();
        e.stopPropagation();
        const act = actionBtn.dataset.menuAct || "";
        const arg = actionBtn.dataset.menuArg || "";
        closeAllMenubarMenus();
        handleMenubarAction(act, arg).catch((err) => showAlert(err?.message || String(err)));
        return;
      }
      const btn = e.target.closest(".menubar-btn");
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      if (btn.classList.contains("menubar-direct")) {
        closeAllMenubarMenus();
        const act = btn.dataset.menuAct || "";
        const arg = btn.dataset.menuArg || "";
        handleMenubarAction(act, arg).catch((err) => showAlert(err?.message || String(err)));
        return;
      }
      const item = btn.closest(".menubar-item");
      const wasOpen = item?.classList.contains("open");
      closeAllMenubarMenus();
      if (item && !wasOpen) {
        item.classList.add("open");
        btn.setAttribute("aria-expanded", "true");
      }
    });
    // 對齊桌面：已展開任一選單時，滑過其他選單標題會切換展開
    host.addEventListener("mouseover", (e) => {
      const item = e.target.closest(".menubar-item");
      if (!item || !host.querySelector(".menubar-item.open")) return;
      if (item.classList.contains("open")) return;
      if (item.querySelector(".menubar-direct")) return;
      closeAllMenubarMenus();
      item.classList.add("open");
      item.querySelector(".menubar-btn")?.setAttribute("aria-expanded", "true");
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest("#main-menubar")) closeAllMenubarMenus();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeAllMenubarMenus();
    });
  }

  function refreshTopbarI18n() {
    const host = $("#menubar-menus");
    if (host) host.innerHTML = buildMainMenubarHtml();
    bindMainMenubar();
    const sideTitle = $("#sidebar-title");
    if (sideTitle) sideTitle.textContent = t("mainMenu");
    setButtonIcon($("#btn-reload"), "convert_db", t("reloadMeta"), t("reloadMetaTitle"), {
      topbar: false,
    });
    if ($("#btn-reload")) {
      $("#btn-reload").classList.add("menubar-corner-btn");
      $("#btn-reload").classList.remove("topbar-btn");
    }
    setButtonIcon($("#btn-logout"), "exit", t("exitApp"), null, { topbar: false });
    if ($("#btn-logout")) {
      $("#btn-logout").classList.add("menubar-corner-btn");
      $("#btn-logout").classList.remove("topbar-btn");
    }
    setButtonIcon($("#btn-ai"), "ai", "AI", t("aiOpen"), { topbar: false });
    if ($("#btn-ai")) {
      $("#btn-ai").classList.add("menubar-corner-btn");
      $("#btn-ai").classList.remove("topbar-btn", "btn-icon-only");
    }
    setButtonIcon($("#btn-ai-side"), "ai", "AI", t("aiOpen"), { topbar: false });
    if ($("#btn-ai-side")) {
      $("#btn-ai-side").classList.add("sidebar-ai-btn");
      $("#btn-ai-side").classList.remove("btn-icon-only");
    }
  }

  function mountSystemFontToolbar() {
    // 字體調整已併入功能表列「檢視 View」，保留空函式相容舊呼叫
  }

  const I18N = {
    CHN: {
      searchLabel: "搜尋:",
      search: "搜尋",
      filter: "過濾",
      add: "新增",
      edit: "更改",
      del: "刪除",
      copy: "複製",
      print: "列印",
      refreshData: "刷新資料",
      exit: "離開",
      navFirst: "首筆",
      navPrev: "上筆",
      navNext: "下筆",
      navLast: "末筆",
      recordNav: (c, t) => (c != null && c > 0 ? `${c}/${t}` : `-/${t}`),
      save: "儲存",
      cancel: "取消",
      runQueryTitle: "執行查詢",
      runQuerySql: "SQL 指令",
      runQuerySqlHint: "輸入 SELECT／UPDATE／INSERT／DELETE …",
      runQueryRun: "執行",
      runQueryExport: "匯出 Excel",
      runQueryLookup: "查閱",
      runQueryConnect: "連線",
      runQueryExit: "離開",
      runQueryClearSearch: "清除",
      runQueryDb: "資料庫:",
      runQueryFile: "檔案:",
      runQueryHost: "主機:",
      runQueryPort: "連接埠:",
      runQueryDbName: "資料庫名:",
      runQueryUser: "使用者:",
      runQueryPassword: "密碼:",
      detailSuffix: "明細",
      addSuffix: "新增",
      copySuffix: "複製",
      formData: "資 料",
      formDetail: "明 細",
      lookup: "查找",
      formLayoutPlanned: "規劃介面",
      formLayoutDefault: "預設介面",
      formLayoutTipPlanned: "切換為上標下欄規劃輸入介面（3×5／5×5）",
      formLayoutTipDefault: "切換為左標右欄預設輸入介面",
      keyAssignTitle: "新增編號",
      keyAssignHint: "請輸入或選擇單據編號後按儲存；取消則返回輸入資料介面。",
      keyAssignEmpty: "請輸入編號。",
      savedNumberTitle: "儲存成功",
      savedNumberMsg: "編號已儲存：{label} = {value}",
      selectRow: "請先選取一筆記錄。",
      confirmDel: "確定要刪除所選記錄嗎？",
      deleted: "已刪除。",
      delFail: "刪除失敗。",
      noPrint: "無資料可列印。",
      printTitle: "列印報表",
      printPrinter: "印表機:",
      printReport: "報表:",
      printFromNo: (label) => `由${label}編號:`,
      printToNo: (label) => `至${label}編號:`,
      printFromDate: "由日期:",
      printToDate: "至日期:",
      printPreview: "預覽",
      printBtn: "列印",
      printExportPdf: "匯出 PDF",
      printExportXlsx: "匯出 XLSX",
      printExportDocx: "匯出 DOCX",
      printEmail: "電郵",
      printExit: "離開",
      printNoReport: "沒有可列印的報表 !\nNo Report Print !",
      printPickRecord: "選擇記錄",
      printPickFilter: "輸入關鍵字過濾（GRID）",
      printPickOk: "確定",
      printPickCancel: "取消",
      printPickBtn: "選取",
      printDatePickBtn: "選取日期",
      printClearDate: "清除日期",
      printPickNoKey: "找不到可選擇的主編號欄位。",
      printPickNoData: "目前沒有可選擇的資料。",
      printSuccess: (msg) => msg || "完成。",
      printFail: "列印失敗。",
      printPreviewFail: "預覽失敗。",
      printPreviewTitle: "列印預覽",
      printPreviewOpenWindow: "新視窗",
      printPreviewClose: "關閉預覽",
      printPreviewBlocked: "無法開啟新視窗，已改在本頁顯示預覽。",
      printPreviewPdfNav: (c, t) => `${c} / ${t}`,
      printExportFail: "匯出失敗。",
      printExportOk: (name) => `已匯出：${name}`,
      printEmailCopied: "報表全文已複製到剪貼簿，請在郵件本文按 Ctrl+V 貼上。",
      printDesktop: "完整列印預覽（含報表選擇）請使用桌面版「列印預覽」按鈕。",
      emptyMenu: "請從左側主選單選擇作業",
      addTitle: (t) => `新增 - ${t}`,
      editTitle: (t) => `${t}`,
      noData: "無資料",
      confirmTxDel: "刪除此列？",
      txMoveUp: "上移",
      txMoveDown: "下移",
      txSaveFail: "主檔已儲存，但交易明細儲存失敗：",
      fontGridMinus: "Grid字體−(含標題)",
      fontGridPlus: "Grid字體+(含標題)",
      fontFormMinus: "表單字體−",
      fontFormPlus: "表單字體+",
      fontGridMinusTitle: "Grid 字體減少（含標題列）",
      fontGridPlusTitle: "Grid 字體增加（含標題列）",
      fontFormMinusTitle: "表單字體減少",
      fontFormPlusTitle: "表單字體增加",
      langLabel: "語言",
      menuLang: "語言 Language",
      menuStyle: "主選單樣式",
      menuTheme: "主題 Theme",
      menuView: "檢視 View",
      menuDatabase: "資料庫",
      menuInterface: "介面 Interface",
      mainMenu: "主選單",
      reloadMeta: "重新載入",
      reloadMetaTitle: "重新載入資料字典與主選單",
      exitApp: "離開",
      switchDesktop: "桌面介面",
      switchDesktopBoth: "桌面程式已在本機執行，請用工作列或 Alt+Tab 切換至桌面視窗。",
      switchDesktopHint:
        "若要與 Windows 桌面介面隨時切換，請在本機執行：\n  python launcher.py --mode both\n啟動後可用桌面選單「介面 → 開啟 Web 介面」與本頁互換。",
      logout: "登出",
      attachment: "附件",
      otherDefault: "其他",
      attachSelectRow: "請先選取一筆記錄。",
      attachPath: (p) => `附件目錄：\n${p}`,
      attachNoFiles: (folder, key) => `在以下目錄找不到符合「${key}」的附件：\n${folder}`,
      attachNoFilesSimple: "找不到附件。",
      notice: "訊息",
      msgCopyHint: "以下內容可選取、Ctrl+C 複製，或按「複製」按鈕。",
      msgCopyBtn: "複製",
      msgCopied: "已複製到剪貼簿。",
      gridCopyNoSelection: "請先選取要複製的列（右鍵、Ctrl+點擊多選、Shift+範圍選、Ctrl+A 全選）。",
      gridCopied: (n) => `已複製 ${n} 列到剪貼簿（含表頭，Tab 分隔，可貼到 Excel）。`,
      gridCopyTitle: "Grid 資料",
      gridCtxCopy: (n) => `複製到剪貼簿 (${n} 列)`,
      gridCtxCopyAll: "複製全部到剪貼簿",
      gridCtxSelectAll: "全選",
      msgOk: "確定",
      attachPreview: "附件預覽",
      attachPickHint: "找到多個附件，請選擇要顯示的檔案：",
      attachClose: "關閉",
      arapTitleAR: "應收清賬",
      arapTitleAP: "應付清賬",
      arapAuto: "自動清賬",
      arapVouKey: "傳票編號",
      arapSettleDate: "清賬日期",
      arapPartyAR: "顧客編號-名稱",
      arapPartyAP: "供應商編號-名稱",
      arapSettleAmt: "清賬金額",
      arapExchDiff: "兌匯差額:",
      arapTotal: "合計:",
      arapRemain: "尚餘清賬金額:",
      arapSelectVoucher: "請先選取一筆傳票記錄。",
      arapSaved: "清賬已儲存。",
      rpTitleAR: "收款",
      rpTitleAP: "付款",
      rpDocGroup: "發票資料",
      rpPayGroup: "收付款資料",
      rpInvNo: "發票編號",
      rpInvDate: "日期",
      rpPartyKeyAR: "顧客編號",
      rpPartyNameAR: "顧客名稱",
      rpPartyKeyAP: "供應商編號",
      rpPartyNameAP: "供應商名稱",
      rpCurrency: "貨幣",
      rpRate: "滙率",
      rpNetAmtAR: "發票金額",
      rpNetAmtAP: "購貨發票金額",
      rpPaidAmt: "已付金額",
      rpBalance: "尚餘金額",
      rpPayAmount: "付款金額",
      rpPayDate: "付款日期",
      rpPayMethod: "付款方式",
      rpBank: "銀行",
      rpCheque: "支票編號",
      rpChqDate: "支票日期",
      rpRemark: "備註",
      rpDebitAc: "借項賬戶編號",
      rpCreditAc: "貸項賬戶編號",
      rpSelectRow: "請先選取一筆記錄。",
      rpSavedPrefix: "編號已儲存：VOU_KEY = ",
      partyQueryTitleAR: "顧客查詢",
      partyQueryTitleAP: "供應商查詢",
      partyQueryCustNo: "顧客-供應商編號",
      partyQueryVendNo: "顧客-供應商編號",
      partyQueryName: "名稱",
      partyQueryContact: "聯絡人",
      partyQueryTel: "電話#",
      partyQueryMobile: "手提#",
      partyQueryCredit: "信用額",
      partyQueryRemainCredit: "剩餘信用額",
      partyQueryDateFrom: "由日期",
      partyQueryDateTo: "至日期",
      partyQueryApplyDates: "套用",
      partyQueryTxKind: "交易類型",
      partyQueryKindAll: "全部",
      partyQueryKindInv: "發票(INVOICE)",
      partyQueryKindRec: "收款(VOUCHER/RJ)",
      partyQueryKindPur: "購貨發票(PURCHASE)",
      partyQueryKindPay: "付款(VOUCHER/PJ)",
      partyQueryColDate: "日期",
      partyQueryColType: "交易類別",
      partyQueryColKey: "交易編號",
      partyQueryColCurr: "貨幣",
      partyQueryColRate: "滙率",
      partyQueryColInv: "發票金額",
      partyQueryColPaid: "已收(付)金額",
      partyQueryColRecv: "收(付)款金額",
      partyQueryColSettle: "清賬金額",
      partyQuerySettledTotal: "已清賬金額",
      partyQueryInvTotals: "發票合計",
      partyQueryPurTotals: "購貨發票合計",
      partyQueryAmt: "金額",
      partyQueryPayAmt: "付款金額",
      partyQueryTotal: "合計",
      partyQuerySearchMiss: "找不到符合的資料。",
      partyQueryClearDate: "清除日期",
      stockQueryTitle: "存貨查詢",
      stockQueryNo: "存貨編號",
      stockQueryCat: "存貨分類",
      stockQueryBrand: "牌子名稱",
      stockQueryModel: "型號",
      stockQueryDesc: "說明",
      stockQueryTxKind: "交易類型",
      stockQueryKindPur: "購貨(PURCHASE)",
      stockQueryKindInv: "銷貨(INVOICE)",
      stockQueryKindAdj: "存貨調整(STKADJ)",
      stockQueryKindTri: "存貨轉倉(TRANSFER)",
      stockQueryColDate: "日期",
      stockQueryColType: "交易類別",
      stockQueryColKey: "交易編號",
      stockQueryColQty: "數量",
      stockQueryColUnit: "單位",
      stockQueryColWeight: "重量",
      stockQueryColWgtUnit: "重量單位",
      stockQueryColWh: "貨倉",
      stockQueryColPrice: "單價",
      stockQueryColAmt: "金額",
      stockQueryColUnitCost: "單位成本",
      stockQueryColCostAmt: "成本金額",
      stockQueryPurTotals: "購貨",
      stockQueryInvTotals: "發票",
      stockQueryAdjTotals: "存貨調整",
      stockQueryTriTotals: "存貨轉倉",
      stockQueryQty: "數量",
      stockQueryWeight: "重量",
      stockQueryAmt: "金額",
      menuModeTree: "樹狀",
      menuModeIcon: "圖示",
      menuModeList: "列表",
      menuModeToolbox: "折疊",
      menuModeTabs: "分頁",
      menuEmpty: "尚無可執行程式（請確認 program／MAINMENU 與權限）。",
      menuDblClickHint: "雙擊開啟作業",
      otherNotConfigured: "此功能尚未設定實作內容。",
      queryUnsupported: "不支援此查詢類型（僅支援顧客／供應商查詢、存貨查詢、賬戶查詢）。",
      accountQueryTitle: "賬戶查詢",
      accountQueryNo: "賬戶編號",
      accountQueryParent: "上層賬戶編號",
      accountQueryType: "賬戶類別",
      accountQueryLevel: "賬戶級別",
      accountQueryName: "賬戶名稱",
      accountQueryTxKind: "交易類型",
      accountQueryKindAcc: "賬戶",
      accountQueryColDate: "日期",
      accountQueryColVou: "傳票編號",
      accountQueryColCurr: "貨幣",
      accountQueryColRate: "滙率",
      accountQueryColDr: "借項金額",
      accountQueryColCr: "貸項金額",
      accountQueryColRemark: "備註",
      accountQueryTotals: "合計",
      dataImport: "資料匯入",
      dataImportTitle: "資料匯入",
      dataImportHint: "來源：TRANSFER；目標：公司庫。以下拉選單選擇 PURCHASE／INVOICE／STOCK；各類型可選不同來源資料夾。採購／發票列出 POSTED=FALSE 主檔可複選；TX_TYPE 空白預設 GS-，TX_NO 8 位補零，貨幣 HKD、匯率 1。",
      dataImportKind: "匯入類型",
      dataImportFolder: "來源資料夾（含 TRANSFER.sqlite；各類型可選不同資料夾）",
      dataImportFolderBrowse: "瀏覽…",
      dataImportFolderApply: "套用",
      dataImportFolderPick: "選擇來源資料夾",
      dataImportFolderUp: "上一層",
      dataImportFolderUse: "使用此資料夾",
      dataImportFolderHasDb: "含 TRANSFER.sqlite",
      dataImportFolderNoDb: "此資料夾尚無 TRANSFER.sqlite",
      dataImportPending: "待匯入主檔 GRID",
      dataImportPendingEmpty: "TRANSFER 沒有 POSTED=FALSE 的未處理資料。",
      dataImportSource: "讀取來源",
      dataImportStockHint: "庫存匯入：將 TRANSFER.STK 資料寫入公司庫 STOCK。",
      dataImportSelectAll: "全選",
      dataImportSelectNone: "全不選",
      dataImportSelectRows: "請在 GRID 中勾選要匯入的未處理資料。",
      dataImportReload: "重新載入清單",
      dataImportReloading: "正在重新讀取 TRANSFER…",
      dataImportRun: "執行匯入",
      dataImportSuccess: "匯入完成。",
      dataImportFail: "匯入失敗。",
      aiTab: "AI",
      aiOpen: "AI 助理",
      aiHint: "可問日常問題、搜尋已上傳文件、分析/統計需求，或下指令操作系統。口語也可以，例如：開啟發票、open stock 查詢A02、open 顧客-供應商查詢:GSC33SATAL1、查一下編號。",
      aiSend: "送出",
      aiPlaceholder: "輸入問題或指令，例如：open stock 查詢A02、開啟存貨查詢 A02、open 顧客-供應商查詢:GSC33SATAL1…",
      aiDocs: "私人文件",
      aiUpload: "上傳",
      aiDeleteDoc: "刪除",
      aiNoDocs: "尚未上傳文件。",
      aiWelcome: "您好，我是系統 AI 助理。\n• 解答日常問題\n• 上傳私人文件並在文件中找資料\n• 分析及統計您的需求\n• 輸入編號或關鍵字，找出資料庫中的所有相關資料\n• 操作本系統：開啟資料表、關閉 TAB、新增／更改／刪除／複製／離開／列印（預覽）／查詢／搜尋\n\n口語範例：\n• open 顧客-供應商查詢:GSC33SATAL1\n• 開啟顧客供應商查詢 GSC33SATAL1\n• 查一下 GSC33SATAL1\n• 顯示 GSC33SATAL1 的顧客資料",
      aiNeedWork: "請先開啟資料表。",
      aiSending: "正在思考…",
      aiClearChat: "清除對話",
      aiClearConfirm: "確定清除所有對話？",
      aiSettings: "AI 設定",
      aiCommandSave: "儲存指令",
      aiCommandOpen: "查找指令",
      aiCommandSaved: "已儲存指令至 AI_COMMAND。",
      aiCommandEmpty: "請先在輸入框輸入指令，或先送出一則指令。",
      aiSettingsTitle: "AI 設定",
      aiSettingsModel: "模型",
      aiSettingsBaseUrl: "API 端點",
      aiSettingsApiKey: "API Key",
      aiSettingsApiKeyPh: "留空表示不變更已儲存的 Key",
      aiSettingsKeyHint: (h) => (h ? `已設定 Key：${h}` : "尚未設定 Key"),
      aiSettingsEnvKey: "目前使用伺服器環境變數的 API Key。",
      aiSettingsClearKey: "清除已儲存的 API Key",
      aiSettingsSaved: "設定已儲存（全系統共用）。",
      aiSettingsShared: "此設定全系統共用，儲存後所有使用者皆可使用。",
      aiSettingsModelCustom: "自訂模型",
      aiSettingsModelCustomOpt: "自訂…",
      aiSettingsModelCustomPh: "輸入模型名稱",
      aiSettingsModelRequired: "請選擇或輸入模型。",
    },
    ENG: {
      searchLabel: "Search:",
      search: "Search",
      filter: "Filter",
      add: "Add",
      edit: "Edit",
      del: "Delete",
      copy: "Copy",
      print: "Print",
      refreshData: "Refresh",
      exit: "Exit",
      navFirst: "First",
      navPrev: "Prev",
      navNext: "Next",
      navLast: "Last",
      recordNav: (c, t) => (c != null && c > 0 ? `${c}/${t}` : `-/${t}`),
      save: "Save",
      cancel: "Cancel",
      runQueryTitle: "Execute Query",
      runQuerySql: "SQL command",
      runQuerySqlHint: "Enter SELECT / UPDATE / INSERT / DELETE …",
      runQueryRun: "Run",
      runQueryExport: "Export Excel",
      runQueryLookup: "Lookup",
      runQueryConnect: "Connect",
      runQueryExit: "Exit",
      runQueryClearSearch: "Clear",
      runQueryDb: "Database:",
      runQueryFile: "File:",
      runQueryHost: "Host:",
      runQueryPort: "Port:",
      runQueryDbName: "Database:",
      runQueryUser: "User:",
      runQueryPassword: "Password:",
      detailSuffix: "Detail",
      addSuffix: "Add",
      copySuffix: "Copy",
      formData: "Data",
      formDetail: "Detail",
      lookup: "Lookup",
      formLayoutPlanned: "Planned UI",
      formLayoutDefault: "Default UI",
      formLayoutTipPlanned: "Switch to planned top-label form layout (3×5 / 5×5)",
      formLayoutTipDefault: "Switch to default left-label form layout",
      keyAssignTitle: "New document number",
      keyAssignHint: "Enter or pick a document number, then Save; Cancel returns to the form.",
      keyAssignEmpty: "Please enter a document number.",
      savedNumberTitle: "Saved",
      savedNumberMsg: "Saved number: {label} = {value}",
      selectRow: "Please select a record first.",
      confirmDel: "Delete selected record?",
      deleted: "Deleted.",
      delFail: "Delete failed.",
      noPrint: "No data to print.",
      printTitle: "Print Report",
      printPrinter: "Printer:",
      printReport: "Report:",
      printFromNo: (label) => `From ${label} no.:`,
      printToNo: (label) => `To ${label} no.:`,
      printFromDate: "From date:",
      printToDate: "To date:",
      printPreview: "Preview",
      printBtn: "Print",
      printExportPdf: "Export PDF",
      printExportXlsx: "Export XLSX",
      printExportDocx: "Export DOCX",
      printEmail: "Email",
      printExit: "Exit",
      printNoReport: "No Report Print !",
      printPickRecord: "Select record",
      printPickFilter: "Type to filter (grid)",
      printPickOk: "OK",
      printPickCancel: "Cancel",
      printPickBtn: "Select",
      printDatePickBtn: "Pick date",
      printClearDate: "Clear date",
      printPickNoKey: "Cannot find a key number column.",
      printPickNoData: "No records available.",
      printSuccess: (msg) => msg || "Done.",
      printFail: "Printing failed.",
      printPreviewFail: "Preview failed.",
      printPreviewTitle: "Print Preview",
      printPreviewOpenWindow: "New window",
      printPreviewClose: "Close preview",
      printPreviewBlocked: "Popup blocked; showing preview in this page.",
      printPreviewPdfNav: (c, t) => `${c} / ${t}`,
      printExportFail: "Export failed.",
      printExportOk: (name) => `Exported: ${name}`,
      printEmailCopied: "Full report copied to clipboard; paste with Ctrl+V in your mail app.",
      printDesktop: "For full print preview, use Desktop mode Print Preview.",
      emptyMenu: "Select a program from the main menu",
      addTitle: (t) => `Add - ${t}`,
      editTitle: (t) => t,
      noData: "No data",
      confirmTxDel: "Delete this row?",
      txMoveUp: "Move Up",
      txMoveDown: "Move Down",
      txSaveFail: "Master saved, but detail lines failed: ",
      fontGridMinus: "Grid − (header)",
      fontGridPlus: "Grid + (header)",
      fontFormMinus: "Form −",
      fontFormPlus: "Form +",
      fontGridMinusTitle: "Decrease grid font (incl. header row)",
      fontGridPlusTitle: "Increase grid font (incl. header row)",
      fontFormMinusTitle: "Decrease form font",
      fontFormPlusTitle: "Increase form font",
      langLabel: "Language",
      menuLang: "Language",
      menuStyle: "Main Menu Style",
      menuTheme: "Theme",
      menuView: "View",
      menuDatabase: "Database",
      menuInterface: "Interface",
      mainMenu: "Main Menu",
      reloadMeta: "Reload",
      reloadMetaTitle: "Reload data dictionary and main menu",
      exitApp: "Exit",
      switchDesktop: "Desktop",
      switchDesktopBoth: "Desktop app is running on this machine. Use the taskbar or Alt+Tab to switch.",
      switchDesktopHint:
        "To switch between Web and Desktop anytime, run on this machine:\n  python launcher.py --mode both\nThen use Desktop menu Interface → Open Web.",
      logout: "Logout",
      attachment: "Attachment",
      otherDefault: "Other",
      attachSelectRow: "Please select a record first.",
      attachPath: (p) => `Attachment folder:\n${p}`,
      attachNoFiles: (folder, key) => `No attachment matching "${key}" in:\n${folder}`,
      attachNoFilesSimple: "Attachment not found.",
      notice: "Message",
      msgCopyHint: "Select text, press Ctrl+C, or click Copy.",
      msgCopyBtn: "Copy",
      msgCopied: "Copied to clipboard.",
      gridCopyNoSelection: "Select row(s) to copy (right-click, Ctrl+click, Shift+range, Ctrl+A all).",
      gridCopied: (n) => `Copied ${n} row(s) with header (tab-separated, paste into Excel).`,
      gridCopyTitle: "Grid data",
      gridCtxCopy: (n) => `Copy to Clipboard (${n} row(s))`,
      gridCtxCopyAll: "Copy All to Clipboard",
      gridCtxSelectAll: "Select All",
      msgOk: "OK",
      attachPreview: "Attachment Preview",
      attachPickHint: "Multiple attachments found. Please select one:",
      attachClose: "Close",
      arapTitleAR: "A/R Settlement",
      arapTitleAP: "A/P Settlement",
      arapAuto: "Auto Settle",
      arapVouKey: "Voucher No.",
      arapSettleDate: "Settle Date",
      arapPartyAR: "Customer No.-Name",
      arapPartyAP: "Vendor No.-Name",
      arapSettleAmt: "Settle Amount",
      arapExchDiff: "Exchange Diff.:",
      arapTotal: "Total:",
      arapRemain: "Remain Settle:",
      arapSelectVoucher: "Please select a voucher record first.",
      arapSaved: "Settlement saved.",
      rpTitleAR: "Receipt",
      rpTitleAP: "Payment",
      rpDocGroup: "Document",
      rpPayGroup: "Payment",
      rpInvNo: "Invoice No.",
      rpInvDate: "Date",
      rpPartyKeyAR: "Customer No.",
      rpPartyNameAR: "Customer Name",
      rpPartyKeyAP: "Vendor No.",
      rpPartyNameAP: "Vendor Name",
      rpCurrency: "Currency",
      rpRate: "Rate",
      rpNetAmtAR: "Invoice Amount",
      rpNetAmtAP: "Purchase Amount",
      rpPaidAmt: "Paid Amount",
      rpBalance: "Balance",
      rpPayAmount: "Pay Amount",
      rpPayDate: "Pay Date",
      rpPayMethod: "Pay Method",
      rpBank: "Bank",
      rpCheque: "Cheque No.",
      rpChqDate: "Cheque Date",
      rpRemark: "Remark",
      rpDebitAc: "Debit A/C",
      rpCreditAc: "Credit A/C",
      rpSelectRow: "Please select a record first.",
      rpSavedPrefix: "Saved number: VOU_KEY = ",
      partyQueryTitleAR: "Customer Query",
      partyQueryTitleAP: "Vendor Query",
      partyQueryCustNo: "Cust/Vend No.",
      partyQueryVendNo: "Cust/Vend No.",
      partyQueryName: "Name",
      partyQueryContact: "Contact",
      partyQueryTel: "Tel.",
      partyQueryMobile: "Mobile",
      partyQueryCredit: "Credit Limit",
      partyQueryRemainCredit: "Remaining Credit",
      partyQueryDateFrom: "From date",
      partyQueryDateTo: "To date",
      partyQueryApplyDates: "Apply",
      partyQueryTxKind: "Type",
      partyQueryKindAll: "All",
      partyQueryKindInv: "Invoice (INVOICE)",
      partyQueryKindRec: "Receipt (VOUCHER/RJ)",
      partyQueryKindPur: "Purchase (PURCHASE)",
      partyQueryKindPay: "Payment (VOUCHER/PJ)",
      partyQueryColDate: "Date",
      partyQueryColType: "Type",
      partyQueryColKey: "Doc No.",
      partyQueryColCurr: "Curr.",
      partyQueryColRate: "Rate",
      partyQueryColInv: "Invoice Amt.",
      partyQueryColPaid: "Paid Amt.",
      partyQueryColRecv: "Recv/Pay Amt.",
      partyQueryColSettle: "Settled",
      partyQuerySettledTotal: "Settled Total",
      partyQueryInvTotals: "Invoice totals",
      partyQueryPurTotals: "Purchase totals",
      partyQueryAmt: "Amt",
      partyQueryPayAmt: "Payment",
      partyQueryTotal: "Total",
      partyQuerySearchMiss: "No matching row.",
      partyQueryClearDate: "Clear date",
      stockQueryTitle: "Stock Query",
      stockQueryNo: "Stock No.",
      stockQueryCat: "Category",
      stockQueryBrand: "Brand",
      stockQueryModel: "Model",
      stockQueryDesc: "Description",
      stockQueryTxKind: "Type",
      stockQueryKindPur: "Purchase (PURCHASE)",
      stockQueryKindInv: "Sales (INVOICE)",
      stockQueryKindAdj: "Adjustment (STKADJ)",
      stockQueryKindTri: "Transfer (TRANSFER)",
      stockQueryColDate: "Date",
      stockQueryColType: "Type",
      stockQueryColKey: "Doc No.",
      stockQueryColQty: "Qty",
      stockQueryColUnit: "Unit",
      stockQueryColWeight: "Weight",
      stockQueryColWgtUnit: "Wgt Unit",
      stockQueryColWh: "Loc",
      stockQueryColPrice: "Price",
      stockQueryColAmt: "Amount",
      stockQueryColUnitCost: "Unit Cost",
      stockQueryColCostAmt: "Cost Amt",
      stockQueryPurTotals: "Purchase",
      stockQueryInvTotals: "Invoice",
      stockQueryAdjTotals: "Adjustment",
      stockQueryTriTotals: "Transfer",
      stockQueryQty: "Qty",
      stockQueryWeight: "Weight",
      stockQueryAmt: "Amt",
      menuModeTree: "Tree",
      menuModeIcon: "Icons",
      menuModeList: "List",
      menuModeToolbox: "Toolbox",
      menuModeTabs: "Tabs",
      menuEmpty: "No programs available (check program/MAINMENU and permissions).",
      menuDblClickHint: "Double-click to open",
      otherNotConfigured: "This action is not configured yet.",
      queryUnsupported:
        "Unsupported query type (only customer/vendor, stock and account queries are supported).",
      accountQueryTitle: "Account Query",
      accountQueryNo: "Account No.",
      accountQueryParent: "Parent Acc.",
      accountQueryType: "Acc. Type",
      accountQueryLevel: "Acc. Level",
      accountQueryName: "Acc. Name",
      accountQueryTxKind: "Type",
      accountQueryKindAcc: "Account",
      accountQueryColDate: "Date",
      accountQueryColVou: "Voucher No.",
      accountQueryColCurr: "Curr.",
      accountQueryColRate: "Rate",
      accountQueryColDr: "Debit",
      accountQueryColCr: "Credit",
      accountQueryColRemark: "Remark",
      accountQueryTotals: "Total",
      dataImport: "Data Import",
      dataImportTitle: "Data Import",
      dataImportHint: "Source: TRANSFER; Destination: company DB. Use combo box for PURCHASE/INVOICE/STOCK; each kind may use a different source folder. Purchase/Invoice list POSTED=FALSE headers. Blank TX_TYPE→GS-, TX_NO 8 digits, currency HKD, rate 1.",
      dataImportKind: "Import type",
      dataImportFolder: "Source folder (with TRANSFER.sqlite; each kind may use a different folder)",
      dataImportFolderBrowse: "Browse…",
      dataImportFolderApply: "Apply",
      dataImportFolderPick: "Select source folder",
      dataImportFolderUp: "Up",
      dataImportFolderUse: "Use this folder",
      dataImportFolderHasDb: "Has TRANSFER.sqlite",
      dataImportFolderNoDb: "No TRANSFER.sqlite in this folder",
      dataImportPending: "Pending headers GRID",
      dataImportPendingEmpty: "No unposted rows in TRANSFER (POSTED=FALSE).",
      dataImportSource: "Source",
      dataImportStockHint: "Stock import: copy TRANSFER.STK into company STOCK.",
      dataImportSelectAll: "Select All",
      dataImportSelectNone: "Select None",
      dataImportSelectRows: "Please check unposted rows in the GRID to import.",
      dataImportReload: "Reload list",
      dataImportReloading: "Re-reading TRANSFER…",
      dataImportRun: "Run Import",
      dataImportSuccess: "Import completed.",
      dataImportFail: "Import failed.",
      aiTab: "AI",
      aiOpen: "AI Assistant",
      aiHint: "Ask in natural language: open invoice, search 1001, open customer/vendor query:GSC33SATAL1, look up GSC33SATAL1, show GSC33SATAL1 customer data…",
      aiSend: "Send",
      aiPlaceholder: "Ask or command, e.g. open invoice, customer query:GSC33SATAL1, look up GSC33SATAL1, search 1001, find all related records for INV001…",
      aiDocs: "Private files",
      aiUpload: "Upload",
      aiDeleteDoc: "Delete",
      aiNoDocs: "No files uploaded.",
      aiWelcome: "Hello. I can answer questions, search uploaded files, analyze needs, search related database records, and operate this system.\n\nExamples:\n• open customer/vendor query:GSC33SATAL1\n• look up GSC33SATAL1\n• show GSC33SATAL1 customer data\n• search 1001",
      aiNeedWork: "Please open a table first.",
      aiSending: "Thinking…",
      aiClearChat: "Clear chat",
      aiClearConfirm: "Clear all messages?",
      aiSettings: "AI Settings",
      aiCommandSave: "Save command",
      aiCommandOpen: "Lookup command",
      aiCommandSaved: "Command saved to AI_COMMAND.",
      aiCommandEmpty: "Enter a command in the input box, or send one first.",
      aiSettingsTitle: "AI Settings",
      aiSettingsModel: "Model",
      aiSettingsBaseUrl: "API base URL",
      aiSettingsApiKey: "API Key",
      aiSettingsApiKeyPh: "Leave blank to keep saved key",
      aiSettingsKeyHint: (h) => (h ? `Key set: ${h}` : "No key configured"),
      aiSettingsEnvKey: "Using server environment API key.",
      aiSettingsClearKey: "Clear saved API key",
      aiSettingsSaved: "Settings saved (system-wide).",
      aiSettingsShared: "These settings are system-wide and available to all users after saving.",
      aiSettingsModelCustom: "Custom model",
      aiSettingsModelCustomOpt: "Custom…",
      aiSettingsModelCustomPh: "Enter model id",
      aiSettingsModelRequired: "Please select or enter a model.",
    },
  };

  const GRID_VISIBLE_ROWS = 20;
  /** 明細 TX Grid 可視列數：對齊桌面 TxDetailGridPane._FIXED_VIEW_ROWS */
  const TX_VISIBLE_ROWS = 6;
  const ARAP_GRID_VISIBLE_ROWS = 15;
  const PARTY_QUERY_GRID_VISIBLE_ROWS = 15;

  let token = localStorage.getItem(TOKEN_KEY) || "";
  let currentUser = null;
  let menuGroups = [];
  let menuHint = "";
  let openTabs = [];
  let activeTabId = null;
  let currentLang = "CHN";
  let formModalState = null;
  let attachModalState = null;
  let arapModalState = null;
  let receiptPaymentModalState = null;
  let partyQueryModalState = null;
  let stockQueryModalState = null;
  let accountQueryModalState = null;

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const loginView = $("#login-view");
  const mainView = $("#main-view");

  function t(key, ...args) {
    const pack = I18N[currentLang] || I18N.CHN;
    const v = pack[key];
    return typeof v === "function" ? v(...args) : v;
  }

  const PUBLIC_API_PATHS = new Set([
    "/companies",
    "/auth/login",
    "/auth/last-company",
    "/health",
    "/settings/ui",
  ]);

  function apiErrorMessage(data, fallback) {
    if (!data || data.detail == null) return fallback;
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) {
      return data.detail.map((d) => d.msg || String(d)).join("；") || fallback;
    }
    return fallback;
  }

  function isPublicApiPath(path) {
    const p = path.startsWith("/") ? path : `/${path}`;
    return PUBLIC_API_PATHS.has(p);
  }

  async function api(path, options = {}) {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    const isPublic = options.public === true || isPublicApiPath(normalizedPath);
    const headers = {
      "Content-Type": "application/json",
      "Cache-Control": "no-cache",
      Pragma: "no-cache",
      ...(options.headers || {}),
    };
    if (token && options.omitAuth !== true) headers.Authorization = `Bearer ${token}`;
    const fetchOpts = { cache: "no-store", ...options, headers };
    const res = await fetch(`/api${normalizedPath}`, fetchOpts);
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
      if (!isPublic && token) {
        clearSession();
        showLogin();
      }
      throw new Error(apiErrorMessage(data, isPublic ? "登入失敗。" : "未登入或 session 已過期。"));
    }
    if (!res.ok) throw new Error(apiErrorMessage(data, res.statusText || "請求失敗"));
    return data;
  }

  function userMaySeeAttachFolder() {
    const gl = currentUser?.group_level;
    if (gl == null || gl === "") return false;
    const n = Number(gl);
    return !Number.isNaN(n) && n <= 3;
  }

  function formatAttachNotFoundMessage(folder, key) {
    if (userMaySeeAttachFolder()) {
      return t("attachNoFiles", folder || "", key || "");
    }
    return t("attachNoFilesSimple");
  }

  function closeMessageModal() {
    const el = $("#message-modal-overlay");
    if (el) el.remove();
  }

  async function copyTextForUser(text, textareaEl, statusEl) {
    const raw = String(text == null ? "" : text);
    if (textareaEl) {
      textareaEl.focus();
      textareaEl.select();
      try {
        if (document.execCommand("copy")) {
          if (statusEl) statusEl.textContent = t("msgCopied");
          return true;
        }
      } catch (_) {}
    }
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(raw);
        if (statusEl) statusEl.textContent = t("msgCopied");
        return true;
      } catch (_) {}
    }
    if (textareaEl) {
      textareaEl.focus();
      textareaEl.select();
    }
    return false;
  }

  async function copyTextToClipboard(text) {
    const raw = String(text == null ? "" : text);
    if (!raw) return false;
    if (navigator.clipboard && window.isSecureContext) {
      try {
        await navigator.clipboard.writeText(raw);
        return true;
      } catch (_) {}
    }
    const ta = document.createElement("textarea");
    ta.value = raw;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch (_) {
      document.body.removeChild(ta);
      return false;
    }
  }

  function escapeGridCellForTsv(value) {
    return String(value == null ? "" : value)
      .replace(/\t/g, " ")
      .replace(/\r?\n/g, " ");
  }

  function formatGridTsv(headers, rows) {
    const lines = [];
    if (headers && headers.length) {
      lines.push(headers.map(escapeGridCellForTsv).join("\t"));
    }
    (rows || []).forEach((row) => {
      lines.push((row || []).map(escapeGridCellForTsv).join("\t"));
    });
    return lines.join("\n");
  }

  function ensureWorkGridSelection(tab) {
    if (!tab.selectedRows || !(tab.selectedRows instanceof Set)) {
      tab.selectedRows = new Set();
      if (tab.selectedRow != null && tab.selectedRow >= 0) tab.selectedRows.add(tab.selectedRow);
    }
  }

  function clampWorkGridCol(tab, col) {
    const n = (tab.fields || []).length;
    if (!n) return 0;
    return Math.max(0, Math.min(col, n - 1));
  }

  function ensureWorkGridCurrentCol(tab) {
    if (tab.currentCol == null || tab.currentCol < 0) tab.currentCol = 0;
    tab.currentCol = clampWorkGridCol(tab, tab.currentCol);
  }

  /** 是否為會攔截 Grid 鍵盤操作的輸入控制項（對齊桌面：表單內 ←→ 不攔截）。 */
  function isGridKeyboardBlockedTarget(el) {
    if (!el) return false;
    return !!el.closest("input, textarea, select, button, a, [contenteditable=true]");
  }

  /** 主檔 Grid 是否應接受方向鍵／Home／End（對齊 QTableView 焦點行為）。 */
  function isWorkGridKeyboardActive(page, gridWrap) {
    if (!page || !gridWrap) return false;
    const ae = document.activeElement;
    if (ae === gridWrap || gridWrap.contains(ae)) return true;
    if (!page.contains(ae)) return false;
    if (isGridKeyboardBlockedTarget(ae)) return false;
    return true;
  }

  function focusWorkGridWrap(page) {
    const wrap = $(".work-table-wrap:not(.tx-table-wrap)", page) || $(".work-table-wrap", page);
    if (wrap) wrap.focus({ preventScroll: true });
  }

  function clampTxGridCol(txd, col) {
    const n = (txd.fields || []).length;
    if (!n) return 0;
    return Math.max(0, Math.min(col, n - 1));
  }

  function ensureTxGridCurrentCol(txd) {
    if (txd.currentCol == null || txd.currentCol < 0) txd.currentCol = 0;
    txd.currentCol = clampTxGridCol(txd, txd.currentCol);
  }

  function refreshWorkGridSelectionUi(page, tab) {
    if (!page) return;
    ensureWorkGridSelection(tab);
    ensureWorkGridCurrentCol(tab);
    $$(`.work-table tbody tr[data-row]`, page).forEach((tr) => {
      const ri = parseInt(tr.dataset.row, 10);
      tr.classList.toggle("selected", tab.selectedRows.has(ri));
      tr.classList.toggle("current-row", tab.selectedRow === ri);
      tr.querySelectorAll("td").forEach((td, ci) => {
        td.classList.toggle("current-cell", tab.selectedRow === ri && tab.currentCol === ci);
      });
    });
    refreshWorkGridNavUi(page, tab);
  }

  function selectAllWorkGridRows(tab, page) {
    ensureWorkGridSelection(tab);
    tab.selectedRows.clear();
    for (let i = 0; i < tab.rows.length; i++) tab.selectedRows.add(i);
    if (tab.rows.length && (tab.selectedRow == null || tab.selectedRow < 0)) tab.selectedRow = 0;
    refreshWorkGridSelectionUi(page, tab);
    const wrap = $(".work-table-wrap", page);
    if (wrap) wrap.focus({ preventScroll: true });
  }

  async function copyWorkGridToClipboard(tab) {
    ensureWorkGridSelection(tab);
    let indices = [...tab.selectedRows].sort((a, b) => a - b);
    if (!indices.length && tab.selectedRow != null && tab.selectedRow >= 0) {
      indices = [tab.selectedRow];
    }
    if (!indices.length) {
      showAlert(t("gridCopyNoSelection"));
      return false;
    }
    const headers = (tab.columns || []).map((c) => c.title || c.name);
    const dataRows = indices.map((i) => tab.rows[i]).filter((r) => r != null);
    const text = formatGridTsv(headers, dataRows);
    const ok = await copyTextToClipboard(text);
    if (ok) showAlert(t("gridCopied", indices.length));
    else showCopyableMessage(t("gridCopyTitle"), text);
    return ok;
  }

  function ensureTxGridSelection(txd) {
    if (!txd.selectedRows || !(txd.selectedRows instanceof Set)) {
      txd.selectedRows = new Set();
      if (txd.selectedRow != null && txd.selectedRow >= 0) txd.selectedRows.add(txd.selectedRow);
    }
  }

  function selectAllTxGridRows(page, detail, tx) {
    const txd = detail.txData[tx];
    if (!txd) return;
    collectTxPhysicalRowsFromPage(page, detail);
    ensureTxGridSelection(txd);
    txd.selectedRows.clear();
    for (let i = 0; i < txd.physical_rows.length; i++) txd.selectedRows.add(i);
    if (txd.physical_rows.length && (txd.selectedRow == null || txd.selectedRow < 0)) txd.selectedRow = 0;
    updateTxSelectionUi(page, tx, txd);
    const wrap = page.querySelector(`.tx-table[data-tx="${CSS.escape(tx)}"]`)?.closest(".tx-table-wrap");
    if (wrap) wrap.focus({ preventScroll: true });
  }

  function getTxRowValuesForCopy(page, tx, txd, rowIndex) {
    const tr = page.querySelector(
      `.tx-table[data-tx="${CSS.escape(tx)}"] tr[data-tx-row="${rowIndex}"]`
    );
    return (txd.fields || []).map((f, j) => {
      const pi = txd.physical_fields.indexOf(f);
      if (tr && pi >= 0) {
        const inp = tr.querySelector(`.tx-cell[data-phys-idx="${pi}"]`);
        if (inp) return inp.value;
      }
      if (txd.rows && txd.rows[rowIndex] && txd.rows[rowIndex][j] !== undefined) {
        return txd.rows[rowIndex][j];
      }
      const prow = txd.physical_rows[rowIndex];
      return pi >= 0 && prow && prow[pi] !== undefined ? prow[pi] : "";
    });
  }

  async function copyTxGridToClipboard(page, detail, tx) {
    const txd = detail.txData[tx];
    if (!txd) return false;
    collectTxPhysicalRowsFromPage(page, detail);
    ensureTxGridSelection(txd);
    let indices = [...txd.selectedRows].sort((a, b) => a - b);
    if (!indices.length && txd.selectedRow != null && txd.selectedRow >= 0) {
      indices = [txd.selectedRow];
    }
    if (!indices.length) {
      showAlert(t("gridCopyNoSelection"));
      return false;
    }
    const headers = (txd.columns || []).map((c) => c.title || c.name || c);
    const dataRows = indices.map((i) => getTxRowValuesForCopy(page, tx, txd, i));
    const text = formatGridTsv(headers, dataRows);
    const ok = await copyTextToClipboard(text);
    if (ok) showAlert(t("gridCopied", indices.length));
    else showCopyableMessage(t("gridCopyTitle"), text);
    return ok;
  }

  async function copyAllWorkGridToClipboard(tab) {
    if (!tab.rows.length) {
      showAlert(t("gridCopyNoSelection"));
      return false;
    }
    const headers = (tab.columns || []).map((c) => c.title || c.name);
    const text = formatGridTsv(headers, tab.rows);
    const ok = await copyTextToClipboard(text);
    if (ok) showAlert(t("gridCopied", tab.rows.length));
    else showCopyableMessage(t("gridCopyTitle"), text);
    return ok;
  }

  let gridContextMenuEl = null;

  function closeGridContextMenu() {
    if (gridContextMenuEl) {
      gridContextMenuEl.remove();
      gridContextMenuEl = null;
    }
    document.removeEventListener("click", closeGridContextMenu, true);
    document.removeEventListener("contextmenu", closeGridContextMenu, true);
    document.removeEventListener("scroll", closeGridContextMenu, true);
    document.removeEventListener("keydown", closeGridContextMenu, true);
  }

  function showGridContextMenu(clientX, clientY, items) {
    closeGridContextMenu();
    const menu = document.createElement("div");
    menu.className = "grid-context-menu";
    menu.setAttribute("role", "menu");
    items.forEach((item) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "grid-context-menu-item" + (item.icon ? " btn-has-icon" : "");
      btn.setAttribute("role", "menuitem");
      if (item.icon) {
        btn.innerHTML = `${uiIcon(item.icon, 14)}<span class="btn-label">${escapeHtml(item.label)}</span>`;
      } else {
        btn.textContent = item.label;
      }
      btn.disabled = !!item.disabled;
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeGridContextMenu();
        if (!item.disabled && item.onClick) item.onClick();
      });
      menu.appendChild(btn);
    });
    document.body.appendChild(menu);
    gridContextMenuEl = menu;
    menu.style.visibility = "hidden";
    menu.style.left = "0";
    menu.style.top = "0";
    const rect = menu.getBoundingClientRect();
    let x = clientX;
    let y = clientY;
    if (x + rect.width > window.innerWidth - 4) x = Math.max(4, window.innerWidth - rect.width - 4);
    if (y + rect.height > window.innerHeight - 4) y = Math.max(4, window.innerHeight - rect.height - 4);
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    menu.style.visibility = "";
    requestAnimationFrame(() => {
      document.addEventListener("click", closeGridContextMenu, true);
      document.addEventListener("contextmenu", closeGridContextMenu, true);
      document.addEventListener("scroll", closeGridContextMenu, true);
      document.addEventListener("keydown", closeGridContextMenu, true);
    });
  }

  function workGridContextMenuItems(tab, page) {
    ensureWorkGridSelection(tab);
    const count = tab.selectedRows.size;
    const hasRows = tab.rows.length > 0;
    return [
      {
        label: count > 0 ? t("gridCtxCopy", count) : t("gridCtxCopy", 0),
        icon: "edit-copy",
        disabled: !hasRows || count <= 0,
        onClick: () => copyWorkGridToClipboard(tab),
      },
      {
        label: t("gridCtxCopyAll"),
        icon: "copy",
        disabled: !hasRows,
        onClick: () => copyAllWorkGridToClipboard(tab),
      },
      {
        label: t("gridCtxSelectAll"),
        icon: "edit",
        disabled: !hasRows,
        onClick: () => selectAllWorkGridRows(tab, page),
      },
    ];
  }

  function handleWorkGridContextMenu(e, tab, page) {
    const tr = e.target.closest("tbody tr[data-row]");
    if (tr) {
      const ri = parseInt(tr.dataset.row, 10);
      const td = e.target.closest("td");
      const col = td ? td.cellIndex : tab.currentCol ?? 0;
      ensureWorkGridSelection(tab);
      if (!tab.selectedRows.has(ri)) {
        selectWorkGridRow(tab, page, ri, { col });
      } else {
        tab.selectedRow = ri;
        tab.currentCol = clampWorkGridCol(tab, col);
        refreshWorkGridSelectionUi(page, tab);
      }
    }
    e.preventDefault();
    e.stopPropagation();
    showGridContextMenu(e.clientX, e.clientY, workGridContextMenuItems(tab, page));
  }

  function bindWorkGridContextMenu(page, tab) {
    const wrap =
      $(".work-page .work-table-wrap:not(.tx-table-wrap)", page) ||
      $(".work-table-wrap:not(.tx-table-wrap)", page);
    if (!wrap || wrap.dataset.ctxBound) return;
    wrap.dataset.ctxBound = "1";
    wrap.addEventListener("contextmenu", (e) => handleWorkGridContextMenu(e, tab, page));
  }

  async function copyAllTxGridToClipboard(page, detail, tx) {
    const txd = detail.txData[tx];
    if (!txd) return false;
    collectTxPhysicalRowsFromPage(page, detail);
    if (!txd.physical_rows.length) {
      showAlert(t("gridCopyNoSelection"));
      return false;
    }
    const headers = (txd.columns || []).map((c) => c.title || c.name || c);
    const dataRows = txd.physical_rows.map((_, i) => getTxRowValuesForCopy(page, tx, txd, i));
    const text = formatGridTsv(headers, dataRows);
    const ok = await copyTextToClipboard(text);
    if (ok) showAlert(t("gridCopied", txd.physical_rows.length));
    else showCopyableMessage(t("gridCopyTitle"), text);
    return ok;
  }

  function txGridContextMenuItems(page, detail, tx) {
    const txd = detail.txData[tx];
    if (!txd) return [];
    ensureTxGridSelection(txd);
    const count = txd.selectedRows.size;
    const total = txd.physical_rows.length;
    return [
      {
        label: count > 0 ? t("gridCtxCopy", count) : t("gridCtxCopy", 0),
        icon: "edit-copy",
        disabled: !total || count <= 0,
        onClick: () => copyTxGridToClipboard(page, detail, tx),
      },
      {
        label: t("gridCtxCopyAll"),
        icon: "copy",
        disabled: !total,
        onClick: () => copyAllTxGridToClipboard(page, detail, tx),
      },
      {
        label: t("gridCtxSelectAll"),
        icon: "edit",
        disabled: !total,
        onClick: () => selectAllTxGridRows(page, detail, tx),
      },
    ];
  }

  function handleTxGridContextMenu(e, page, detail, tx) {
    if (e.target.closest(".tx-cell")) return;
    const tr = e.target.closest("tbody tr[data-tx-row]");
    if (tr) {
      const ri = parseInt(tr.dataset.txRow, 10);
      const td = e.target.closest("td");
      let col = 0;
      if (td && !td.classList.contains("tx-row-gutter")) {
        const raw = parseInt(td.dataset.colIdx, 10);
        col = Number.isFinite(raw) ? raw : Math.max(0, (td.cellIndex || 1) - 1);
      }
      const txd = detail.txData[tx];
      if (txd) {
        ensureTxGridSelection(txd);
        if (!txd.selectedRows.has(ri)) {
          selectTxRow(page, detail, tx, ri, { col });
        } else {
          txd.selectedRow = ri;
          txd.currentCol = clampTxGridCol(txd, col);
          updateTxSelectionUi(page, tx, txd);
        }
      }
    }
    e.preventDefault();
    e.stopPropagation();
    showGridContextMenu(e.clientX, e.clientY, txGridContextMenuItems(page, detail, tx));
  }

  function showCopyableMessage(title, message) {
    closeMessageModal();
    const text = String(message == null ? "" : message);
    const overlay = document.createElement("div");
    overlay.id = "message-modal-overlay";
    overlay.className = "message-modal-overlay";
    overlay.innerHTML = `<div class="message-modal" role="dialog" aria-modal="true">
      <div class="message-modal-header"><h2>${escapeHtml(title)}</h2></div>
      <div class="message-modal-body">
        <p class="message-modal-hint">${escapeHtml(t("msgCopyHint"))}</p>
        <textarea class="message-modal-text" rows="8" spellcheck="false"></textarea>
        <p class="message-modal-status" aria-live="polite"></p>
      </div>
      <div class="message-modal-actions">
        ${iconBtn(t("msgCopyBtn"), "edit-copy", "btn secondary", 'data-msg-act="copy"')}
        ${iconBtn(t("msgOk"), "dialog-ok", "btn action-btn", 'data-msg-act="ok"')}
      </div>
    </div>`;
    document.body.appendChild(overlay);
    const ta = $(".message-modal-text", overlay);
    const statusEl = $(".message-modal-status", overlay);
    if (ta) {
      ta.value = text;
      ta.readOnly = false;
      ta.addEventListener("click", () => ta.select());
      ta.addEventListener("focus", () => ta.select());
      requestAnimationFrame(() => {
        ta.focus();
        ta.select();
      });
    }
    overlay.querySelector('[data-msg-act="copy"]').addEventListener("click", () => {
      copyTextForUser(text, ta, statusEl);
    });
    overlay.querySelector('[data-msg-act="ok"]').addEventListener("click", closeMessageModal);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeMessageModal();
    });
  }

  function showAlert(message, title) {
    showCopyableMessage(title != null && title !== "" ? title : t("notice"), message);
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function iconBtn(label, iconName, className, attrs = "", tooltip = null) {
    const tlt = escapeHtml(tooltip != null ? tooltip : label);
    let iconPx = 16;
    if (/\btopbar-btn\b/.test(className)) iconPx = 18;
    else if (/\bwork-action-btn\b/.test(className)) iconPx = 16;
    return `<button type="button" class="${className} btn-has-icon" title="${tlt}" aria-label="${tlt}" ${attrs}>${uiIcon(iconName, iconPx)}<span class="btn-label">${escapeHtml(label)}</span></button>`;
  }

  function iconBtnOnly(label, iconName, className, attrs = "") {
    const tlt = escapeHtml(label);
    return `<button type="button" class="${className} btn-icon-only" title="${tlt}" aria-label="${tlt}" ${attrs}>${uiIcon(iconName, 16)}</button>`;
  }

  function setButtonIcon(el, iconName, label, tooltip = null, options = {}) {
    if (!el) return;
    el.classList.add("btn-has-icon");
    if (options.topbar) el.classList.add("topbar-btn");
    const text = label != null ? label : el.textContent.trim();
    const tlt = tooltip != null ? tooltip : text;
    el.setAttribute("title", tlt);
    el.setAttribute("aria-label", tlt);
    const iconPx = options.topbar ? 18 : 16;
    el.innerHTML = `${uiIcon(iconName, iconPx)}<span class="btn-label">${escapeHtml(text)}</span>`;
  }

  function decorateChromeButtons() {
    setButtonIcon($("#btn-login-ok"), "dialog-ok");
    setButtonIcon($("#btn-login-cancel"), "cancel");
    refreshTopbarI18n();
  }

  function hideLoginError() {
    const errEl = $("#login-error");
    if (errEl) errEl.classList.add("hidden");
  }

  function showLoginError(message) {
    const errEl = $("#login-error");
    if (!errEl) return;
    errEl.textContent = message;
    errEl.classList.remove("hidden");
  }

  function showLogin() {
    loginView.classList.remove("hidden");
    mainView.classList.add("hidden");
  }

  function showMain() {
    loginView.classList.add("hidden");
    mainView.classList.remove("hidden");
    hideLoginError();
    refreshTopbarI18n();
  }

  function todayAppDate() {
    const d = new Date();
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}/${m}/${day}`;
  }

  function normalizeAppDateText(val) {
    const v = String(val ?? "").trim();
    if (!v) return "";
    const compact = v.match(/^(\d{4})(\d{2})(\d{2})$/);
    if (compact) {
      return `${compact[1]}/${compact[2]}/${compact[3]}`;
    }
    const m = v.match(/^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})/);
    if (!m) return v;
    return `${m[1]}/${String(m[2]).padStart(2, "0")}/${String(m[3]).padStart(2, "0")}`;
  }

  function formatAppDateDisplay(val) {
    const raw = String(val ?? "").trim();
    if (!raw) return "";
    const compact = raw.match(/^(\d{4})(\d{2})(\d{2})$/);
    if (compact) return `${compact[1]}/${compact[2]}/${compact[3]}`;
    const iso = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T\s].*)?$/);
    if (iso) {
      return `${iso[1]}/${String(iso[2]).padStart(2, "0")}/${String(iso[3]).padStart(2, "0")}`;
    }
    return normalizeAppDateText(raw);
  }

  function parseAppDate(val) {
    const n = normalizeAppDateText(val);
    const m = n.match(/^(\d{4})\/(\d{2})\/(\d{2})$/);
    if (!m) return null;
    const y = parseInt(m[1], 10);
    const mo = parseInt(m[2], 10);
    const d = parseInt(m[3], 10);
    const dt = new Date(y, mo - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
    return { y, mo, d };
  }

  function lastDayOfMonth(y, mo) {
    return new Date(y, mo, 0).getDate();
  }

  function initLoginDate() {
    const dt = $("#login-date");
    if (dt && !dt.value) dt.value = todayAppDate();
  }

  async function loadCompanies() {
    const data = await api("/companies", { public: true });
    const sel = $("#login-company");
    sel.innerHTML = "";
    (data.companies || ["GS"]).forEach((co) => {
      const opt = document.createElement("option");
      opt.value = co;
      opt.textContent = co;
      sel.appendChild(opt);
    });
    if (!sel.value && sel.options.length) sel.selectedIndex = 0;
  }

  async function tryLastCompany(userNo, password) {
    if (!userNo || !password) return;
    try {
      const data = await api("/auth/last-company", {
        method: "POST",
        public: true,
        body: JSON.stringify({ user_no: userNo, password }),
      });
      if (data.company_key) {
        const sel = $("#login-company");
        if (![...sel.options].some((o) => o.value === data.company_key)) {
          const opt = document.createElement("option");
          opt.value = data.company_key;
          opt.textContent = data.company_key;
          sel.insertBefore(opt, sel.firstChild);
        }
        sel.value = data.company_key;
      }
    } catch (_) {}
  }

  async function login(userNo, password, companyKey) {
    hideLoginError();
    const selectedCo = (companyKey || $("#login-company").value || "").trim();
    const loginDate = normalizeAppDateText($("#login-date")?.value || todayAppDate());
    try {
      await tryLastCompany(userNo, password);
      const co = selectedCo || ($("#login-company").value || "").trim();
      const data = await api("/auth/login", {
        method: "POST",
        public: true,
        omitAuth: true,
        body: JSON.stringify({
          user_no: userNo,
          password,
          company_key: co,
          login_date: loginDate,
        }),
      });
      token = data.token;
      currentUser = data;
      localStorage.setItem(TOKEN_KEY, token);
      localStorage.setItem(USER_KEY, JSON.stringify(data));
      showMain();
      await refreshMenu();
      updateUserInfo();
    } catch (e) {
      showLoginError(e.message || "登入失敗。");
    }
  }

  function clearSession() {
    const oldToken = token;
    token = "";
    currentUser = null;
    openTabs = [];
    activeTabId = null;
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    if (oldToken) {
      fetch("/api/auth/logout", {
        method: "POST",
        headers: { Authorization: `Bearer ${oldToken}` },
      }).catch(() => {});
    }
  }

  function logout() {
    clearSession();
    showLogin();
    hideLoginError();
    initLoginDate();
  }

  async function restoreSession() {
    if (!token) return false;
    try {
      const data = await api("/auth/me");
      currentUser = { ...JSON.parse(localStorage.getItem(USER_KEY) || "{}"), ...data };
      localStorage.setItem(USER_KEY, JSON.stringify(currentUser));
      return true;
    } catch (_) {
      clearSession();
      return false;
    }
  }

  function updateUserInfo() {
    const el = $("#user-info");
    if (currentUser) el.textContent = `${currentUser.user_no} @ ${currentUser.company_key}`;
  }

  async function refreshMenu() {
    const data = await api("/menu");
    menuGroups = normalizeMenuGroups(data.groups);
    menuHint = (data.hint || "").trim();
    currentLang = data.lang || "CHN";
    renderMenu();
    refreshTopbarI18n();
  }

  function normalizeMenuGroups(groups) {
    return (groups || []).map((g) => ({
      menu_type: g.menu_type || "",
      title: (g.title || g.menu_type || "").trim(),
      items: Array.isArray(g.items)
        ? g.items.filter((it) => it && String(it.do_proc || "").trim())
        : [],
    }));
  }

  function totalMenuItemCount() {
    return menuGroups.reduce((n, g) => n + (g.items || []).length, 0);
  }

  function loadMenuMode() {
    try {
      const v = localStorage.getItem(MENU_MODE_KEY);
      if (["TREE", "ICON_GRID", "LIST", "TOOLBOX", "TABS"].includes(v)) return v;
    } catch (_) {}
    return MENU_MODE_DEFAULT;
  }

  function saveMenuMode(mode) {
    localStorage.setItem(MENU_MODE_KEY, mode);
  }

  function menuItemIconName(item) {
    return item.icon || "applications-system";
  }

  function openProgramFromMenu(doProc, title) {
    openWorkTab(doProc, title);
  }

  function bindMenuItemOpen(el, doProc, title, useDblClick) {
    const open = () => openProgramFromMenu(doProc, title);
    const activate = () => {
      const nav = el.closest("#menu-nav");
      if (nav) {
        nav.querySelectorAll(".menu-item.active, .menu-icon-item.active").forEach((n) => {
          n.classList.remove("active");
        });
      }
      el.classList.add("active");
    };
    if (useDblClick) {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        activate();
      });
      el.addEventListener("dblclick", (e) => {
        e.preventDefault();
        open();
      });
    } else {
      el.addEventListener("click", open);
    }
  }

  function createMenuItemButton(item, groupTitle, opts = {}) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = opts.className || "menu-item btn-has-icon";
    btn.dataset.doProc = item.do_proc;
    const icon = menuItemIconName(item);
    const label = opts.showGroup && groupTitle ? `[${groupTitle}] ${item.title}` : item.title;
    if (opts.iconOnly) {
      btn.className = opts.className || "menu-icon-item";
      btn.innerHTML = `${uiIcon(icon, 44)}<span>${escapeHtml(item.title)}</span>`;
      btn.title = item.title;
    } else {
      btn.innerHTML = `${uiIcon(icon, 32)}<span class="btn-label">${escapeHtml(label)}</span>`;
    }
    bindMenuItemOpen(btn, item.do_proc, item.title, !!opts.dblClick);
    return btn;
  }

  function renderMenuTree(nav) {
    nav.className = "menu-nav-tree";
    menuGroups.forEach((group) => {
      const gEl = document.createElement("div");
      gEl.className = "menu-tree-group";
      const title = document.createElement("div");
      title.className = "menu-tree-group-title";
      title.textContent = group.title;
      gEl.appendChild(title);
      group.items.forEach((item) => {
        const btn = createMenuItemButton(item, group.title, {
          className: "menu-item menu-tree-item btn-has-icon",
          dblClick: true,
        });
        gEl.appendChild(btn);
      });
      nav.appendChild(gEl);
    });
  }

  function renderMenuIconGrid(nav) {
    // 對齊桌面：圖示模式扁平、不顯示群組標題
    const grid = document.createElement("div");
    grid.className = "menu-icon-grid";
    menuGroups.forEach((group) => {
      group.items.forEach((item) => {
        grid.appendChild(
          createMenuItemButton(item, group.title, { iconOnly: true, dblClick: true })
        );
      });
    });
    nav.appendChild(grid);
  }

  function renderMenuList(nav) {
    menuGroups.forEach((group) => {
      group.items.forEach((item) => {
        nav.appendChild(
          createMenuItemButton(item, group.title, {
            className: "menu-item menu-list-item btn-has-icon",
            showGroup: true,
            dblClick: true,
          })
        );
      });
    });
  }

  function renderMenuToolbox(nav) {
    nav.className = "menu-nav-toolbox";
    menuGroups.forEach((group, gi) => {
      const gEl = document.createElement("div");
      gEl.className = "menu-toolbox-group";
      const head = document.createElement("button");
      head.type = "button";
      head.className = "menu-toolbox-title";
      head.textContent = group.title;
      head.setAttribute("aria-expanded", gi === 0 ? "true" : "false");
      const body = document.createElement("div");
      body.className = "menu-toolbox-body" + (gi === 0 ? "" : " hidden");
      group.items.forEach((item) => {
        body.appendChild(
          createMenuItemButton(item, group.title, {
            className: "menu-item btn-has-icon",
            dblClick: true,
          })
        );
      });
      head.addEventListener("click", () => {
        // 對齊桌面 QToolBox：一次只展開一組
        nav.querySelectorAll(".menu-toolbox-body").forEach((b) => b.classList.add("hidden"));
        nav.querySelectorAll(".menu-toolbox-title").forEach((h) => h.setAttribute("aria-expanded", "false"));
        body.classList.remove("hidden");
        head.setAttribute("aria-expanded", "true");
      });
      gEl.appendChild(head);
      gEl.appendChild(body);
      nav.appendChild(gEl);
    });
  }

  function renderMenuTabs(nav) {
    nav.className = "menu-nav-tabs";
    const bar = document.createElement("div");
    bar.className = "menu-tabs-bar";
    const panels = document.createElement("div");
    panels.className = "menu-tabs-panels";
    menuGroups.forEach((group, gi) => {
      const tabBtn = document.createElement("button");
      tabBtn.type = "button";
      tabBtn.className = "menu-tab-btn" + (gi === 0 ? " active" : "");
      tabBtn.style.color = tabTitleColor(gi);
      tabBtn.textContent = group.title;
      tabBtn.dataset.menuTab = String(gi);
      const panel = document.createElement("div");
      panel.className = "menu-tabs-panel" + (gi === 0 ? "" : " hidden");
      panel.dataset.menuPanel = String(gi);
      group.items.forEach((item) => {
        panel.appendChild(
          createMenuItemButton(item, group.title, { className: "menu-item btn-has-icon", dblClick: true })
        );
      });
      tabBtn.addEventListener("click", () => {
        bar.querySelectorAll(".menu-tab-btn").forEach((b) => {
          b.classList.toggle("active", b.dataset.menuTab === String(gi));
        });
        panels.querySelectorAll(".menu-tabs-panel").forEach((p) => {
          p.classList.toggle("hidden", p.dataset.menuPanel !== String(gi));
        });
      });
      bar.appendChild(tabBtn);
      panels.appendChild(panel);
    });
    nav.appendChild(bar);
    nav.appendChild(panels);
  }

  function syncMenuModeSelect() {
    const sel = $("#menu-mode-select");
    if (sel) sel.value = loadMenuMode();
  }

  function renderMenu() {
    const nav = $("#menu-nav");
    if (!nav) return;
    nav.innerHTML = "";
    nav.className = "";
    const mode = loadMenuMode();
    syncMenuModeSelect();
    if (!menuGroups.length || totalMenuItemCount() === 0) {
      const extra = menuHint
        ? `<br><span class="menu-empty-detail">${escapeHtml(menuHint)}</span>`
        : "";
      nav.innerHTML = `<p class="menu-empty-hint">${escapeHtml(t("menuEmpty"))}${extra}</p>`;
      return;
    }
    try {
      if (mode === "ICON_GRID") renderMenuIconGrid(nav);
      else if (mode === "LIST") renderMenuList(nav);
      else if (mode === "TOOLBOX") renderMenuToolbox(nav);
      else if (mode === "TABS") renderMenuTabs(nav);
      else renderMenuTree(nav);
      const hint = document.createElement("p");
      hint.className = "menu-dblclick-hint";
      hint.textContent = t("menuDblClickHint");
      nav.appendChild(hint);
    } catch (err) {
      console.error("renderMenu failed", err);
      nav.innerHTML = `<p class="menu-empty-hint">${escapeHtml(t("menuEmpty"))}</p>`;
    }
  }

  function workTabId(doProc) {
    return `work-${doProc}`;
  }

  function detailTabId(workId, suffix) {
    return `detail-${workId}-${suffix}`;
  }

  async function openWorkTab(doProc, title) {
    const doKey = String(doProc || "").trim().toUpperCase();
    // DATAIMPORT / RUNQUERY：即使選單 STD_PROC 誤標為 TRUE，仍走專用介面
    if (isDataImportProc(doProc) || isRunQueryProc(doProc) || isNonStandardMenuProgram(doProc)) {
      if (isDataImportProc(doProc)) {
        await openDataImportModal({ doProc });
        return;
      }
      if (isRunQueryProc(doProc)) {
        await openRunQueryTab(doProc, title);
        return;
      }
      showAlert(currentLang === "CHN" ? `非標準程式「${doProc}」尚未支援。` : `Non-standard program「${doProc}」is not supported.`);
      return;
    }
    const id = workTabId(doProc);
    if (!openTabs.find((x) => x.id === id)) {
      openTabs.push({
        type: "work",
        id,
        doProc,
        title,
        keyword: "",
        filtered: false,
        selectedRow: null,
        selectedRows: new Set(),
        currentCol: 0,
        rows: [],
        physicalRows: [],
        fields: [],
        columns: [],
        formFields: [],
        formColumns: [],
        physicalFields: [],
        txFiles: [],
        printKeyColumn: null,
        menuTitle: title,
        columnWidths: {},
        sortStack: [],
        workActions: mergeWorkActions({}, findMenuWorkActions(doProc)),
      });
    }
    const tab = openTabs.find((x) => x.id === id);
    if (tab) {
      tab.menuTitle = title;
      tab.workActions = mergeWorkActions(findMenuWorkActions(doProc), tab.workActions || {});
      await loadWorkData(tab, { reloadProgram: true, asFilter: !!tab.filtered });
    }
    activeTabId = id;
    renderTabs();
  }

  async function loadWorkData(tab, opts = {}) {
    const asFilter = opts.asFilter === true;
    const reloadProgram = opts.reloadProgram === true;
    const data = await api(`/work/${encodeURIComponent(tab.doProc)}/rows`, {
      method: "POST",
      body: JSON.stringify({
        keyword: tab.keyword,
        as_filter: asFilter,
        limit: 100000,
        reload_program: reloadProgram,
      }),
    });
    Object.assign(tab, {
      tableName: data.table_name,
      rows: data.rows,
      physicalRows: data.physical_rows || data.rows,
      fields: data.fields,
      columns: data.columns,
      formFields: data.form_fields || [],
      formColumns: data.form_columns || [],
      physicalFields: data.physical_fields || data.fields,
      txFiles: data.tx_files || [],
      printKeyColumn: data.print_doc_key_column,
      menuTitle: data.menu_title || tab.title,
      searchIndices: data.search_indices == null ? null : data.search_indices,
      searchRetField: data.search_ret_field || null,
      searchRetValue: data.search_ret_value || null,
      workActions: mergeWorkActions(
        findMenuWorkActions(tab.doProc),
        tab.workActions,
        data.work_actions || {}
      ),
      keyCodeColumn: data.key_code_column || null,
      numTypeColumn: data.num_type_column || null,
      numControlColumn: data.num_control_column || null,
      numDigit: data.num_digit || 8,
      procName: data.proc_name || tab.procName || "",
      filtered: asFilter,
    });
    applyWorkGridSort(tab);
    if (opts.preserveAnchor && anchorRowHasKey(opts.anchorRow)) {
      const idx = findWorkRowIndex(tab, opts.anchorRow);
      if (idx >= 0) tab.selectedRow = idx;
      else if (opts.clearSelectionIfMissing) tab.selectedRow = null;
    } else if (!asFilter && tab.keyword) {
      if (tab.searchRetField && tab.searchRetValue) {
        const phys = tab.physicalFields || [];
        const dest = String(tab.searchRetField).toUpperCase();
        const want = String(tab.searchRetValue).trim().toLowerCase();
        const pi = phys.findIndex((n) => String(n).toUpperCase() === dest);
        let idx = -1;
        if (pi >= 0) {
          idx = (tab.physicalRows || []).findIndex(
            (row) => pi < row.length && String(row[pi] || "").trim().toLowerCase() === want
          );
          if (idx < 0) {
            idx = (tab.physicalRows || []).findIndex(
              (row) =>
                pi < row.length &&
                String(row[pi] || "").trim().toLowerCase().includes(want)
            );
          }
        }
        if (idx < 0) {
          showAlert(
            currentLang === "CHN"
              ? `找不到「${tab.searchRetField}」=「${tab.searchRetValue}」的紀錄。`
              : `No record with ${tab.searchRetField}=${tab.searchRetValue}.`
          );
          tab.selectedRow = null;
        } else {
          tab.selectedRow = idx;
        }
        } else {
          const kw = tab.keyword.toLowerCase();
          const idx = (tab.physicalRows || []).findIndex((row) =>
            rowMatchesKeyword(row, kw, null)
          );
          // 搜尋無命中：保留原選列（與桌面一致），不過濾
          if (idx >= 0) tab.selectedRow = idx;
          else if (
            tab.selectedRow != null &&
            (tab.selectedRow < 0 || tab.selectedRow >= (tab.rows || []).length)
          ) {
            tab.selectedRow = null;
          }
        }
    } else if (!asFilter && !tab.keyword && tab.txFiles?.length && tab.rows.length) {
      tab.selectedRow = 0;
    } else if (asFilter && tab.rows.length) {
      tab.selectedRow = 0;
    } else if (asFilter && !tab.rows.length && tab.keyword) {
      // 過濾無結果（含 SEARCH_RET LOOKUP 無主檔列）
      if (tab.searchRetField && tab.searchRetValue) {
        showAlert(
          currentLang === "CHN"
            ? `找不到「${tab.searchRetField}」=「${tab.searchRetValue}」的紀錄。`
            : `No record with ${tab.searchRetField}=${tab.searchRetValue}.`
        );
      }
      tab.selectedRow = null;
    }
    ensureWorkGridSelection(tab);
    tab.selectedRows.clear();
    if (tab.selectedRow != null && tab.selectedRow >= 0 && tab.selectedRow < tab.rows.length) {
      tab.selectedRows.add(tab.selectedRow);
    }
    initWorkColumnWidths(tab);
  }

  function rowMatchesKeyword(row, kw, searchIndices) {
    if (!row) return false;
    if (searchIndices == null) {
      return row.some((c) => String(c).toLowerCase().includes(kw));
    }
    return searchIndices.some(
      (i) => i >= 0 && i < row.length && String(row[i]).toLowerCase().includes(kw)
    );
  }

  /** 對齊桌面 reload_keep_current_row：KEY_CODE / TX_KEY / ID → 整列比對。 */
  function findWorkRowIndex(tab, anchorRow) {
    if (!anchorRow || !tab.physicalRows?.length) return -1;
    const phys = tab.physicalFields || tab.fields || [];
    const keyNames = [];
    for (const k of [tab.printKeyColumn, tab.keyCodeColumn, "TX_KEY", "ID"]) {
      const name = (k || "").trim();
      if (!name) continue;
      if (!keyNames.some((x) => x.toUpperCase() === name.toUpperCase())) keyNames.push(name);
    }
    for (const key of keyNames) {
      const pi = phys.findIndex((n) => String(n).toUpperCase() === key.toUpperCase());
      if (pi < 0) continue;
      const want = String(anchorRow[pi] ?? "").trim();
      if (!want) continue;
      const hit = tab.physicalRows.findIndex(
        (row) => pi < row.length && String(row[pi] ?? "").trim() === want
      );
      if (hit >= 0) return hit;
    }
    const norm = anchorRow.map((c) => String(c ?? "").trim());
    if (!norm.some((v) => v)) return -1;
    return tab.physicalRows.findIndex((row) => {
      const n = Math.min(row.length, norm.length);
      if (!n) return false;
      for (let i = 0; i < n; i++) {
        if (norm[i] !== String(row[i] ?? "").trim()) return false;
      }
      return true;
    });
  }

  function physicalRowFromFormValues(tab, values) {
    const phys = tab.physicalFields || tab.fields || [];
    return phys.map((f) => {
      const want = String(f || "").trim().toUpperCase();
      if (!want) return "";
      for (const [k, v] of Object.entries(values || {})) {
        if (String(k).trim().toUpperCase() === want) return String(v ?? "");
      }
      return "";
    });
  }

  function anchorRowHasKey(anchorRow) {
    return Array.isArray(anchorRow) && anchorRow.some((c) => String(c ?? "").trim());
  }

  /** 對齊 Access/SQLite 布林（Y/1/-1/TRUE）與 JSON boolean。 */
  function isWorkFlagTrue(v) {
    if (v === true || v === 1 || v === -1) return true;
    if (typeof v === "string") {
      const s = v.trim().toUpperCase();
      return s === "Y" || s === "YES" || s === "TRUE" || s === "1" || s === "-1";
    }
    return false;
  }

  function findMenuProgramItem(doProc) {
    const key = String(doProc || "").trim().toUpperCase();
    for (const g of menuGroups) {
      for (const it of g.items || []) {
        if (String(it.do_proc || "").trim().toUpperCase() === key) {
          return it;
        }
      }
    }
    return null;
  }

  function isNonStandardMenuProgram(doProc) {
    const it = findMenuProgramItem(doProc);
    return it && it.std_proc === false;
  }

  function findMenuWorkActions(doProc) {
    const key = String(doProc || "").trim().toUpperCase();
    for (const g of menuGroups) {
      for (const it of g.items || []) {
        if (String(it.do_proc || "").trim().toUpperCase() === key) {
          return {
            need_attach: it.need_attach,
            attach_path: it.attach_path || "",
            attach_key: it.attach_key || "",
            need_other: it.need_other,
            other_title: it.other_title || "",
          };
        }
      }
    }
    return {};
  }

  /** 合併選單 PROGRAM 與作業 API 的 NEED_ATTACH / NEED_OTHER 旗標。 */
  function mergeWorkActions(...sources) {
    const out = {
      need_attach: false,
      attach_path: "",
      attach_key: "",
      need_other: false,
      other_title: "",
    };
    for (const wa of sources) {
      if (!wa) continue;
      if (isWorkFlagTrue(wa.need_attach)) {
        out.need_attach = true;
        if ((wa.attach_path || "").trim()) out.attach_path = wa.attach_path.trim();
        if ((wa.attach_key || "").trim()) out.attach_key = wa.attach_key.trim();
      }
      if (isWorkFlagTrue(wa.need_other)) {
        out.need_other = true;
        if ((wa.other_title || "").trim()) out.other_title = wa.other_title.trim();
      }
    }
    return out;
  }

  function isDataImportProc(doProc) {
    const key = String(doProc || "").trim().toUpperCase();
    return key === "DATAIMPORT" || key === "DO_DATAIMPORT" || key.endsWith("DATAIMPORT");
  }

  function isRunQueryProc(doProc) {
    const key = String(doProc || "").trim().toUpperCase().replace(/-/g, "_");
    if (!key) return false;
    if (key === "RUNQUERY" || key === "DO_RUNQUERY" || key === "RUN_QUERY" || key === "DO_RUN_QUERY") {
      return true;
    }
    return key.endsWith("RUNQUERY") || key.endsWith("RUN_QUERY");
  }

  function isDataImportTab(tab) {
    return isDataImportProc(tab?.doProc);
  }

  function tabWorkActions(tab) {
    return mergeWorkActions(findMenuWorkActions(tab.doProc), tab.workActions || {});
  }

  function formatRecordNavLabel(total, current1based) {
    if (total <= 0) return "0/0";
    if (current1based == null) return `-/${total}`;
    return `${current1based}/${total}`;
  }

  function refreshWorkGridNavUi(page, tab) {
    if (!page) return;
    const total = tab.rows.length;
    const cur = tab.selectedRow != null && tab.selectedRow >= 0 && tab.selectedRow < total
      ? tab.selectedRow + 1
      : null;
    const navEl = $(".record-nav", page);
    if (navEl) navEl.textContent = formatRecordNavLabel(total, cur);

    const row = tab.selectedRow;
    const noSel = row == null || row < 0 || row >= total;
    const hasRows = total > 0;
    const setDisabled = (sel, disabled) => {
      const btn = page.querySelector(sel);
      if (btn) btn.disabled = disabled;
    };
    setDisabled('[data-nav="first"]', !hasRows || (!noSel && row <= 0));
    setDisabled('[data-nav="prev"]', !hasRows || noSel || row <= 0);
    setDisabled('[data-nav="next"]', !hasRows || noSel || row >= total - 1);
    setDisabled('[data-nav="last"]', !hasRows || (!noSel && row >= total - 1));
  }

  function scrollRowInContainer(container, row, opts = {}) {
    if (!container || !row) return;
    const headSel = opts.headSelector ?? "thead";
    const head = headSel ? container.querySelector(headSel) : null;
    const headH = head ? head.getBoundingClientRect().height : 0;
    const margin = opts.margin ?? 6;
    const hBar = Math.max(0, container.offsetHeight - container.clientHeight);

    const adjust = () => {
      const cRect = container.getBoundingClientRect();
      const rRect = row.getBoundingClientRect();
      const viewTop = cRect.top + headH + margin;
      const viewBottom = cRect.bottom - hBar - margin;
      if (rRect.top < viewTop) {
        container.scrollTop -= viewTop - rRect.top;
        return true;
      }
      if (rRect.bottom > viewBottom) {
        container.scrollTop += rRect.bottom - viewBottom;
        return true;
      }
      return false;
    };

    adjust();
    adjust();
  }

  function scrollWorkGridCellIntoView(tab, page) {
    page = page || document.querySelector(`.work-page[data-tab="${tab.id}"]`);
    if (!page || tab.selectedRow == null) return;
    const wrap = $(".work-table-wrap", page);
    const tr = page.querySelector(`tbody tr[data-row="${tab.selectedRow}"]`);
    if (!wrap || !tr) return;
    scrollRowInContainer(wrap, tr);
    const td = tr.querySelectorAll("td")[tab.currentCol];
    if (!td) return;
    const cRect = wrap.getBoundingClientRect();
    const tRect = td.getBoundingClientRect();
    if (tRect.left < cRect.left) wrap.scrollLeft -= cRect.left - tRect.left + 8;
    else if (tRect.right > cRect.right) wrap.scrollLeft += tRect.right - cRect.right + 8;
  }

  function scrollWorkGridRowIntoView(tab, page) {
    page = page || document.querySelector(`.work-page[data-tab="${tab.id}"]`);
    if (!page || tab.selectedRow == null) return;
    const wrap = $(".work-table-wrap", page);
    const tr = page.querySelector(`tbody tr[data-row="${tab.selectedRow}"]`);
    if (!wrap || !tr) return;
    scrollRowInContainer(wrap, tr);
  }

  function selectWorkGridRow(tab, page, row, opts = {}) {
    const total = tab.rows.length;
    ensureWorkGridSelection(tab);
    const mode = opts.mode || "single";
    if (!total) {
      tab.selectedRow = null;
      tab.selectedRows.clear();
    } else if (row == null || row < 0 || row >= total) {
      return false;
    } else {
      tab.selectedRow = row;
      if (opts.col != null) tab.currentCol = clampWorkGridCol(tab, opts.col);
      else ensureWorkGridCurrentCol(tab);
      if (mode === "single") {
        tab.selectedRows.clear();
        tab.selectedRows.add(row);
        tab.selectionAnchor = row;
      } else if (mode === "toggle") {
        if (tab.selectedRows.has(row)) tab.selectedRows.delete(row);
        else tab.selectedRows.add(row);
        if (!tab.selectedRows.size) tab.selectedRows.add(row);
        tab.selectionAnchor = row;
      } else if (mode === "range") {
        const anchor = opts.anchor ?? tab.selectionAnchor ?? tab.selectedRow ?? 0;
        const lo = Math.min(anchor, row);
        const hi = Math.max(anchor, row);
        tab.selectedRows.clear();
        for (let i = lo; i <= hi; i++) tab.selectedRows.add(i);
        tab.selectionAnchor = anchor;
      }
    }
    refreshWorkGridSelectionUi(page, tab);
    refreshWorkOtherButtonState(tab, page);
    if (opts.scroll !== false) scrollWorkGridCellIntoView(tab, page);
    if (opts.focus !== false) {
      const wrap = $(".work-table-wrap", page);
      if (wrap) wrap.focus({ preventScroll: true });
    }
    return true;
  }

  function navigateWorkGrid(tab, page, nav) {
    const n = tab.rows.length;
    if (!n) return;
    const row = tab.selectedRow;
    const noSel = row == null || row < 0 || row >= n;
    if (nav === "first") selectWorkGridRow(tab, page, 0);
    else if (nav === "last") selectWorkGridRow(tab, page, n - 1);
    else if (nav === "prev") {
      if (!noSel && row > 0) selectWorkGridRow(tab, page, row - 1);
    }     else if (nav === "next") {
      if (!noSel && row < n - 1) selectWorkGridRow(tab, page, row + 1);
    }
  }

  function charWidthPx(chars) {
    return Math.max(48, Math.round(chars * 9 + 20));
  }

  function gridCellAlignClass(meta) {
    return meta && meta.align === "right" ? " cell-align-right" : "";
  }

  /** 對齊 core/grid_sort.py：單欄點擊／Ctrl+點擊多欄排序。 */
  function toggleGridSortStack(stack, column, multi) {
    const col = Number(column);
    const hit = stack.findIndex((s) => s.column === col);
    if (!multi) {
      if (hit >= 0 && stack.length === 1) {
        stack[0] = { column: col, descending: !stack[0].descending };
      } else {
        stack.length = 0;
        stack.push({ column: col, descending: false });
      }
      return;
    }
    if (hit >= 0) {
      if (!stack[hit].descending) {
        stack[hit] = { column: col, descending: true };
      } else {
        stack.splice(hit, 1);
      }
    } else {
      stack.push({ column: col, descending: false });
    }
  }

  function gridSortIndicatorHtml(stack, column) {
    for (let i = 0; i < (stack || []).length; i++) {
      const sk = stack[i];
      if (sk.column === column) {
        const arrow = sk.descending ? "▼" : "▲";
        const suffix = stack.length > 1 ? String(i + 1) : "";
        return `<span class="grid-sort-indicator" aria-hidden="true">${arrow}${suffix}</span>`;
      }
    }
    return "";
  }

  function compareGridSortValues(a, b, numeric) {
    const sa = String(a ?? "").trim();
    const sb = String(b ?? "").trim();
    if (numeric) {
      const na = sa ? parseFloat(sa.replace(/,/g, "")) : 0;
      const nb = sb ? parseFloat(sb.replace(/,/g, "")) : 0;
      if (!Number.isNaN(na) && !Number.isNaN(nb)) {
        if (na < nb) return -1;
        if (na > nb) return 1;
        return 0;
      }
    }
    const la = sa.toLowerCase();
    const lb = sb.toLowerCase();
    if (la < lb) return -1;
    if (la > lb) return 1;
    return 0;
  }

  function sortRowIndices(rows, stack, valueAt, isNumericCol) {
    if (!rows?.length || !stack?.length) return rows.map((_, i) => i);
    const numFn = isNumericCol || (() => false);
    const indices = rows.map((_, i) => i);
    indices.sort((ia, ib) => {
      for (const sk of stack) {
        const va = valueAt(rows[ia], sk.column);
        const vb = valueAt(rows[ib], sk.column);
        let c = compareGridSortValues(va, vb, numFn(sk.column));
        if (c !== 0) return sk.descending ? -c : c;
      }
      return 0;
    });
    return indices;
  }

  function isWorkColumnNumeric(tab, colIdx) {
    const meta = (tab.columns || [])[colIdx] || {};
    const dt = (meta.data_type || "").toUpperCase();
    return dt === "N" || dt === "NUMERIC" || meta.align === "right";
  }

  function isTxColumnNumeric(txd, colIdx) {
    const cols = txd.columns || [];
    const f = (txd.fields || [])[colIdx];
    const meta = cols.find((c) => c.name === f) || cols[colIdx] || {};
    const dt = (meta.data_type || "").toUpperCase();
    return dt === "N" || dt === "NUMERIC" || meta.align === "right";
  }

  function applyWorkGridSort(tab) {
    if (!tab.sortStack?.length || !tab.rows?.length) return;
    const order = sortRowIndices(
      tab.rows,
      tab.sortStack,
      (row, col) => (col < row.length ? row[col] : ""),
      (col) => isWorkColumnNumeric(tab, col)
    );
    tab.rows = order.map((i) => tab.rows[i]);
    if (tab.physicalRows?.length === order.length) {
      tab.physicalRows = order.map((i) => tab.physicalRows[i]);
    }
  }

  function applyTxGridSort(txd) {
    if (!txd.sortStack?.length || !txd.rows?.length) return;
    const order = sortRowIndices(
      txd.rows,
      txd.sortStack,
      (row, col) => (col < row.length ? row[col] : ""),
      (col) => isTxColumnNumeric(txd, col)
    );
    txd.rows = order.map((i) => txd.rows[i]);
    if (txd.physical_rows?.length === order.length) {
      txd.physical_rows = order.map((i) => txd.physical_rows[i]);
    }
  }

  function handleWorkGridHeaderSort(tab, colIdx, multi) {
    if (!tab.sortStack) tab.sortStack = [];
    const anchor =
      tab.selectedRow != null && tab.physicalRows?.[tab.selectedRow]
        ? tab.physicalRows[tab.selectedRow]
        : null;
    toggleGridSortStack(tab.sortStack, colIdx, multi);
    applyWorkGridSort(tab);
    if (anchor) {
      const idx = findWorkRowIndex(tab, anchor);
      tab.selectedRow = idx >= 0 ? idx : null;
    }
    tab.selectedRows = new Set();
    if (tab.selectedRow != null && tab.selectedRow >= 0 && tab.selectedRow < tab.rows.length) {
      tab.selectedRows.add(tab.selectedRow);
    }
    renderTabs();
  }

  function handleTxGridHeaderSort(detail, tx, colIdx, multi) {
    const txd = detail.txData[tx];
    if (!txd) return;
    if (!txd.sortStack) txd.sortStack = [];
    const anchor =
      txd.selectedRow != null && txd.physical_rows?.[txd.selectedRow]
        ? txd.physical_rows[txd.selectedRow]
        : null;
    toggleGridSortStack(txd.sortStack, colIdx, multi);
    applyTxGridSort(txd);
    if (anchor) {
      const norm = anchor.map((c) => String(c ?? "").trim());
      const idx = txd.physical_rows.findIndex((row) => {
        if (row.length !== norm.length) return false;
        return norm.every((v, i) => v === String(row[i] ?? "").trim());
      });
      txd.selectedRow = idx >= 0 ? idx : null;
    }
    txd.selectedRows = new Set();
    if (txd.selectedRow != null && txd.selectedRow >= 0) txd.selectedRows.add(txd.selectedRow);
    if (detail.inModal) refreshFormModalUI(detail);
    else renderTabs();
  }

  function bindWorkGridSortHeaders(page, tab) {
    $$(".work-table:not(.tx-table) thead th[data-col-idx]", page).forEach((th) => {
      th.addEventListener("click", (e) => {
        if (e.target.closest(".col-resizer")) return;
        const colIdx = parseInt(th.dataset.colIdx, 10);
        if (Number.isNaN(colIdx)) return;
        handleWorkGridHeaderSort(tab, colIdx, e.ctrlKey || e.metaKey);
      });
    });
  }

  function bindTxGridSortHeaders(page, detail, tx) {
    $$(`.tx-table[data-tx="${CSS.escape(tx)}"] thead th[data-col-idx]`, page).forEach((th) => {
      th.addEventListener("click", (e) => {
        if (e.target.closest(".col-resizer")) return;
        const colIdx = parseInt(th.dataset.colIdx, 10);
        if (Number.isNaN(colIdx)) return;
        handleTxGridHeaderSort(detail, tx, colIdx, e.ctrlKey || e.metaKey);
      });
    });
  }

  function initWorkColumnWidths(tab) {
    if (!tab.columnWidths) tab.columnWidths = {};
    (tab.fields || []).forEach((field, i) => {
      if (tab.columnWidths[field] != null) return;
      const meta = (tab.columns || [])[i] || {};
      const title = meta.title || field;
      let maxChars = String(title).length;
      (tab.rows || []).slice(0, 5000).forEach((row) => {
        maxChars = Math.max(maxChars, String(row[i] || "").length);
      });
      const wdict = meta.grid_width_chars || 0;
      if (wdict > 0) {
        tab.columnWidths[field] = charWidthPx(wdict);
      } else {
        tab.columnWidths[field] = charWidthPx(Math.min(Math.max(maxChars, 6), 80));
      }
    });
  }

  function workColWidthStyle(tab, field) {
    const w = tab.columnWidths && tab.columnWidths[field];
    if (!w) return "";
    return ` style="width:${w}px;min-width:${w}px;max-width:${w}px"`;
  }

  function initTxColumnWidths(txd) {
    if (!txd.columnWidths) txd.columnWidths = {};
    (txd.fields || []).forEach((field, i) => {
      if (txd.columnWidths[field] != null) return;
      const meta = (txd.columns || []).find((c) => c.name === field) || (txd.columns || [])[i] || {};
      const title = meta.title || field;
      let maxChars = String(title).length;
      (txd.rows || txd.physical_rows || []).slice(0, 5000).forEach((row, ri) => {
        const prow = (txd.physical_rows || [])[ri];
        const pi = txd.physical_fields.indexOf(field);
        let val = "";
        if (Array.isArray(row) && i < row.length) {
          val = row[i] !== undefined ? row[i] : "";
        } else if (prow && pi >= 0) {
          val = prow[pi] !== undefined ? prow[pi] : "";
        }
        maxChars = Math.max(maxChars, String(val).length);
      });
      const wdict = meta.grid_width_chars || 0;
      if (wdict > 0) {
        txd.columnWidths[field] = charWidthPx(wdict);
      } else {
        txd.columnWidths[field] = charWidthPx(Math.min(Math.max(maxChars, 6), 80));
      }
    });
  }

  function txColWidthStyle(txd, field) {
    const w = txd.columnWidths && txd.columnWidths[field];
    if (!w) return "";
    return ` style="width:${w}px;min-width:${w}px;max-width:${w}px"`;
  }

  function bindWorkGridColumnResize(page, tab) {
    $$(".work-page .work-table:not(.tx-table) th[data-col] .col-resizer", page).forEach((resizer) => {
      resizer.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const th = resizer.closest("th[data-col]");
        if (!th) return;
        const field = th.dataset.col;
        const startX = e.clientX;
        const startW = th.offsetWidth;
        document.body.classList.add("col-resizing");

        const onMove = (ev) => {
          const newW = Math.max(40, startW + (ev.clientX - startX));
          if (!tab.columnWidths) tab.columnWidths = {};
          tab.columnWidths[field] = newW;
          th.style.width = `${newW}px`;
          th.style.minWidth = `${newW}px`;
          th.style.maxWidth = `${newW}px`;
          const colIdx = tab.fields.indexOf(field);
          if (colIdx >= 0) {
            $$(`.work-page .work-table:not(.tx-table) tbody tr`, page).forEach((tr) => {
              const td = tr.children[colIdx];
              if (td) {
                td.style.width = `${newW}px`;
                td.style.minWidth = `${newW}px`;
                td.style.maxWidth = `${newW}px`;
              }
            });
          }
        };
        const onUp = () => {
          document.body.classList.remove("col-resizing");
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
        };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
    });
  }

  function bindTxGridColumnResize(page, detail, tx) {
    const txd = detail.txData[tx];
    if (!txd) return;
    $$(`.tx-table[data-tx="${CSS.escape(tx)}"] th[data-col] .col-resizer`, page).forEach((resizer) => {
      resizer.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        const th = resizer.closest("th[data-col]");
        if (!th) return;
        const field = th.dataset.col;
        const startX = e.clientX;
        const startW = th.offsetWidth;
        document.body.classList.add("col-resizing");

        const onMove = (ev) => {
          const newW = Math.max(40, startW + (ev.clientX - startX));
          if (!txd.columnWidths) txd.columnWidths = {};
          txd.columnWidths[field] = newW;
          th.style.width = `${newW}px`;
          th.style.minWidth = `${newW}px`;
          th.style.maxWidth = `${newW}px`;
          const colIdx = txd.fields.indexOf(field);
          if (colIdx >= 0) {
            $$(`.tx-table[data-tx="${CSS.escape(tx)}"] tbody tr`, page).forEach((tr) => {
              const td = tr.children[colIdx];
              if (td) {
                td.style.width = `${newW}px`;
                td.style.minWidth = `${newW}px`;
                td.style.maxWidth = `${newW}px`;
              }
            });
          }
        };
        const onUp = () => {
          document.body.classList.remove("col-resizing");
          document.removeEventListener("mousemove", onMove);
          document.removeEventListener("mouseup", onUp);
        };
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
      });
    });
  }

  const AI_TAB_ID = "tab-ai";

  function currentWorkTab() {
    const active = openTabs.find((x) => x.id === activeTabId);
    if (active && active.type === "work") return active;
    for (let i = openTabs.length - 1; i >= 0; i--) {
      if (openTabs[i].type === "work") return openTabs[i];
    }
    return null;
  }

  function findWorkTabByDoProc(doProc) {
    const key = String(doProc || "").trim().toUpperCase();
    if (!key) return null;
    return openTabs.find((x) => x.type === "work" && String(x.doProc || "").toUpperCase() === key) || null;
  }

  function bytesToBase64(buf) {
    const bytes = new Uint8Array(buf);
    let binary = "";
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
  }

  function openAiTab() {
    let tab = openTabs.find((x) => x.id === AI_TAB_ID);
    if (!tab) {
      tab = {
        type: "ai",
        id: AI_TAB_ID,
        title: t("aiTab"),
        messages: [{ role: "assistant", content: t("aiWelcome") }],
        promptHistory: [],
        docs: [],
      };
      openTabs.push(tab);
    }
    activeTabId = AI_TAB_ID;
    renderTabs();
    refreshAiDocs(tab).catch((err) => showAlert(err?.message || String(err)));
  }

  async function refreshAiDocs(tab) {
    const data = await api("/ai/docs");
    tab.docs = data.docs || [];
    const list = document.querySelector(".ai-doc-list");
    if (list) list.innerHTML = renderAiDocList(tab);
  }

  function renderAiDocList(tab) {
    const docs = tab.docs || [];
    if (!docs.length) return `<li class="muted">${escapeHtml(t("aiNoDocs"))}</li>`;
    return docs
      .map(
        (d) =>
          `<li><span>${escapeHtml(d.name || "")} <small>${escapeHtml(d.uploaded_at || "")}</small></span>` +
          `<button type="button" class="btn secondary btn-sm" data-ai-del="${escapeHtml(d.id)}">${escapeHtml(t("aiDeleteDoc"))}</button></li>`
      )
      .join("");
  }

  function formatAiMessageHtml(text) {
    const raw = String(text == null ? "" : text);
    return escapeHtml(raw).replace(/\r\n|\r|\n/g, "<br>");
  }

  function renderAiPage(tab) {
    const msgs = (tab.messages || [])
      .map((m) => {
        const who = m.role === "assistant" ? "AI" : currentLang === "CHN" ? "您" : "You";
        const cls = m.role === "assistant" ? "assistant" : "user";
        let src = "";
        if (m.sources && m.sources.length) {
          src =
            `<ul class="ai-sources">` +
            m.sources
              .map(
                (s) =>
                  `<li><b>${escapeHtml(s.name || "")}</b> ${escapeHtml(s.snippet || "")}</li>`
              )
              .join("") +
            `</ul>`;
        }
        const body =
          cls === "assistant"
            ? `<div class="ai-msg-body">${formatAiMessageHtml(m.content || "")}</div>`
            : escapeHtml(m.content || "");
        return `<div class="ai-msg ${cls}"><b>${who}</b>${body}${src}</div>`;
      })
      .join("");
    return `<div class="ai-page" data-tab="${escapeHtml(tab.id)}">
      <div class="ai-layout">
        <section class="ai-chat">
          <div class="ai-toolbar">
            ${iconBtn(t("aiClearChat"), "edit-clear", "btn secondary btn-sm", 'data-ai-act="clear"')}
            ${iconBtn(t("aiSettings"), "theme", "btn secondary btn-sm", 'data-ai-act="settings"')}
          </div>
          <p class="ai-hint">${escapeHtml(t("aiHint"))}</p>
          <div class="ai-messages">${msgs}</div>
          <div class="ai-compose">
            <button type="button" class="btn secondary ai-compose-mini" data-ai-act="open-cmd" title="${escapeHtml(t("aiCommandOpen"))}" aria-label="${escapeHtml(t("aiCommandOpen"))}">…</button>
            <textarea id="ai-input" placeholder="${escapeHtml(t("aiPlaceholder"))}"></textarea>
            <div class="ai-compose-actions">
              ${iconBtn(t("aiCommandSave"), "save", "btn secondary", 'data-ai-act="save-cmd"')}
              ${iconBtn(t("aiSend"), "ai", "btn primary", 'data-ai-act="send"')}
            </div>
          </div>
        </section>
        <aside class="ai-docs">
          <h3>${escapeHtml(t("aiDocs"))}</h3>
          <div class="ai-doc-actions">
            <label class="btn secondary btn-sm">${escapeHtml(t("aiUpload"))}
              <input type="file" id="ai-file" hidden accept=".txt,.md,.csv,.json,.pdf,.docx,.xlsx,.xls">
            </label>
          </div>
          <ul class="ai-doc-list">${renderAiDocList(tab)}</ul>
        </aside>
      </div>
    </div>`;
  }

  function navigateAiPromptHistory(tab, input, direction) {
    const hist = tab.promptHistory || [];
    if (!hist.length || !input) return false;
    if (tab._histIdx == null || tab._histIdx < 0) {
      tab._histDraft = input.value;
      tab._histIdx = hist.length;
    }
    const next = tab._histIdx + direction;
    if (next < 0 || next > hist.length) return false;
    tab._histIdx = next;
    input.value = next === hist.length ? tab._histDraft || "" : hist[next] || "";
    const len = input.value.length;
    input.setSelectionRange(len, len);
    return true;
  }

  function bindAiPageEvents(tab) {
    const page = document.querySelector(`.ai-page[data-tab="${tab.id}"]`);
    if (!page) return;
    const input = page.querySelector("#ai-input");
    const send = () => sendAiMessage(tab, page).catch((err) => showAlert(err?.message || String(err)));
    page.querySelector('[data-ai-act="send"]')?.addEventListener("click", send);
    page.querySelector('[data-ai-act="clear"]')?.addEventListener("click", () => clearAiChat(tab));
    page.querySelector('[data-ai-act="settings"]')?.addEventListener("click", () =>
      openAiSettingsModal(tab).catch((err) => showAlert(err?.message || String(err)))
    );
    page.querySelector('[data-ai-act="save-cmd"]')?.addEventListener("click", () =>
      saveAiCommandChat(tab).catch((err) => showAlert(err?.message || String(err)))
    );
    page.querySelector('[data-ai-act="open-cmd"]')?.addEventListener("click", () =>
      openAiCommandLookup(input).catch((err) => showAlert(err?.message || String(err)))
    );
    input?.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
        return;
      }
      if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
      if (e.altKey || e.ctrlKey || e.metaKey) return;
      const val = input.value;
      const start = input.selectionStart ?? 0;
      const end = input.selectionEnd ?? 0;
      if (start !== end) return;
      const onFirstLine = !val.slice(0, start).includes("\n");
      const onLastLine = !val.slice(end).includes("\n");
      if (e.key === "ArrowUp" && onFirstLine && navigateAiPromptHistory(tab, input, -1)) {
        e.preventDefault();
      } else if (e.key === "ArrowDown" && onLastLine && navigateAiPromptHistory(tab, input, 1)) {
        e.preventDefault();
      }
    });
    page.querySelector("#ai-file")?.addEventListener("change", (e) => {
      const f = e.target.files && e.target.files[0];
      e.target.value = "";
      if (f) uploadAiDoc(tab, f).catch((err) => showAlert(err?.message || String(err)));
    });
    page.querySelector(".ai-doc-list")?.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-ai-del]");
      if (!btn) return;
      deleteAiDoc(tab, btn.getAttribute("data-ai-del")).catch((err) =>
        showAlert(err?.message || String(err))
      );
    });
    const box = page.querySelector(".ai-messages");
    if (box) box.scrollTop = box.scrollHeight;
    requestAnimationFrame(() => input?.focus());
  }

  async function uploadAiDoc(tab, file) {
    if (!file) return;
    try {
      const buf = await file.arrayBuffer();
      await api("/ai/upload", {
        method: "POST",
        body: JSON.stringify({ name: file.name || "upload.bin", content_base64: bytesToBase64(buf) }),
      });
      await refreshAiDocs(tab);
    } catch (err) {
      showAlert(err?.message || String(err));
      throw err;
    }
  }

  async function deleteAiDoc(tab, docId) {
    if (!docId) return;
    await api(`/ai/docs/${encodeURIComponent(docId)}`, { method: "DELETE" });
    await refreshAiDocs(tab);
  }

  function clearAiChat(tab) {
    if (tab._busy) return;
    const hasChat = (tab.messages || []).some((m) => m.role === "user");
    if (hasChat && !confirm(t("aiClearConfirm"))) return;
    tab.messages = [{ role: "assistant", content: t("aiWelcome") }];
    tab._busy = false;
    tab._histIdx = -1;
    tab._histDraft = "";
    if (activeTabId === tab.id) renderTabs();
  }

  async function openAiCommandLookup(input) {
    const meta = await api("/ai/command/open", { method: "POST", body: "{}" });
    await openLookupPicker(null, "CMD_PROMPT", "AI_COMMAND", "CMD_PROMPT", {
      doProc: meta.do_proc || "AI_COMMAND",
      onSelect: (val) => {
        if (!input) return;
        input.value = val || "";
        input.focus();
        const len = input.value.length;
        try {
          input.setSelectionRange(len, len);
        } catch (_e) {
          /* ignore */
        }
      },
    });
  }

  async function saveAiCommandChat(tab) {
    const page = document.querySelector(`.ai-page[data-tab="${tab.id}"]`);
    const input = page?.querySelector("#ai-input");
    let prompt = (input?.value || "").trim();
    let reply = "";
    if (!prompt) {
      const messages = (tab.messages || []).filter(
        (m) => m.role === "user" || m.role === "assistant"
      );
      for (let i = messages.length - 1; i >= 0; i--) {
        const m = messages[i];
        if (m.role === "user" && String(m.content || "").trim()) {
          prompt = String(m.content || "").trim();
          for (let j = i + 1; j < messages.length; j++) {
            if (messages[j].role === "assistant") {
              reply = String(messages[j].content || "").trim();
            }
          }
          break;
        }
      }
    }
    if (!prompt) {
      showAlert(t("aiCommandEmpty"));
      return;
    }
    const data = await api("/ai/command/save", {
      method: "POST",
      body: JSON.stringify({ prompt, reply, title: "" }),
    });
    showAlert(data.message || t("aiCommandSaved"));
  }

  let aiSettingsState = null;

  function closeAiSettingsModal() {
    const el = $("#ai-settings-modal-overlay");
    if (el) el.remove();
    aiSettingsState = null;
  }

  function renderAiModelSelect(data) {
    const models = data.models || [];
    const current = data.model || data.default_model || "gpt-4o-mini";
    const presetIds = new Set(models.map((m) => m.id).filter((id) => id !== "__custom__"));
    const isCustom = !presetIds.has(current);
    let opts = models
      .filter((m) => m.id !== "__custom__")
      .map(
        (m) =>
          `<option value="${escapeHtml(m.id)}"${m.id === current && !isCustom ? " selected" : ""}>${escapeHtml(m.label || m.id)}</option>`
      )
      .join("");
    opts += `<option value="__custom__"${isCustom ? " selected" : ""}>${escapeHtml(t("aiSettingsModelCustomOpt"))}</option>`;
    const customCls = isCustom ? "" : " hidden";
    const customVal = isCustom ? current : "";
    return `<label class="ai-settings-row ai-settings-model-row"><span>${escapeHtml(t("aiSettingsModel"))}</span>
          <div class="ai-settings-model-wrap">
            <select id="ai-set-model">${opts}</select>
            <input type="text" id="ai-set-model-custom" class="ai-settings-custom-model${customCls}" placeholder="${escapeHtml(t("aiSettingsModelCustomPh"))}" value="${escapeHtml(customVal)}" autocomplete="off">
          </div></label>`;
  }

  function bindAiModelSelectEvents(overlay) {
    const sel = overlay.querySelector("#ai-set-model");
    const custom = overlay.querySelector("#ai-set-model-custom");
    if (!sel || !custom) return;
    const sync = () => {
      const customMode = sel.value === "__custom__";
      custom.classList.toggle("hidden", !customMode);
      if (!customMode) custom.value = "";
    };
    sel.addEventListener("change", sync);
    sync();
  }

  function readAiSettingsModel() {
    const sel = $("#ai-set-model");
    if (!sel) return "";
    if (sel.value === "__custom__") {
      return ($("#ai-set-model-custom")?.value || "").trim();
    }
    return (sel.value || "").trim();
  }

  async function openAiSettingsModal(tab) {
    closeAiSettingsModal();
    const data = await api("/ai/settings");
    aiSettingsState = { tab, data };
    const hint = data.config_source === "env"
      ? t("aiSettingsEnvKey")
      : t("aiSettingsKeyHint", data.api_key_hint || "");
    const overlay = document.createElement("div");
    overlay.id = "ai-settings-modal-overlay";
    overlay.className = "ai-settings-overlay";
    overlay.innerHTML = `<div class="ai-settings-modal" role="dialog" aria-modal="true">
      <div class="ai-settings-header"><h3>${escapeHtml(t("aiSettingsTitle"))}</h3></div>
      <div class="ai-settings-body">
        <p class="ai-settings-shared">${escapeHtml(t("aiSettingsShared"))}</p>
        ${renderAiModelSelect(data)}
        <label class="ai-settings-row"><span>${escapeHtml(t("aiSettingsBaseUrl"))}</span>
          <input type="text" id="ai-set-base" value="${escapeHtml(data.base_url || "")}" autocomplete="off"></label>
        <label class="ai-settings-row"><span>${escapeHtml(t("aiSettingsApiKey"))}</span>
          <input type="password" id="ai-set-key" placeholder="${escapeHtml(t("aiSettingsApiKeyPh"))}" autocomplete="off"></label>
        <p class="ai-settings-hint">${escapeHtml(hint)}</p>
        <label class="ai-settings-check"><input type="checkbox" id="ai-set-clear-key"> ${escapeHtml(t("aiSettingsClearKey"))}</label>
      </div>
      <div class="ai-settings-actions">
        ${iconBtn(t("save"), "save", "btn primary", 'data-ai-set-act="save"')}
        ${iconBtn(t("cancel"), "cancel", "btn secondary", 'data-ai-set-act="cancel"')}
      </div>
    </div>`;
    document.body.appendChild(overlay);
    bindAiModelSelectEvents(overlay);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeAiSettingsModal();
    });
    overlay.querySelector('[data-ai-set-act="cancel"]')?.addEventListener("click", closeAiSettingsModal);
    overlay.querySelector('[data-ai-set-act="save"]')?.addEventListener("click", () =>
      saveAiSettings().catch((err) => showAlert(err?.message || String(err)))
    );
  }

  async function saveAiSettings() {
    if (!aiSettingsState) return;
    const model = readAiSettingsModel();
    if (!model) {
      showAlert(t("aiSettingsModelRequired"));
      return;
    }
    const baseUrl = ($("#ai-set-base")?.value || "").trim();
    const apiKey = ($("#ai-set-key")?.value || "").trim();
    const clearKey = !!$("#ai-set-clear-key")?.checked;
    await api("/ai/settings", {
      method: "PUT",
      body: JSON.stringify({
        model,
        base_url: baseUrl,
        api_key: apiKey,
        clear_api_key: clearKey,
      }),
    });
    closeAiSettingsModal();
    showAlert(t("aiSettingsSaved"));
  }

  async function sendAiMessage(tab, page) {
    const input = page.querySelector("#ai-input");
    const text = (input?.value || "").trim();
    if (!text || tab._busy) return;
    tab._busy = true;
    if (input) input.value = "";
    tab.promptHistory = tab.promptHistory || [];
    tab.promptHistory.push(text);
    tab._histIdx = -1;
    tab._histDraft = "";
    tab.messages = tab.messages || [];
    tab.messages.push({ role: "user", content: text });
    const box = page.querySelector(".ai-messages");
    if (box) {
      box.insertAdjacentHTML(
        "beforeend",
        `<div class="ai-msg user"><b>${currentLang === "CHN" ? "您" : "You"}</b>${escapeHtml(text)}</div>` +
          `<div class="ai-msg assistant" data-ai-pending="1"><b>AI</b>${escapeHtml(t("aiSending"))}</div>`
      );
      box.scrollTop = box.scrollHeight;
    }
    try {
      const activeTab = openTabs.find((x) => x.id === activeTabId);
      const work = activeTab?.type === "work" ? activeTab : null;
      const hist = (tab.messages || [])
        .filter((m) => m.role === "user" || m.role === "assistant")
        .slice(0, -1)
        .slice(-8)
        .map((m) => ({ role: m.role, content: m.content }));
      const data = await api("/ai/chat", {
        method: "POST",
        body: JSON.stringify({
          message: text,
          history: hist,
          active_do_proc: work?.doProc || "",
          table_name: work?.tableName || "",
        }),
      });
      const reply = data.reply || "";
      const sources = data.sources || [];
      tab.messages.push({ role: "assistant", content: reply, sources });
      const pending = page.querySelector("[data-ai-pending]");
      if (pending) {
        pending.removeAttribute("data-ai-pending");
        let src = "";
        if (sources.length) {
          src =
            `<ul class="ai-sources">` +
            sources
              .map((s) => `<li><b>${escapeHtml(s.name || "")}</b> ${escapeHtml(s.snippet || "")}</li>`)
              .join("") +
            `</ul>`;
        }
        pending.innerHTML = `<b>AI</b><div class="ai-msg-body">${formatAiMessageHtml(reply)}</div>${src}`;
      }
      await executeAiActions(data.actions || []);
    } catch (e) {
      const pending = page.querySelector("[data-ai-pending]");
      if (pending) pending.innerHTML = `<b>AI</b>${escapeHtml(e.message || String(e))}`;
      tab.messages.push({ role: "assistant", content: e.message || String(e) });
    } finally {
      tab._busy = false;
      const box2 = page.querySelector(".ai-messages");
      if (box2) box2.scrollTop = box2.scrollHeight;
    }
  }

  async function executeAiActions(actions) {
    for (const act of actions || []) {
      const kind = String(act.type || "").toLowerCase();
      const doProc = String(act.do_proc || "").trim();
      const title = act.title || doProc;
      if (kind === "export_related_xlsx") {
        const keyword = String(act.keyword || "").trim();
        if (!keyword) continue;
        const includeDate = act.include_date !== false;
        const includeQty = act.include_qty !== false;
        const fields = Array.isArray(act.fields) ? act.fields : [];
        try {
          const headers = { "Content-Type": "application/json" };
          if (token) headers.Authorization = `Bearer ${token}`;
          const res = await fetch("/api/ai/related/export/xlsx", {
            method: "POST",
            headers,
            body: JSON.stringify({
              keyword,
              fields,
              include_date: includeDate,
              include_qty: includeQty,
            }),
          });
          if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(apiErrorMessage(data, "匯出 XLSX 失敗。"));
          }
          const blob = await res.blob();
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = `related_${keyword}.xlsx`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          setTimeout(() => URL.revokeObjectURL(a.href), 5000);
          showAlert(currentLang === "CHN" ? `已匯出：${a.download}` : `Exported: ${a.download}`);
        } catch (e) {
          showAlert(e.message || "匯出 XLSX 失敗。");
        }
        continue;
      }
      if (kind === "open_work" && doProc) {
        await openWorkTab(doProc, title);
      } else if (kind === "close_all_tabs") {
        partyQueryModalState = null;
        stockQueryModalState = null;
        accountQueryModalState = null;
        openTabs = openTabs.filter((x) => x.type === "ai");
        const keep = openTabs.find((x) => x.type === "ai");
        activeTabId = keep ? keep.id : null;
        renderTabs();
      } else if (kind === "close_tab") {
        const tab = (doProc && findWorkTabByDoProc(doProc)) || currentWorkTab();
        if (tab && tab.type !== "ai") closeTab(tab.id);
      } else if (["add", "edit", "copy", "delete", "exit", "print", "query", "search"].includes(kind)) {
        let work = doProc ? findWorkTabByDoProc(doProc) : currentWorkTab();
        if (!work && doProc) {
          await openWorkTab(doProc, title);
          work = findWorkTabByDoProc(doProc);
        }
        if (!work) {
          showAlert(t("aiNeedWork"));
          continue;
        }
        activeTabId = work.id;
        if (kind === "add") await openDetailTab(work, "add", null);
        else if (kind === "edit") {
          if (work.selectedRow == null) {
            showAlert(t("selectRow"));
            continue;
          }
          await openDetailTab(work, "edit", work.selectedRow);
        } else if (kind === "copy") {
          if (work.selectedRow == null) {
            showAlert(t("selectRow"));
            continue;
          }
          await openDetailTab(work, "copy", work.selectedRow);
        } else if (kind === "delete") await doDelete(work);
        else if (kind === "exit") closeTab(work.id);
        else if (kind === "print") doPrint(work);
        else if (kind === "query") {
          const entityKey = pickQueryEntityKeyFromAction(act);
          if (await openQueryForWorkTab(work, { key: entityKey })) continue;
          await doOther(work);
        }         else if (kind === "search") {
          work.keyword = String(act.keyword || "").trim();
          work.filtered = false;
          await loadWorkData(work, { asFilter: false });
          renderTabs();
          if (work.keyword && work.selectedRow == null) {
            showAlert(
              currentLang === "CHN"
                ? `找不到「${work.keyword}」。`
                : `Cannot find "${work.keyword}".`
            );
          }
        }
      }
    }
  }

  function closeTab(id) {
    const tab = openTabs.find((x) => x.id === id);
    if (tab && tab.type === "party-query" && partyQueryModalState && partyQueryModalState.id === id) {
      partyQueryModalState = null;
    }
    if (tab && tab.type === "stock-query" && stockQueryModalState && stockQueryModalState.id === id) {
      stockQueryModalState = null;
    }
    if (
      tab &&
      tab.type === "account-query" &&
      accountQueryModalState &&
      accountQueryModalState.id === id
    ) {
      accountQueryModalState = null;
    }
    if (tab && tab.type === "work") {
      openTabs = openTabs.filter((x) => x.parentWorkId !== id && x.id !== id);
    } else {
      openTabs = openTabs.filter((x) => x.id !== id);
    }
    if (activeTabId === id) {
      activeTabId = openTabs.length ? openTabs[openTabs.length - 1].id : null;
    }
    renderTabs();
  }

  function getWorkTabForDetail(detailTab) {
    return openTabs.find((x) => x.id === detailTab.parentWorkId);
  }

  function clearTxRowsMasterKeys(txd, masterKeyCol) {
    const phys = txd.physical_fields || [];
    const keyCols = [masterKeyCol, "TX_KEY", "ID"].filter(Boolean);
    const keyU = new Set(keyCols.map((k) => String(k).toUpperCase()));
    const keyIdx = phys
      .map((f, i) => (keyU.has(String(f).toUpperCase()) ? i : -1))
      .filter((i) => i >= 0);
    txd.physical_rows = (txd.physical_rows || []).map((row) => {
      const r = clonePhysicalRow(row);
      keyIdx.forEach((i) => {
        if (i < r.length) r[i] = "";
      });
      return r;
    });
    syncTxDisplayRows(txd);
    return txd;
  }

  function emptyTxData(tx) {
    return normalizeTxData({
      tx_table: tx,
      fields: [],
      physical_fields: [],
      columns: [],
      physical_rows: [],
      rows: [],
      read_only: false,
    });
  }

  function clearFormValuesForCopy(workTab, formValues) {
    /** 複製：清空 EDIT_TYPE=ED 欄位，並清空主鍵候選欄。 */
    const out = { ...(formValues || {}) };
    const metas = [...(workTab?.formColumns || []), ...(workTab?.columns || [])];
    const byName = new Map(
      metas.map((m) => [String(m?.name || "").trim().toUpperCase(), m])
    );
    Object.keys(out).forEach((k) => {
      const meta = byName.get(String(k).trim().toUpperCase());
      if (String(meta?.edit_type || "").trim().toUpperCase() === "ED") {
        out[k] = "";
      }
    });
    const keyCandidates = [workTab?.printKeyColumn, workTab?.keyCodeColumn, "TX_KEY", "ID"].filter(
      Boolean
    );
    const keyU = new Set(keyCandidates.map((k) => String(k).toUpperCase()));
    Object.keys(out).forEach((k) => {
      if (keyU.has(String(k).toUpperCase())) out[k] = "";
    });
    return out;
  }

  async function resetDetailTabState(detail, workTab, mode, rowIndex) {
    const m = String(mode || "edit").trim().toLowerCase();
    let formValues = {};
    let sourceRowForTx = [];
    if (m === "add") {
      formValues = emptyFormValuesForAdd(workTab);
    } else {
      const src = workTab.physicalRows[rowIndex];
      sourceRowForTx = Array.isArray(src) ? clonePhysicalRow(src) : [];
      try {
        const fv = await api(`/work/${encodeURIComponent(workTab.doProc)}/form-values`, {
          method: "POST",
          body: JSON.stringify({ old_row: sourceRowForTx }),
        });
        formValues = fv.values || {};
      } catch (_) {
        workTab.formFields.forEach((f) => {
          const fi = workTab.physicalFields.indexOf(f);
          const raw = fi >= 0 && sourceRowForTx[fi] !== undefined ? sourceRowForTx[fi] : "";
          formValues[f] = raw == null ? "" : String(raw);
        });
      }
    }
    Object.keys(formValues).forEach((k) => {
      formValues[k] = formValues[k] == null ? "" : String(formValues[k]);
    });
    if (m === "copy") {
      formValues = clearFormValuesForCopy(workTab, formValues);
    }
    detail.mode = m;
    detail.rowIndex = rowIndex;
    detail.oldRow = m === "edit" ? sourceRowForTx : [];
    detail.formValues = formValues;
    detail.txData = {};
    if (detail.txFiles.length) {
      if (m === "add") {
        detail.txFiles.forEach((tx) => {
          detail.txData[tx] = emptyTxData(tx);
        });
      } else if (m === "copy") {
        for (const tx of detail.txFiles) {
          try {
            const txd = await api(
              `/work/${encodeURIComponent(workTab.doProc)}/tx/${encodeURIComponent(tx)}/rows`,
              { method: "POST", body: JSON.stringify({ physical_row: sourceRowForTx }) }
            );
            detail.txData[tx] = clearTxRowsMasterKeys(
              normalizeTxData(txd),
              workTab.printKeyColumn
            );
          } catch (_) {
            detail.txData[tx] = emptyTxData(tx);
          }
        }
      } else {
        for (const tx of detail.txFiles) {
          try {
            const txd = await api(
              `/work/${encodeURIComponent(workTab.doProc)}/tx/${encodeURIComponent(tx)}/rows`,
              { method: "POST", body: JSON.stringify({ physical_row: sourceRowForTx }) }
            );
            detail.txData[tx] = normalizeTxData(txd);
          } catch (_) {
            detail.txData[tx] = emptyTxData(tx);
          }
        }
      }
    }
  }

  async function openDetailTab(workTab, mode, rowIndex) {
    try {
      const m = String(mode || "edit").trim().toLowerCase();
      let suffix = String(rowIndex);
      if (m === "add") suffix = "new";
      else if (m === "copy") suffix = `copy-${rowIndex}`;
      const id = detailTabId(workTab.id, suffix);
      const existing = openTabs.find((x) => x.id === id);
      if (existing) {
        await resetDetailTabState(existing, workTab, m, rowIndex);
        activeTabId = id;
        renderTabs();
        return;
      }

      let formValues = {};
      let oldRow = [];
      let sourceRowForTx = [];
      const loadFromRow = m === "edit" || m === "copy";
      if (!loadFromRow) {
        formValues = emptyFormValuesForAdd(workTab);
      } else {
        const src = workTab.physicalRows[rowIndex];
        oldRow = Array.isArray(src) ? clonePhysicalRow(src) : [];
        sourceRowForTx = oldRow;
        try {
          const fv = await api(`/work/${encodeURIComponent(workTab.doProc)}/form-values`, {
            method: "POST",
            body: JSON.stringify({ old_row: oldRow }),
          });
          formValues = fv.values || {};
        } catch (_) {
          workTab.formFields.forEach((f) => {
            const fi = workTab.physicalFields.indexOf(f);
            const raw = fi >= 0 && oldRow[fi] !== undefined ? oldRow[fi] : "";
            formValues[f] = raw == null ? "" : String(raw);
          });
        }
      }
      // 確保表單值皆為字串，避免輸入控制項／日期正規化崩潰
      Object.keys(formValues).forEach((k) => {
        formValues[k] = formValues[k] == null ? "" : String(formValues[k]);
      });

      // 複製：清空 EDIT_TYPE=ED 與主鍵；明細自來源單據載入後再清空 TX 鍵欄
      if (m === "copy") {
        formValues = clearFormValuesForCopy(workTab, formValues);
      }

      const detail = {
        type: "detail",
        id,
        parentWorkId: workTab.id,
        doProc: workTab.doProc,
        procName: workTab.procName || "",
        title: workTab.menuTitle || workTab.title,
        mode: m,
        rowIndex,
        // 複製／新增儲存走 insert，不需舊列 WHERE；更改才保留 oldRow
        oldRow: m === "edit" ? oldRow : [],
        formValues,
        formFields: Array.isArray(workTab.formFields) ? workTab.formFields.slice() : [],
        formColumns: Array.isArray(workTab.formColumns) ? workTab.formColumns.slice() : [],
        txFiles: Array.isArray(workTab.txFiles) ? workTab.txFiles.slice() : [],
        txData: {},
        workActions: tabWorkActions(workTab),
      };

      if (detail.txFiles.length) {
        if (m === "add") {
          detail.txFiles.forEach((tx) => {
            detail.txData[tx] = emptyTxData(tx);
          });
        } else if (m === "copy") {
          for (const tx of detail.txFiles) {
            try {
              const txd = await api(
                `/work/${encodeURIComponent(workTab.doProc)}/tx/${encodeURIComponent(tx)}/rows`,
                { method: "POST", body: JSON.stringify({ physical_row: sourceRowForTx }) }
              );
              detail.txData[tx] = clearTxRowsMasterKeys(
                normalizeTxData(txd),
                workTab.printKeyColumn
              );
            } catch (_) {
              detail.txData[tx] = emptyTxData(tx);
            }
          }
        } else {
          for (const tx of detail.txFiles) {
            try {
              const txd = await api(
                `/work/${encodeURIComponent(workTab.doProc)}/tx/${encodeURIComponent(tx)}/rows`,
                { method: "POST", body: JSON.stringify({ physical_row: oldRow }) }
              );
              detail.txData[tx] = normalizeTxData(txd);
            } catch (_) {
              detail.txData[tx] = emptyTxData(tx);
            }
          }
        }
      }

      openTabs.push(detail);
      activeTabId = id;
      renderTabs();
    } catch (e) {
      showAlert(e && e.message ? e.message : String(e));
    }
  }

  async function buildFormDetailState(workTab, mode, rowIndex) {
    let formValues = {};
    let oldRow = [];
    if (mode === "add") {
      formValues = emptyFormValuesForAdd(workTab);
    } else {
      oldRow = (() => {
        const src = workTab.physicalRows[rowIndex];
        return Array.isArray(src) ? clonePhysicalRow(src) : [];
      })();
      try {
        const fv = await api(`/work/${encodeURIComponent(workTab.doProc)}/form-values`, {
          method: "POST",
          body: JSON.stringify({ old_row: oldRow }),
        });
        formValues = fv.values || {};
      } catch (_) {
        workTab.formFields.forEach((f) => {
          const fi = workTab.physicalFields.indexOf(f);
          const raw = fi >= 0 && oldRow[fi] !== undefined ? oldRow[fi] : "";
          formValues[f] = raw == null ? "" : String(raw);
        });
      }
    }
    Object.keys(formValues).forEach((k) => {
      formValues[k] = formValues[k] == null ? "" : String(formValues[k]);
    });
    const modeL = String(mode || "").trim().toLowerCase();
    if (modeL === "copy") {
      formValues = clearFormValuesForCopy(workTab, formValues);
    }

    const detail = {
      type: "detail",
      id: "form-modal",
      parentWorkId: workTab.id,
      doProc: workTab.doProc,
      procName: workTab.procName || "",
      title: workTab.menuTitle || workTab.title,
      mode,
      rowIndex,
      // 複製／新增走 insert；更改才保留 oldRow
      oldRow: modeL === "edit" ? oldRow : [],
      formValues,
      formFields: Array.isArray(workTab.formFields) ? workTab.formFields.slice() : [],
      formColumns: Array.isArray(workTab.formColumns) ? workTab.formColumns.slice() : [],
      txFiles: Array.isArray(workTab.txFiles) ? workTab.txFiles.slice() : [],
      txData: {},
      inModal: true,
    };

    if (workTab.txFiles.length && modeL === "add") {
      workTab.txFiles.forEach((tx) => {
        detail.txData[tx] = emptyTxData(tx);
      });
    } else if (workTab.txFiles.length && modeL === "copy") {
      for (const tx of workTab.txFiles) {
        try {
          const txd = await api(
            `/work/${encodeURIComponent(workTab.doProc)}/tx/${encodeURIComponent(tx)}/rows`,
            { method: "POST", body: JSON.stringify({ physical_row: oldRow }) }
          );
          detail.txData[tx] = clearTxRowsMasterKeys(
            normalizeTxData(txd),
            workTab.printKeyColumn
          );
        } catch (_) {
          detail.txData[tx] = emptyTxData(tx);
        }
      }
    } else if (workTab.txFiles.length) {
      for (const tx of workTab.txFiles) {
        try {
          const txd = await api(
            `/work/${encodeURIComponent(workTab.doProc)}/tx/${encodeURIComponent(tx)}/rows`,
            { method: "POST", body: JSON.stringify({ physical_row: oldRow }) }
          );
          detail.txData[tx] = normalizeTxData(txd);
        } catch (_) {
          detail.txData[tx] = emptyTxData(tx);
        }
      }
    }
    return detail;
  }

  function closeFormModal() {
    const el = $("#form-modal-overlay");
    if (el) {
      if (el._escHandler) {
        document.removeEventListener("keydown", el._escHandler, true);
      }
      el.remove();
    }
    formModalState = null;
  }

  async function persistDetailRecord(detail, page) {
    collectTxPhysicalRowsFromPage(page, detail);
    let values = collectFormValues(page);
    let manualKey = "";
    if (detail.mode === "add" || detail.mode === "copy") {
      const prepared = await prepareSaveKeyValues(detail, values);
      if (!prepared) return;
      values = prepared.values;
      manualKey = prepared.manualKey || "";
      applyFormValuesToPage(page, values);
      detail.formValues = { ...(detail.formValues || {}), ...values };
      await api(`/work/${encodeURIComponent(detail.doProc)}/insert`, {
        method: "POST",
        body: JSON.stringify({
          values,
          manual_key: manualKey,
          skip_key_prepare: true,
        }),
      });
    } else {
      await api(`/work/${encodeURIComponent(detail.doProc)}/update`, {
        method: "PUT",
        body: JSON.stringify({ values, old_row: detail.oldRow }),
      });
    }
    if (detail.txFiles.length) {
      for (const tx of detail.txFiles) {
        const txd = detail.txData[tx];
        renumberTxItemNo(txd);
        const txRows = txd?.physical_rows || [];
        await api(
          `/work/${encodeURIComponent(detail.doProc)}/tx/${encodeURIComponent(tx)}/save`,
          {
            method: "PUT",
            body: JSON.stringify({
              physical_rows: txRows,
              master_form_values: values,
              master_row: detail.oldRow,
            }),
          }
        );
      }
    }
    // NUM_CONTROL 或 NUM_TYPE 非空白（自動編號）：儲存後顯示所產生的編號
    if (detail.mode === "add" || detail.mode === "copy") {
      const workTab = getWorkTabForDetail(detail);
      const numControl = String(workTab?.numControlColumn || "").trim();
      const numType = String(workTab?.numTypeColumn || "").trim();
      const keyField = String(workTab?.keyCodeColumn || "").trim();
      if ((numControl || numType) && keyField) {
        let keyVal = "";
        const want = keyField.toUpperCase();
        for (const [f, v] of Object.entries(values || {})) {
          if (String(f).trim().toUpperCase() === want) {
            keyVal = String(v || "").trim();
            break;
          }
        }
        if (keyVal) {
          const col = (workTab?.columns || []).find(
            (c) => String(c?.name || "").toUpperCase() === want
          );
          const label = String(col?.title || keyField).trim() || keyField;
          const msg = String(t("savedNumberMsg") || "")
            .replace("{label}", label)
            .replace("{value}", keyVal);
          showAlert(msg, t("savedNumberTitle"));
        }
      }
    }
    const workTab = getWorkTabForDetail(detail);
    if (workTab) {
      const isNew = detail.mode === "add" || detail.mode === "copy";
      const anchor = physicalRowFromFormValues(workTab, values);
      // 新增／複製：定位到新紀錄；更改：定位到更新後同一筆
      await loadWorkData(workTab, {
        asFilter: workTab.filtered,
        preserveAnchor: true,
        anchorRow: anchor,
      });
      let idx = findWorkRowIndex(workTab, anchor);
      // 過濾結果找不到新紀錄時，改載全部再定位
      if (idx < 0 && isNew && workTab.filtered) {
        workTab.keyword = "";
        await loadWorkData(workTab, {
          asFilter: false,
          preserveAnchor: true,
          anchorRow: anchor,
        });
        idx = findWorkRowIndex(workTab, anchor);
      }
      if (idx >= 0) {
        workTab.selectedRow = idx;
        ensureWorkGridSelection(workTab);
        workTab.selectedRows.clear();
        workTab.selectedRows.add(idx);
      }
      activeTabId = workTab.id;
      renderTabs();
      requestAnimationFrame(() => {
        const page = document.querySelector(`.work-page[data-tab="${CSS.escape(workTab.id)}"]`);
        if (page && workTab.selectedRow != null && workTab.selectedRow >= 0) {
          selectWorkGridRow(workTab, page, workTab.selectedRow, { scroll: true, focus: true });
        }
      });
    }
  }

  async function openFormModal(workTab, mode, rowIndex) {
    try {
      const detail = await buildFormDetailState(workTab, mode, rowIndex);
      Object.keys(detail.formValues || {}).forEach((k) => {
        detail.formValues[k] = detail.formValues[k] == null ? "" : String(detail.formValues[k]);
      });
      closeFormModal();
      formModalState = detail;
      const overlay = document.createElement("div");
      overlay.id = "form-modal-overlay";
      overlay.className = "form-modal-overlay";
      const headerTitle =
        detail.mode === "add" ? t("addTitle", detail.title) : t("editTitle", detail.title);
      overlay.innerHTML = `<div class="form-modal" role="dialog" aria-modal="true">
      <div class="form-modal-header"><h2>${escapeHtml(headerTitle)}</h2></div>
      <div class="form-modal-body">${renderDetailPage(detail)}</div>
    </div>`;
      document.body.appendChild(overlay);
      const page = overlay.querySelector(".detail-page");
      bindDetailPageEvents(detail, {
        onCancel: closeFormModal,
        onSaved: closeFormModal,
        rootPage: page,
      });
      bindDateFields(page);
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) closeFormModal();
      });
      overlay._escHandler = (e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          closeFormModal();
        }
      };
      document.addEventListener("keydown", overlay._escHandler, true);
      syncFormFieldTabIndex(page);
      requestAnimationFrame(() => {
        const first = page.querySelector(
          ".detail-form-area input[data-field], .detail-form-area textarea[data-field]"
        );
        if (first) focusFormFieldElement(page, first);
      });
    } catch (e) {
      showAlert(e && e.message ? e.message : String(e));
    }
  }

  function tabLabel(tab) {
    if (tab.type === "ai") return t("aiTab");
    if (tab.type === "run-query") return tab.menuTitle || tab.title || t("runQueryTitle");
    if (tab.type === "work") return tab.menuTitle || tab.title;
    if (
      tab.type === "party-query" ||
      tab.type === "stock-query" ||
      tab.type === "account-query"
    ) {
      return tab.menuTitle || tab.title || t("queryUnsupported");
    }
    const mode = String(tab.mode || "edit").toLowerCase();
    const suffix =
      mode === "add" ? t("addSuffix") : mode === "copy" ? t("copySuffix") : t("detailSuffix");
    return `${tab.title} — ${suffix}`;
  }

  function renderQueryPage(active) {
    const kind =
      active.type === "party-query"
        ? "party"
        : active.type === "stock-query"
          ? "stock"
          : "account";
    const bodyHtml =
      kind === "party"
        ? renderPartyQueryModalBody(active)
        : kind === "stock"
          ? renderStockQueryModalBody(active)
          : renderAccountQueryModalBody(active);
    return `<div class="query-page work-page" data-query-kind="${kind}" data-tab="${escapeHtml(active.id)}">
      <div class="query-page-body arap-modal-body">${bodyHtml}</div>
    </div>`;
  }

  function bindQueryPageEvents(active) {
    const workTab = active.tab || getWorkTabForDetail(active) || active;
    if (active.type === "party-query") {
      partyQueryModalState = active;
      bindPartyQueryModalEvents(workTab);
    } else if (active.type === "stock-query") {
      stockQueryModalState = active;
      bindStockQueryModalEvents(workTab);
    } else if (active.type === "account-query") {
      accountQueryModalState = active;
      bindAccountQueryModalEvents(workTab);
    }
  }

  function renderTabs() {
    const bar = $("#tabs-bar");
    const content = $("#tabs-content");
    bar.innerHTML = "";

    if (!openTabs.length) {
      content.innerHTML = `<div class="empty-state"><p>${t("emptyMenu")}</p></div>`;
      return;
    }

    openTabs.forEach((tab, i) => {
      const btn = document.createElement("button");
      btn.className = "tab-btn" + (tab.id === activeTabId ? " active" : "");
      btn.style.color = tabTitleColor(i);
      btn.innerHTML = `<span class="tab-label">${escapeHtml(tabLabel(tab))}</span><span class="tab-close btn-icon-only" data-close="${tab.id}" title="${escapeHtml(t("exit"))}" aria-label="${escapeHtml(t("exit"))}">${uiIcon("window-close", 12)}</span>`;
      btn.addEventListener("click", (e) => {
        if (e.target.closest(".tab-close")) {
          e.stopPropagation();
          closeTab(tab.id);
        } else {
          const prevId = activeTabId;
          activeTabId = tab.id;
          renderTabs();
          if (tab.id !== prevId) {
            refreshOpenQueryTabFromServer(tab).catch((err) =>
              showAlert(err?.message || String(err))
            );
          }
        }
      });
      bar.appendChild(btn);
    });

    const active = openTabs.find((x) => x.id === activeTabId);
    if (!active) return;
    try {
      if (active.type === "ai") content.innerHTML = renderAiPage(active);
      else if (active.type === "run-query") content.innerHTML = renderRunQueryPage(active);
      else if (active.type === "work") content.innerHTML = renderWorkPage(active);
      else if (
        active.type === "party-query" ||
        active.type === "stock-query" ||
        active.type === "account-query"
      ) {
        content.innerHTML = renderQueryPage(active);
      } else content.innerHTML = renderDetailPage(active);
    } catch (e) {
      content.innerHTML = `<div class="empty-state"><p class="error">${escapeHtml(e && e.message ? e.message : String(e))}</p></div>`;
      showAlert(e && e.message ? e.message : String(e));
      return;
    }
    if (active.type === "ai") {
      bindAiPageEvents(active);
    } else if (active.type === "run-query") {
      bindRunQueryPageEvents(active);
    } else if (active.type === "work") {
      bindWorkPageEvents(active);
      const page = document.querySelector(`.work-page[data-tab="${active.id}"]`);
      if (page) {
        refreshWorkGridNavUi(page, active);
        requestAnimationFrame(() => {
          scrollWorkGridRowIntoView(active, page);
          focusWorkGridWrap(page);
        });
      }
    } else if (
      active.type === "party-query" ||
      active.type === "stock-query" ||
      active.type === "account-query"
    ) {
      bindQueryPageEvents(active);
    } else bindDetailPageEvents(active);
    if (active.type === "detail") {
      const dp = document.querySelector(`.detail-page[data-tab="${active.id}"]`);
      bindDateFields(dp);
      requestAnimationFrame(() => {
        const first = dp?.querySelector(
          ".detail-form-area input[data-field], .detail-form-area textarea[data-field]"
        );
        if (first) focusFormFieldElement(dp, first);
      });
    }
  }

  function renderWorkPage(tab) {
    initWorkColumnWidths(tab);
    const colTitles = tab.columns.map((c) => c.title || c.name);
    const thead = tab.fields
      .map((f, i) => {
        const ws = workColWidthStyle(tab, f);
        const sortInd = gridSortIndicatorHtml(tab.sortStack || [], i);
        return `<th class="grid-sortable" data-col="${escapeHtml(f)}" data-col-idx="${i}"${ws}><span class="th-text">${escapeHtml(colTitles[i] || f)}${sortInd}</span><span class="col-resizer" title="拖曳調整欄寬"></span></th>`;
      })
      .join("");
    const emptyCells = tab.fields
      .map((f) => {
        const ws = f ? workColWidthStyle(tab, f) : "";
        return `<td class="grid-pad-cell"${ws}>&nbsp;</td>`;
      })
      .join("");
    let tbody = "";
    if (tab.rows.length) {
      tbody = tab.rows
        .map((row, ri) => {
          const isCurRow = tab.selectedRow === ri;
          const curCol = tab.currentCol == null ? 0 : tab.currentCol;
          const cells = row
            .map((v, ci) => {
              const field = tab.fields[ci];
              const meta = (tab.columns || [])[ci] || {};
              const ws = field ? workColWidthStyle(tab, field) : "";
              const cls = gridCellAlignClass(meta);
              const curCell = isCurRow && curCol === ci ? " current-cell" : "";
              return `<td class="${cls.trim()}${curCell}" data-col-idx="${ci}"${ws}>${escapeHtml(v)}</td>`;
            })
            .join("");
          const sel =
            tab.selectedRows instanceof Set
              ? tab.selectedRows.has(ri)
              : tab.selectedRow === ri;
          const cls = [sel ? "selected" : "", isCurRow ? "current-row" : ""].filter(Boolean).join(" ");
          return `<tr data-row="${ri}" class="${cls}">${cells}</tr>`;
        })
        .join("");
      const padCount = Math.max(0, GRID_VISIBLE_ROWS - tab.rows.length);
      for (let i = 0; i < padCount; i++) {
        tbody += `<tr class="grid-pad-row" aria-hidden="true">${emptyCells}</tr>`;
      }
    } else {
      // 無資料時仍保留 20 列空白視區（與桌面 QTableView 一致）
      let pads = "";
      for (let i = 0; i < GRID_VISIBLE_ROWS; i++) {
        pads += `<tr class="grid-pad-row" aria-hidden="true">${emptyCells}</tr>`;
      }
      tbody = pads;
    }

    const cur =
      tab.selectedRow != null && tab.selectedRow >= 0 && tab.selectedRow < tab.rows.length
        ? tab.selectedRow + 1
        : null;
    const total = tab.rows.length;
    const navLabel = formatRecordNavLabel(total, cur);
    const totalRows = tab.rows.length;
    const row = tab.selectedRow;
    const noSel = row == null || row < 0 || row >= totalRows;
    const hasRows = totalRows > 0;
    const disFirst = !hasRows || (!noSel && row <= 0);
    const disPrev = !hasRows || noSel || row <= 0;
    const disNext = !hasRows || noSel || row >= totalRows - 1;
    const disLast = !hasRows || (!noSel && row >= totalRows - 1);
    const wa = tabWorkActions(tab);
    const actionCls = "btn action-btn work-action-btn";
    const attachBtn = isWorkFlagTrue(wa.need_attach)
      ? iconBtn(t("attachment"), "attachment", actionCls, 'data-act="attachment"')
      : "";
    const otherTitle = (wa.other_title || "").trim() || t("otherDefault");
    const otherDisabled = isWorkRowFullyPaid(tab);
    const otherBtn = isWorkFlagTrue(wa.need_other)
      ? iconBtn(
          otherTitle,
          "other",
          actionCls + (otherDisabled ? " disabled" : ""),
          `data-act="other"${otherDisabled ? " disabled" : ""}`
        )
      : "";
    const importBtn = isDataImportTab(tab)
      ? iconBtn(t("dataImport"), "database", actionCls, 'data-act="import"')
      : "";

    return `
      <div class="work-page" data-tab="${tab.id}">
        <div class="work-toolbar">
          <table class="work-toolbar-table">
            <tbody>
              <tr class="work-toolbar-search-row">
                <td>${iconBtn(t("filter"), "filter", actionCls, 'data-act="filter"')}</td>
                <td>${iconBtn(t("search"), "search", actionCls, 'data-act="search"')}</td>
                <td class="work-toolbar-label-cell">
                  <label class="search-label"><span class="work-toolbar-label-icon" aria-hidden="true">${uiIcon("search", 18)}</span><span>${t("searchLabel")}</span></label>
                </td>
                <td class="work-toolbar-input-cell">
                  <input type="text" class="search-input" value="${escapeHtml(tab.keyword)}">
                </td>
              </tr>
              <tr class="work-toolbar-actions-tr">
                <td colspan="4" class="work-toolbar-actions-cell">
                  <div class="work-toolbar-actions-row" role="toolbar" aria-label="${escapeHtml(currentLang === "CHN" ? "功能按鈕" : "Actions")}">
                    ${iconBtn(t("add"), "add", actionCls, 'data-act="add"')}
                    ${iconBtn(t("edit"), "edit", actionCls, 'data-act="edit"')}
                    ${iconBtn(t("del"), "delete", actionCls, 'data-act="delete"')}
                    ${iconBtn(t("copy"), "copy", actionCls, 'data-act="copy"')}
                    ${iconBtn(t("exit"), "exit", actionCls, 'data-act="exit"')}
                    ${iconBtn(t("refreshData"), "convert_db", actionCls, 'data-act="refresh"')}
                    ${iconBtn(t("print"), "print", actionCls, 'data-act="print"')}
                    ${importBtn}
                    ${attachBtn}
                    ${otherBtn}
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="work-table-wrap grid-focus-target work-grid-20-rows" tabindex="0">
          <table class="work-table">
            <thead><tr>${thead}</tr></thead>
            <tbody>${tbody}</tbody>
          </table>
        </div>
        <div class="nav-row">
          ${iconBtnOnly(t("navFirst"), "nav-first", "btn nav-btn", `data-nav="first"${disFirst ? " disabled" : ""}`)}
          ${iconBtnOnly(t("navPrev"), "nav-prev", "btn nav-btn", `data-nav="prev"${disPrev ? " disabled" : ""}`)}
          ${iconBtnOnly(t("navNext"), "nav-next", "btn nav-btn", `data-nav="next"${disNext ? " disabled" : ""}`)}
          ${iconBtnOnly(t("navLast"), "nav-last", "btn nav-btn", `data-nav="last"${disLast ? " disabled" : ""}`)}
          <span class="record-nav">${navLabel}</span>
        </div>
      </div>`;
  }

  function isLongTextField(meta) {
    const dt = (meta.data_type || "").toUpperCase();
    const name = (meta.name || "").toLowerCase();
    if (/note|remark|memo|備註|說明/.test(name)) return true;
    if (!dt) return false;
    if (dt === "MEMO" || dt === "LONGTEXT" || dt === "NTEXT") return true;
    return dt.includes("MEMO");
  }

  function isDateDataType(dt) {
    const t = String(dt || "").trim().toUpperCase();
    return t === "D" || t === "DATE" || t === "DATETIME" || t === "DT" || t === "TIME";
  }

  function isNumericDataType(dt) {
    const t = String(dt || "").trim().toUpperCase();
    return ["N", "NUM", "NUMBER", "NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "INT", "INTEGER", "CURRENCY", "MONEY", "BYTE"].includes(t);
  }

  function isStringDataType(dt) {
    const t = String(dt || "").trim().toUpperCase();
    return ["S", "STRING", "STR", "TEXT", "CHAR", "VARCHAR", "NVARCHAR", "MEMO", "LONGTEXT", "NTEXT"].includes(t);
  }

  function isBoolField(meta) {
    const t = String(meta.data_type || "").trim().toUpperCase();
    return ["B", "BOOL", "BOOLEAN", "LOGICAL", "BIT", "YESNO", "YN"].includes(t);
  }

  function dataFormatLooksLikeDate(df) {
    const u = String(df || "").trim().toUpperCase();
    if (!u) return false;
    return ["YYYY", "YY/", "/MM", "MM/", "/DD", "DD/", "日期"].some((x) => u.includes(x));
  }

  function fieldNameLooksLikeDate(name) {
    const s = String(name || "").trim().toUpperCase();
    if (!s) return false;
    return s.includes("DATE") || s.endsWith("DT") || String(name || "").includes("日期");
  }

  function isDateField(meta) {
    const dt = meta.data_type || "";
    if (isDateDataType(dt)) return true;
    if (isBoolField(meta) || isNumericDataType(dt) || isStringDataType(dt)) return false;
    // 無明確 DATA_TYPE 時：僅依欄名／日期格式判斷（勿把任意 DATA_FORMAT 當成日期）
    const fmt = meta.data_format || "";
    return fieldNameLooksLikeDate(meta.name) || dataFormatLooksLikeDate(fmt);
  }

  function isNumFormField(meta) {
    return isNumericDataType(meta.data_type) || meta.align === "right";
  }

  function sessionLoginDate() {
    return normalizeAppDateText(
      (currentUser && currentUser.login_date) || todayAppDate()
    );
  }

  function sessionCompanyCurrency() {
    const c = String((currentUser && currentUser.company_currency) || "").trim();
    return c || "HKD";
  }

  function isCurrencyCodeField(name) {
    const u = String(name || "").trim().toUpperCase();
    if (!u) return false;
    if (["TX_CURR", "CURRENCY", "CURR", "CO_CURR", "BASE_CURR", "HOME_CURR"].includes(u)) {
      return true;
    }
    return u.endsWith("_CURR");
  }

  function isExchangeRateField(name) {
    const u = String(name || "").trim().toUpperCase();
    return ["TX_RATE", "FIX_RATE", "EX_RATE", "EXCHANGE_RATE"].includes(u);
  }

  /** 新增表單初值：日期＝登入日期，貨幣＝公司貨幣，匯率＝1，數字＝0，其餘空白；DO_ARAP 另套專用預設。 */
  function emptyFormValuesForAdd(workTab) {
    const loginDate = sessionLoginDate();
    const companyCurr = sessionCompanyCurrency();
    const metas = [...(workTab?.formColumns || []), ...(workTab?.columns || [])];
    const byName = new Map();
    metas.forEach((m) => {
      if (!m || !m.name) return;
      byName.set(String(m.name).toUpperCase(), m);
      byName.set(String(m.name), m);
    });
    const out = {};
    (workTab.formFields || []).forEach((f) => {
      const meta =
        byName.get(String(f).toUpperCase()) ||
        byName.get(f) ||
        { name: f, data_type: "", data_format: "" };
      if (isDateField(meta)) out[f] = loginDate;
      else if (isCurrencyCodeField(f) || isCurrencyCodeField(meta.name)) out[f] = companyCurr;
      else if (isExchangeRateField(f) || isExchangeRateField(meta.name)) out[f] = "1";
      else if (isNumericDataType(meta.data_type)) out[f] = "0";
      else out[f] = "";
    });
    return applyProcNewRecordDefaults(out, workTab);
  }

  function isDoArapProc(workTab) {
    const proc = String(workTab?.procName || workTab?.proc_name || "").trim().toUpperCase();
    const doProc = String(workTab?.doProc || "").trim().toUpperCase();
    return ["DO_ARAP", "ARAP"].includes(proc) || ["DO_ARAP", "ARAP"].includes(doProc);
  }

  function applyProcNewRecordDefaults(values, workTab) {
    const out = { ...(values || {}) };
    if (!isDoArapProc(workTab)) return out;
    const defaults = { VOU_TYPE: "RJ", TX_TYPE: "AR", PAID_METHOD: "CHEQUE" };
    const fields = workTab?.formFields || Object.keys(out);
    const byUpper = new Map();
    fields.forEach((f) => {
      const name = String(f || "").trim();
      if (name) byUpper.set(name.toUpperCase(), name);
    });
    Object.keys(out).forEach((f) => {
      const name = String(f || "").trim();
      if (name && !byUpper.has(name.toUpperCase())) byUpper.set(name.toUpperCase(), name);
    });
    Object.entries(defaults).forEach(([key, val]) => {
      const fname = byUpper.get(key);
      if (!fname) return;
      if (!String(out[fname] || "").trim()) out[fname] = val;
    });
    return out;
  }

  function formLabelCaption(rawTitle) {
    let t = String(rawTitle || "").trim();
    if (!t) return "";
    while (t.length > 0 && [":", "：", "︰"].includes(t.slice(-1))) {
      t = t.slice(0, -1).trimEnd();
    }
    return `${t}:`;
  }

  function formFieldTitle(meta) {
    if (!meta) return "";
    if (currentLang === "ENG") {
      return (meta.eng_title || meta.title || meta.name || "").trim();
    }
    return (meta.chn_title || meta.title || meta.name || "").trim();
  }

  const FORM_LABEL_WIDTH_DEFAULT_PX = 180;
  const FORM_EDITOR_WIDTH_DEFAULT_PX = 220;
  const FORM_LABEL_WIDTH_PLANNED_PX = 240;
  const FORM_EDITOR_WIDTH_PLANNED_PX = 240;
  const FORM_EDITOR_HEIGHT_PX = 30;
  const FORM_LONG_TEXT_COL_SPAN = 2;
  const FORM_LONG_TEXT_ROW_SPAN = 2;
  const FORM_LABEL_WIDTH_PX = FORM_LABEL_WIDTH_DEFAULT_PX;
  const FORM_LABEL_WIDTH_MIN_PX = FORM_LABEL_WIDTH_DEFAULT_PX;
  const FORM_LABEL_WIDTH_MAX_PX = FORM_LABEL_WIDTH_DEFAULT_PX;
  const FORM_EDITOR_WIDTH_PX = FORM_EDITOR_WIDTH_DEFAULT_PX;

  function formLayoutDims(mode) {
    const planned = String(mode || getFormLayoutMode()) === FORM_LAYOUT_PLANNED;
    return planned
      ? {
          labelW: FORM_LABEL_WIDTH_PLANNED_PX,
          editorW: FORM_EDITOR_WIDTH_PLANNED_PX,
          editorH: FORM_EDITOR_HEIGHT_PX,
        }
      : {
          labelW: FORM_LABEL_WIDTH_DEFAULT_PX,
          editorW: FORM_EDITOR_WIDTH_DEFAULT_PX,
          editorH: FORM_EDITOR_HEIGHT_PX,
        };
  }

  function computeFormLabelWidthPx(fields, mode) {
    return formLayoutDims(mode).labelW;
  }

  function fieldEditLocked(meta, detailMode) {
    const et = String((meta && meta.edit_type) || "").trim().toUpperCase();
    if (et === "ED") return true;
    if (et === "AE") return String(detailMode || "edit").trim().toLowerCase() === "edit";
    return false;
  }

  function arapVouTypeForTxType(txType) {
    const u = String(txType || "").trim().toUpperCase();
    if (u === "AR") return "RJ";
    if (u === "AP") return "PJ";
    if (u === "ARAP") return "RPJ";
    return "";
  }

  function arapFieldLockedByTxType(fieldName, txType, detailOrTab) {
    if (!isDoArapProc(detailOrTab || {})) return false;
    const kind = String(txType || "").trim().toUpperCase();
    const key = String(fieldName || "").trim().toUpperCase();
    if (kind === "AR") return ["PAY_AMT", "VEND_DISC", "PAY_DISC"].includes(key);
    if (kind === "AP") return ["REC_AMT", "CUST_DISC", "REC_DISC"].includes(key);
    return false;
  }

  function formFieldForceLocked(meta, opts = {}) {
    const detail = opts.detail || opts.workTab || null;
    const txType =
      opts.txType != null
        ? opts.txType
        : (opts.formValues && (opts.formValues.TX_TYPE || opts.formValues.tx_type)) ||
          "";
    return (
      fieldEditLocked(meta, opts.detailMode) ||
      arapFieldLockedByTxType(meta && meta.name, txType, detail)
    );
  }

  function parseComboList(raw) {
    const text = String(raw || "").trim();
    if (!text) return [];
    const out = [];
    const seen = new Set();
    String(text)
      .split("/")
      .forEach((chunk) => {
        const s = String(chunk || "").trim();
        if (!s || seen.has(s)) return;
        seen.add(s);
        out.push(s);
      });
    return out;
  }

  function fieldUsesCombo(meta) {
    const choices = parseComboList(meta && meta.combo_list);
    if (choices.length) return true;
    const ct = String((meta && meta.ctrl_type) || "")
      .trim()
      .toUpperCase();
    return ct === "COMBO" || ct === "COMBOBOX" || ct === "DROPDOWN";
  }

  function renderFormField(meta, value, opts = {}) {
    const name = meta.name;
    const title = formLabelCaption(formFieldTitle(meta) || name);
    const labelW = opts.labelWidthPx || FORM_LABEL_WIDTH_MIN_PX;
    let captionWider = false;
    try {
      const canvas = document.createElement("canvas");
      const ctx = canvas.getContext("2d");
      const pt = getComputedStyle(document.documentElement).getPropertyValue("--form-label-pt").trim() || "12";
      const family = getComputedStyle(document.body).fontFamily || "sans-serif";
      if (ctx) {
        ctx.font = `700 ${pt}pt ${family}`;
        captionWider = ctx.measureText(title).width + 6 > labelW;
      }
    } catch (_) {
      captionWider = false;
    }
    const lookupKey = (meta.lookup_key || "").trim();
    const lookupDb = (meta.lookup_db || "").trim();
    const lookupRet = (meta.lookup_ret || "").trim();
    const locked = formFieldForceLocked(meta, opts);
    // 對齊桌面：LOOKUP_KEY + LOOKUP_DB 才顯示查找鈕；LOOKUP_RET 預設回寫本欄
    // 鎖定欄仍可 FOCUS，但不顯示 LOOKUP／日期選取（避免改值）
    const hasLookup = !locked && !!(lookupKey && lookupDb);
    const lookupAttrs = hasLookup
      ? ` data-lookup-db="${escapeHtml(lookupDb)}" data-lookup-ret="${escapeHtml(lookupRet || name)}" data-has-lookup="1"`
      : "";
    const roAttr = locked ? " readonly tabindex=\"0\"" : "";
    let inputHtml;
    const comboChoices = parseComboList(meta.combo_list);
    if (fieldUsesCombo(meta)) {
      if (locked) {
        // select[disabled] 無法聚焦；改為 readonly 輸入以保留 FOCUS 與標題同色背景
        inputHtml = `<input type="text" name="${escapeHtml(name)}" data-field="${escapeHtml(name)}" readonly tabindex="0" value="${escapeHtml(value || "")}">`;
      } else {
        const optsHtml = comboChoices
          .map((opt) => {
            const sel = String(value || "") === String(opt) ? " selected" : "";
            return `<option value="${escapeHtml(opt)}"${sel}>${escapeHtml(opt)}</option>`;
          })
          .join("");
        const extra =
          value && !comboChoices.includes(String(value))
            ? `<option value="${escapeHtml(value)}" selected>${escapeHtml(value)}</option>`
            : "";
        inputHtml = `<select name="${escapeHtml(name)}" data-field="${escapeHtml(name)}"${lookupAttrs}>${extra}${optsHtml}</select>`;
      }
    } else if (isBoolField(meta)) {
      const y = value === "Y" || value === "y" || value === "1" || value === "-1";
      const disp = y ? "Y" : value === "N" || value === "n" || value === "0" ? "N" : value || "";
      inputHtml = `<input type="text" class="bool-field" name="${escapeHtml(name)}" data-field="${escapeHtml(name)}"${lookupAttrs}${roAttr} value="${escapeHtml(disp)}" maxlength="1">`;
    } else if (isLongTextField(meta)) {
      inputHtml = `<textarea name="${escapeHtml(name)}" data-field="${escapeHtml(name)}"${lookupAttrs}${roAttr} rows="${FORM_LONG_TEXT_ROW_SPAN}">${escapeHtml(value)}</textarea>`;
    } else if (isDateField(meta)) {
      const fmt = meta.data_format || "yyyy/MM/dd";
      const val = normalizeAppDateText(value);
      const dateBtn = locked
        ? ""
        : `<button type="button" class="btn secondary date-pick-btn btn-icon-only" data-date-for="${escapeHtml(name)}" title="${escapeHtml(t("printDatePickBtn"))}">${uiIcon("view-calendar", 14)}</button>`;
      inputHtml = `<div class="date-field-wrap">
        <input type="text" class="app-date-input" name="${escapeHtml(name)}" data-field="${escapeHtml(name)}"${lookupAttrs}${roAttr} value="${escapeHtml(val)}" placeholder="${escapeHtml(fmt)}">
        ${dateBtn}
      </div>`;
    } else {
      const cls = isNumFormField(meta) ? "num-field" : "";
      inputHtml = `<input type="text" class="${cls}" name="${escapeHtml(name)}" data-field="${escapeHtml(name)}"${lookupAttrs}${roAttr} value="${escapeHtml(value)}">`;
    }
    if (hasLookup) {
      inputHtml = `<div class="lookup-field-wrap">${inputHtml}<button type="button" class="btn secondary lookup-btn" data-lookup-field="${escapeHtml(name)}" data-lookup-db="${escapeHtml(lookupDb)}" data-lookup-ret="${escapeHtml(lookupRet || name)}" onclick="return window.__woleeOpenLookup && window.__woleeOpenLookup(this, event)" title="${escapeHtml(t("lookup"))}" aria-label="${escapeHtml(t("lookup"))}">…</button></div>`;
    }
    const wide = isLongTextField(meta);
    const planned = opts.layoutMode === FORM_LAYOUT_PLANNED;
    const labelCls = !planned && (captionWider || wide) ? "form-label-wrap" : "";
    const longCols = Math.max(1, Number(opts.longSpanCols) || FORM_LONG_TEXT_COL_SPAN);
    const longRows = Math.max(1, Number(opts.longSpanRows) || FORM_LONG_TEXT_ROW_SPAN);
    const wideStyle = wide
      ? ` style="--form-long-cols:${longCols};--form-long-rows:${longRows}"`
      : "";
    const fieldCls = [
      "form-field",
      wide ? "form-field-wide" : "",
      planned ? "form-field-stacked" : "",
      locked ? "form-field-locked" : "",
    ]
      .filter(Boolean)
      .join(" ");
    return `<div class="${fieldCls}"${wideStyle}>
      <label class="${labelCls}">${escapeHtml(title)}</label>${inputHtml}
    </div>`;
  }

  function renderFormGridSlots(fields, formValues, cols, rowsPerPage, opts = {}) {
    const planned = opts.layoutMode === FORM_LAYOUT_PLANNED;
    const colCount = planned
      ? Math.max(1, Math.min(5, Number(cols) || 3))
      : Math.max(1, Math.min(3, Number(cols) || 2));
    const rowCount = planned
      ? Math.max(1, Math.min(5, Number(rowsPerPage) || 5))
      : Math.max(1, Math.min(10, Number(rowsPerPage) || 10));
    const totalSlots = colCount * rowCount;
    const labelWidthPx =
      opts.labelWidthPx != null
        ? opts.labelWidthPx
        : computeFormLabelWidthPx(fields, opts.layoutMode);
    const cells = [];
    let col = 0;
    let slotsUsed = 0;
    const fillerHtml = `<div class="form-slot-filler" aria-hidden="true"></div>`;

    const pushFiller = () => {
      cells.push(fillerHtml);
      slotsUsed += 1;
      col += 1;
      if (col >= colCount) col = 0;
    };

    const padToRowEnd = () => {
      if (col <= 0) return;
      const need = colCount - col;
      for (let i = 0; i < need; i++) pushFiller();
    };

    (Array.isArray(fields) ? fields : []).forEach((meta) => {
      if (!meta || !meta.name) return;
      if (isLongTextField(meta)) {
        const spanCols = Math.min(FORM_LONG_TEXT_COL_SPAN, colCount);
        const spanRows = FORM_LONG_TEXT_ROW_SPAN;
        if (col + spanCols > colCount) padToRowEnd();
        cells.push(
          renderFormField(meta, (formValues && formValues[meta.name]) || "", {
            labelWidthPx,
            layoutMode: opts.layoutMode,
            detailMode: opts.detailMode,
            detail: opts.detail,
            formValues,
            longSpanCols: spanCols,
            longSpanRows: spanRows,
          })
        );
        slotsUsed += spanCols * spanRows;
        col += spanCols;
        // 右側剩餘欄位槽以空白補滿（含跨列高度），下一欄從長文字下方開始
        if (col < colCount) {
          const remain = (colCount - col) * spanRows;
          for (let i = 0; i < remain; i++) {
            cells.push(fillerHtml);
            slotsUsed += 1;
          }
        }
        col = 0;
        return;
      }
      cells.push(
        renderFormField(meta, (formValues && formValues[meta.name]) || "", {
          labelWidthPx,
          layoutMode: opts.layoutMode,
          detailMode: opts.detailMode,
          detail: opts.detail,
          formValues,
        })
      );
      slotsUsed += 1;
      col += 1;
      if (col >= colCount) col = 0;
    });

    // 不足一頁時補空白槽（有上限，避免 while 失控）
    const remain = Math.max(0, totalSlots - slotsUsed);
    for (let i = 0; i < remain; i++) pushFiller();

    return { html: cells.join(""), labelWidthPx };
  }

  function openAppDatePicker(targetEl, onChange) {
    if (!targetEl) return;
    const picker = document.createElement("input");
    picker.type = "date";
    picker.style.position = "fixed";
    picker.style.left = "-9999px";
    picker.style.opacity = "0";
    document.body.appendChild(picker);
    const parsed = parseAppDate(normalizeAppDateText(targetEl.value));
    if (parsed) {
      picker.value = `${parsed.y}-${String(parsed.mo).padStart(2, "0")}-${String(parsed.d).padStart(2, "0")}`;
    }
    const cleanup = () => picker.remove();
    picker.addEventListener("change", () => {
      if (picker.value) {
        const [y, mo, d] = picker.value.split("-").map((x) => parseInt(x, 10));
        targetEl.value = `${y}/${String(mo).padStart(2, "0")}/${String(d).padStart(2, "0")}`;
        if (onChange) onChange();
      }
      cleanup();
    });
    picker.addEventListener("blur", cleanup, { once: true });
    if (typeof picker.showPicker === "function") picker.showPicker();
    else picker.click();
  }

  function bindDateFields(root, onChange) {
    if (!root) return;
    root.querySelectorAll(".app-date-input").forEach((inp) => {
      inp.addEventListener("blur", () => {
        inp.value = normalizeAppDateText(inp.value);
      });
    });
    root.querySelectorAll(".date-pick-btn[data-date-for]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const name = btn.dataset.dateFor;
        const inp = root.querySelector(`[data-field="${CSS.escape(name)}"]`);
        openAppDatePicker(inp, onChange);
      });
    });
  }

  function resolveDetailDoProc(detail) {
    const direct = String(detail?.doProc || detail?.workDoProc || "").trim();
    if (direct) return direct;
    const parentId = String(detail?.parentWorkId || "").trim();
    if (!parentId) return "";
    const work = openTabs.find((t) => t && t.type === "work" && t.id === parentId);
    return String(work?.doProc || "").trim();
  }

  async function openLookupPicker(detail, fieldName, lookupDb, lookupRet, opts = {}) {
    const doProc = String(opts.doProc || resolveDetailDoProc(detail) || "").trim();
    const lookupTable = String(lookupDb || "").trim();
    if (!doProc || !lookupTable) {
      showAlert(currentLang === "CHN" ? "LOOKUP 設定不完整。" : "Lookup configuration is incomplete.");
      return;
    }
    let data;
    try {
      data = await api(`/work/${encodeURIComponent(doProc)}/lookup/rows`, {
        method: "POST",
        body: JSON.stringify({ lookup_db: lookupTable, keyword: "", as_filter: false }),
      });
    } catch (e) {
      showAlert(e.message || "Lookup failed");
      return;
    }
    const fields = Array.isArray(data?.fields) ? data.fields : [];
    const columns = Array.isArray(data?.columns) ? data.columns : [];
    const rows = Array.isArray(data?.rows) ? data.rows : [];
    const physicalRows = Array.isArray(data?.physical_rows) ? data.physical_rows : rows;
    const physicalFields = Array.isArray(data?.physical_fields) ? data.physical_fields : fields;
    const titleBy = new Map(columns.map((c) => [c.name, c.title || c.name]));
    let selected = rows.length ? 0 : -1;
    const overlay = document.createElement("div");
    overlay.className = "arap-modal-overlay";
    const navDisabled = (nav) => {
      const total = rows.length;
      const hasRows = total > 0;
      const noSel = selected < 0;
      const row = selected;
      if (nav === "first") return !hasRows || (!noSel && row <= 0);
      if (nav === "prev") return !hasRows || noSel || row <= 0;
      if (nav === "next") return !hasRows || noSel || row >= total - 1;
      if (nav === "last") return !hasRows || (!noSel && row >= total - 1);
      return true;
    };
    const renderBody = () => {
      const thead = fields.map((f) => `<th>${escapeHtml(titleBy.get(f) || f)}</th>`).join("");
      const tbody = rows.length
        ? rows
            .map((r, i) => {
              const cells = r.map((c) => `<td>${escapeHtml(c)}</td>`).join("");
              return `<tr data-lu-row="${i}" class="${i === selected ? "selected" : ""}">${cells}</tr>`;
            })
            .join("")
        : `<tr><td colspan="99">${t("noData")}</td></tr>`;
      const navLabel = formatRecordNavLabel(rows.length, selected >= 0 ? selected + 1 : null);
      return `<div class="work-table-wrap" style="max-height:360px;overflow:auto"><table class="work-table"><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table></div>
        <div class="nav-row lookup-nav-row">
          ${iconBtnOnly(t("navFirst"), "nav-first", "btn nav-btn", `data-lu-nav="first"${navDisabled("first") ? " disabled" : ""}`)}
          ${iconBtnOnly(t("navPrev"), "nav-prev", "btn nav-btn", `data-lu-nav="prev"${navDisabled("prev") ? " disabled" : ""}`)}
          ${iconBtnOnly(t("navNext"), "nav-next", "btn nav-btn", `data-lu-nav="next"${navDisabled("next") ? " disabled" : ""}`)}
          ${iconBtnOnly(t("navLast"), "nav-last", "btn nav-btn", `data-lu-nav="last"${navDisabled("last") ? " disabled" : ""}`)}
          <span class="record-nav">${escapeHtml(navLabel)}</span>
        </div>`;
    };
    overlay.innerHTML = `<div class="arap-modal" role="dialog" aria-modal="true">
      <div class="arap-modal-header"><h2>Lookup — ${escapeHtml(lookupTable)}</h2></div>
      <div class="arap-modal-body">
        <div class="lookup-modal-body">${renderBody()}</div>
      </div>
      <div class="arap-modal-footer">
        <button type="button" class="btn secondary" data-lu="cancel">${t("cancel")}</button>
        <button type="button" class="btn action-btn" data-lu="ok">${t("msgOk") || "OK"}</button>
      </div>
    </div>`;
    document.body.appendChild(overlay);
    const bodyHost = overlay.querySelector(".lookup-modal-body");
    const applySelection = () => {
      if (selected < 0 || !rows.length) return;
      const ret = (lookupRet || fieldName || "").trim().toUpperCase();
      let idx = physicalFields.findIndex((f) => String(f).toUpperCase() === ret);
      if (idx < 0) idx = 0;
      const prow = physicalRows[selected] || [];
      const val = prow[idx] != null ? String(prow[idx]) : "";
      overlay.remove();
      if (typeof opts.onSelect === "function") {
        opts.onSelect(val);
        if (typeof opts.onClose === "function") opts.onClose(val);
        return;
      }
      const page =
        (detail && $(`.detail-page[data-tab="${detail.id}"]`)) ||
        document.querySelector(".form-modal-overlay .detail-page") ||
        document;
      const inp =
        page.querySelector(`[data-field="${CSS.escape(fieldName)}"]`) ||
        page.querySelector(`[name="${CSS.escape(fieldName)}"]`);
      if (inp) {
        inp.value = val;
        inp.dispatchEvent(new Event("change", { bubbles: true }));
      }
      // LOOKUP 關閉後焦點回到輸入欄；並觸發 SEARCH_RET（若有）
      if (inp) {
        requestAnimationFrame(() => {
          focusFormFieldElement(page, inp);
          if (typeof inp.select === "function") inp.select();
          if (detail) applyFormFieldSearchRet(page, detail, inp).catch(() => {});
        });
      }
    };
    const closeLookup = () => {
      overlay.remove();
      if (typeof opts.onClose === "function") {
        opts.onClose(null);
        return;
      }
      if (typeof opts.onSelect === "function") return;
      const page =
        (detail && $(`.detail-page[data-tab="${detail.id}"]`)) ||
        document.querySelector(".form-modal-overlay .detail-page") ||
        document;
      const inp =
        page.querySelector(`[data-field="${CSS.escape(fieldName)}"]`) ||
        page.querySelector(`[name="${CSS.escape(fieldName)}"]`);
      if (inp) {
        requestAnimationFrame(() => focusFormFieldElement(page, inp));
      }
    };
    const selectLookupRow = (row) => {
      const n = rows.length;
      if (n <= 0) return;
      selected = Math.max(0, Math.min(row, n - 1));
      bodyHost.innerHTML = renderBody();
      rebind();
      const tr = bodyHost.querySelector(`tr[data-lu-row="${selected}"]`);
      if (tr) tr.scrollIntoView({ block: "nearest" });
    };
    const rebind = () => {
      bodyHost.querySelectorAll("tr[data-lu-row]").forEach((tr) => {
        tr.addEventListener("click", () => {
          selectLookupRow(Number(tr.dataset.luRow) || 0);
        });
        tr.addEventListener("dblclick", () => {
          selected = Number(tr.dataset.luRow) || 0;
          applySelection();
        });
      });
      bodyHost.querySelectorAll("[data-lu-nav]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const nav = btn.dataset.luNav;
          const n = rows.length;
          if (!n) return;
          if (nav === "first") selectLookupRow(0);
          else if (nav === "last") selectLookupRow(n - 1);
          else if (nav === "prev" && selected > 0) selectLookupRow(selected - 1);
          else if (nav === "next" && selected >= 0 && selected < n - 1) selectLookupRow(selected + 1);
        });
      });
    };
    rebind();
    overlay.querySelector('[data-lu="cancel"]').addEventListener("click", closeLookup);
    overlay.querySelector('[data-lu="ok"]').addEventListener("click", applySelection);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeLookup();
    });
  }

  function bindLookupButtons(page, detail) {
    if (!page || !detail) return;
    if (page._lookupDelegateBound) return;
    page._lookupDelegateBound = true;
    page.addEventListener("click", (e) => {
      const btn = e.target && e.target.closest ? e.target.closest(".lookup-btn[data-lookup-field]") : null;
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      const fieldName = btn.dataset.lookupField || "";
      const lookupDb = btn.dataset.lookupDb || "";
      const lookupRet = btn.dataset.lookupRet || "";
      openLookupPicker(detail, fieldName, lookupDb, lookupRet).catch((err) => {
        showAlert(err?.message || String(err) || "Lookup failed");
      });
    });
  }

  function _detailFromElement(el) {
    const detailPage = el?.closest?.(".detail-page[data-tab]");
    const tabId = detailPage?.dataset?.tab || "";
    if (tabId) {
      const d = openTabs.find((t) => t && t.type === "detail" && t.id === tabId);
      if (d) return d;
    }
    if (formModalState && formModalState.type === "detail") return formModalState;
    const active = openTabs.find((t) => t && t.id === activeTabId);
    return active && active.type === "detail" ? active : null;
  }

  function bindGlobalLookupButtons() {
    if (document._lookupGlobalBound) return;
    document._lookupGlobalBound = true;
    document.addEventListener(
      "click",
      (e) => {
        const btn = e.target?.closest?.(".lookup-btn[data-lookup-field]");
        if (!btn) return;
        e.preventDefault();
        e.stopPropagation();
        const detail = _detailFromElement(btn);
        if (!detail) {
          showAlert(currentLang === "CHN" ? "無法取得明細內容。" : "Cannot resolve detail context.");
          return;
        }
        openLookupPicker(
          detail,
          btn.dataset.lookupField || "",
          btn.dataset.lookupDb || "",
          btn.dataset.lookupRet || ""
        ).catch((err) => {
          showAlert(err?.message || String(err) || "Lookup failed");
        });
      },
      true
    );
  }

  window.__woleeOpenLookup = function (btn, ev) {
    try {
      if (ev) {
        ev.preventDefault();
        ev.stopPropagation();
      }
      const detail = _detailFromElement(btn);
      if (!detail) {
        showAlert(currentLang === "CHN" ? "無法取得明細內容。" : "Cannot resolve detail context.");
        return false;
      }
      const fieldName = btn?.dataset?.lookupField || "";
      let lookupDb = btn?.dataset?.lookupDb || "";
      let lookupRet = btn?.dataset?.lookupRet || "";
      if (!lookupDb && fieldName) {
        const meta = formColumnMeta(detail, fieldName);
        lookupDb = String(meta?.lookup_db || "").trim();
        lookupRet = String(meta?.lookup_ret || fieldName).trim();
      }
      if (!lookupDb) {
        showAlert(
          currentLang === "CHN"
            ? `欄位「${fieldName}」未設定 LOOKUP_DB。`
            : `Field "${fieldName}" has no LOOKUP_DB.`
        );
        return false;
      }
      openLookupPicker(detail, fieldName, lookupDb, lookupRet).catch((err) => {
        showAlert(err?.message || String(err) || "Lookup failed");
      });
    } catch (err) {
      showAlert(err?.message || String(err) || "Lookup failed");
    }
    return false;
  };

  function clonePhysicalRow(r) {
    if (!Array.isArray(r)) return [];
    return r.map((c) => (c == null ? "" : String(c)));
  }

  function normalizeTxData(txd) {
    const rowsIn = Array.isArray(txd.physical_rows) ? txd.physical_rows : [];
    txd.physical_rows = rowsIn.map(clonePhysicalRow);
    txd.physical_fields = Array.isArray(txd.physical_fields) ? txd.physical_fields : [];
    txd.fields = Array.isArray(txd.fields) ? txd.fields : [];
    txd.columns = Array.isArray(txd.columns) ? txd.columns : [];
    txd.selectedRow = txd.selectedRow != null ? txd.selectedRow : null;
    if (txd.currentCol == null || txd.currentCol < 0) txd.currentCol = 0;
    if (!txd.selectedRows || !(txd.selectedRows instanceof Set)) {
      txd.selectedRows = new Set();
      if (txd.selectedRow != null && txd.selectedRow >= 0) txd.selectedRows.add(txd.selectedRow);
    }
    txd.keyword = txd.keyword || "";
    txd.columnWidths = txd.columnWidths || {};
    if (!Array.isArray(txd.sortStack)) txd.sortStack = [];
    if (!txd.rows || !txd.rows.length) {
      syncTxDisplayRows(txd);
    }
    applyTxGridSort(txd);
    return txd;
  }

  function syncTxDisplayRows(txd) {
    txd.rows = txd.physical_rows.map((prow) =>
      txd.fields.map((f) => {
        const pi = txd.physical_fields.indexOf(f);
        return pi >= 0 && prow[pi] !== undefined ? prow[pi] : "";
      })
    );
  }

  function collectFormValues(page) {
    const values = {};
    $$("[data-field]", page).forEach((el) => {
      values[el.dataset.field] = el.value;
    });
    return values;
  }

  function applyFormValuesToPage(page, values) {
    Object.entries(values || {}).forEach(([field, val]) => {
      const el = page.querySelector(`[data-field="${CSS.escape(field)}"]`);
      if (el) el.value = val == null ? "" : String(val);
    });
  }

  function promptKeyAssign(prep, detail) {
    return new Promise((resolve) => {
      const overlay = document.createElement("div");
      overlay.id = "key-assign-overlay";
      overlay.className = "form-modal-overlay";
      const label = escapeHtml(prep.key_label || prep.key_field || "");
      const suggested = escapeHtml(prep.suggested_key || "");
      const lookupDb = String(prep.lookup_db || prep.table_name || "").trim();
      const lookupRet = String(prep.lookup_ret || prep.key_field || "").trim();
      const hasLookup = !!(lookupDb && (detail?.doProc || resolveDetailDoProc(detail)));
      overlay.innerHTML = `<div class="form-modal key-assign-modal" role="dialog" aria-modal="true">
        <div class="form-modal-header"><h2>${escapeHtml(t("keyAssignTitle"))}</h2></div>
        <div class="form-modal-body">
          <p class="message-modal-hint">${escapeHtml(t("keyAssignHint"))}</p>
          <div class="key-assign-row">
            <label class="key-assign-label">${label ? `${label}:` : ""}</label>
            <div class="lookup-field-wrap key-assign-input-wrap">
              <input id="key-assign-input" type="text" value="${suggested}" />
              ${
                hasLookup
                  ? `<button type="button" class="btn secondary lookup-btn" id="key-assign-lookup" title="${escapeHtml(t("lookup"))}" aria-label="${escapeHtml(t("lookup"))}">…</button>`
                  : ""
              }
            </div>
          </div>
          <div class="message-modal-actions">
            <button type="button" class="action-btn" data-act="ok">${escapeHtml(t("printPickOk") || t("save") || "Save")}</button>
            <button type="button" class="btn secondary" data-act="cancel">${escapeHtml(t("cancel"))}</button>
          </div>
        </div>
      </div>`;
      document.body.appendChild(overlay);
      const input = overlay.querySelector("#key-assign-input");
      const focusKey = () => {
        requestAnimationFrame(() => {
          input?.focus();
          if (typeof input?.select === "function") input.select();
        });
      };
      const finish = (value) => {
        overlay.remove();
        resolve(value);
      };
      overlay.querySelector("#key-assign-lookup")?.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        openLookupPicker(
          detail,
          prep.key_field || "",
          lookupDb,
          lookupRet,
          {
            doProc: detail?.doProc || resolveDetailDoProc(detail),
            onSelect: (val) => {
              if (val != null && String(val).trim()) {
                input.value = String(val).trim();
              }
            },
            onClose: () => focusKey(),
          }
        ).catch((err) => {
          showAlert(err?.message || "Lookup failed");
          focusKey();
        });
      });
      overlay.querySelector('[data-act="ok"]')?.addEventListener("click", () => {
        const v = (input?.value || "").trim();
        if (!v) {
          showAlert(t("keyAssignEmpty"));
          focusKey();
          return;
        }
        finish(v);
      });
      overlay.querySelector('[data-act="cancel"]')?.addEventListener("click", () => finish(null));
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) finish(null);
      });
      focusKey();
    });
  }

  async function prepareSaveKeyValues(detail, values) {
    let manualKey = "";
    for (;;) {
      const prep = await api(`/work/${encodeURIComponent(detail.doProc)}/prepare-key`, {
        method: "POST",
        body: JSON.stringify({
          values,
          mode: detail.mode,
          manual_key: manualKey,
        }),
      });
      if (!prep.manual_required) {
        return { values: prep.values || values, manualKey };
      }
      const assigned = await promptKeyAssign(prep, detail);
      if (!assigned) return null;
      manualKey = assigned;
    }
  }

  function resolveMasterKeyForTx(detail, formValues) {
    const workTab = getWorkTabForDetail(detail);
    const printKey = workTab && workTab.printKeyColumn;
    if (printKey && (formValues[printKey] || "").trim()) {
      return { col: printKey, val: formValues[printKey].trim() };
    }
    for (const f of detail.formFields) {
      if (f.toUpperCase() === "TX_KEY" && (formValues[f] || "").trim()) {
        return { col: f, val: formValues[f].trim() };
      }
    }
    return { col: null, val: null };
  }

  function txKeyColOnTable(txd, masterKeyCol) {
    if (masterKeyCol) {
      const c = txd.physical_fields.find((f) => f.toUpperCase() === masterKeyCol.toUpperCase());
      if (c) return c;
    }
    return (
      txd.physical_fields.find((f) => f.toUpperCase() === "TX_KEY") ||
      txd.filter_column ||
      null
    );
  }

  function createEmptyTxRow(txd, keyCol, keyVal) {
    const row = txd.physical_fields.map(() => "");
    if (keyCol && keyVal) {
      const idx = txd.physical_fields.findIndex((f) => f.toUpperCase() === keyCol.toUpperCase());
      if (idx >= 0) row[idx] = keyVal;
    }
    return row;
  }

  function itemNoColumnIndex(txd) {
    return (txd.physical_fields || []).findIndex(
      (f) => String(f || "").trim().toUpperCase() === "ITEM_NO"
    );
  }

  function renumberTxItemNo(txd) {
    if (!txd) return;
    const idx = itemNoColumnIndex(txd);
    if (idx < 0) return;
    (txd.physical_rows || []).forEach((row, i) => {
      if (!Array.isArray(row)) return;
      while (row.length <= idx) row.push("");
      row[idx] = String(i + 1);
    });
  }

  function moveTxRow(txd, src, destBefore) {
    const rows = txd.physical_rows || [];
    const n = rows.length;
    if (n <= 1 || src < 0 || src >= n) return src;
    let dest = Number(destBefore);
    if (!Number.isFinite(dest)) dest = n;
    if (dest < 0) dest = 0;
    if (dest > n) dest = n;
    if (dest === src || dest === src + 1) return src;
    const row = rows.splice(src, 1)[0];
    if (dest > src) dest -= 1;
    dest = Math.max(0, Math.min(dest, rows.length));
    rows.splice(dest, 0, row);
    return dest;
  }

  function relocateTxRow(txd, src, newIndex) {
    const rows = txd.physical_rows || [];
    const n = rows.length;
    if (n <= 1 || src < 0 || src >= n) return src;
    const target = Math.max(0, Math.min(Number(newIndex) || 0, n - 1));
    if (target === src) return src;
    const destBefore = target < src ? target : target + 1;
    return moveTxRow(txd, src, destBefore);
  }

  function applyTxItemNoMove(page, detail, tx, src, itemNoText) {
    const txd = detail.txData[tx];
    if (!txd) return false;
    const raw = String(itemNoText || "").trim();
    if (!raw) return false;
    const target1 = parseInt(raw, 10);
    if (!Number.isFinite(target1)) return false;
    collectTxPhysicalRowsFromPage(page, detail);
    const newIdx = relocateTxRow(txd, src, target1 - 1);
    renumberTxItemNo(txd);
    txd.selectedRow = newIdx;
    txd.selectedRows = new Set([newIdx]);
    syncTxDisplayRows(txd);
    return true;
  }

  function bindTxGridRowReorder(page, detail, refreshUi) {
    const clearDragOver = (tx) => {
      $$(`.tx-table[data-tx="${CSS.escape(tx)}"] tbody tr[data-tx-row]`, page).forEach((r) =>
        r.classList.remove("tx-row-drag-over", "tx-row-dragging")
      );
    };

    $$(".tx-table tbody tr[data-tx-row] .tx-row-gutter", page).forEach((gutter) => {
      const tr = gutter.closest("tr[data-tx-row]");
      if (!tr) return;
      const tx = tr.dataset.tx;
      const ri = parseInt(tr.dataset.txRow, 10);
      const txd = detail.txData[tx];
      if (!txd) return;

      gutter.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        const state = {
          tx,
          src: ri,
          startY: e.clientY,
          dragging: false,
          dest: ri,
        };
        tr.classList.add("tx-row-dragging");
        selectTxRow(page, detail, tx, ri, { focus: false });

        const onMove = (ev) => {
          if (!state.dragging && Math.abs(ev.clientY - state.startY) >= 3) {
            state.dragging = true;
          }
          if (!state.dragging) return;
          const el = document.elementFromPoint(ev.clientX, ev.clientY);
          const targetTr =
            el && el.closest
              ? el.closest(`.tx-table[data-tx="${CSS.escape(tx)}"] tr[data-tx-row]`)
              : null;
          clearDragOver(tx);
          tr.classList.add("tx-row-dragging");
          if (targetTr) {
            const dest = parseInt(targetTr.dataset.txRow, 10);
            if (Number.isFinite(dest)) {
              state.dest = dest;
              targetTr.classList.add("tx-row-drag-over");
            }
          }
        };

        const onUp = () => {
          document.removeEventListener("mousemove", onMove, true);
          document.removeEventListener("mouseup", onUp, true);
          clearDragOver(tx);
          if (state.dragging && Number.isFinite(state.dest) && state.dest !== state.src) {
            collectTxPhysicalRowsFromPage(page, detail);
            const live = detail.txData[tx];
            if (!live) return;
            const newIdx = relocateTxRow(live, state.src, state.dest);
            renumberTxItemNo(live);
            live.selectedRow = newIdx;
            live.selectedRows = new Set([newIdx]);
            syncTxDisplayRows(live);
            refreshUi();
          } else {
            selectTxRow(page, detail, tx, state.src, { focus: false });
          }
        };

        document.addEventListener("mousemove", onMove, true);
        document.addEventListener("mouseup", onUp, true);
      });
    });

    $$(".tx-table tbody tr[data-tx-row]", page).forEach((tr) => {
      const tx = tr.dataset.tx;
      const ri = parseInt(tr.dataset.txRow, 10);
      const txd = detail.txData[tx];
      if (!txd) return;
      tr.querySelectorAll(".tx-cell").forEach((inp) => {
        const physIdx = parseInt(inp.dataset.physIdx, 10);
        const fieldName =
          Number.isFinite(physIdx) && physIdx >= 0
            ? String(txd.physical_fields[physIdx] || "")
            : "";
        if (fieldName.toUpperCase() === "ITEM_NO") {
          inp.addEventListener("change", () => {
            if (applyTxItemNoMove(page, detail, tx, ri, inp.value)) {
              refreshUi();
            }
          });
        }
      });
    });
  }

  function collectTxPhysicalRowsFromPage(page, detail) {
    const result = {};
    for (const tx of detail.txFiles) {
      const txd = detail.txData[tx];
      if (!txd) continue;
      const rows = [];
      $$(`.tx-table[data-tx="${CSS.escape(tx)}"] tbody tr[data-tx-row]`, page).forEach((tr) => {
        const ri = parseInt(tr.dataset.txRow, 10);
        const prow = txd.physical_fields.map((_, i) => {
          const inp = tr.querySelector(`.tx-cell[data-phys-idx="${i}"]`);
          if (inp) return inp.value;
          const existing = txd.physical_rows[ri];
          return existing && existing[i] !== undefined ? existing[i] : "";
        });
        rows.push(prow);
      });
      txd.physical_rows = rows;
      syncTxDisplayRows(txd);
      result[tx] = rows;
    }
    return result;
  }

  function updateTxSelectionUi(page, tx, txd) {
    const total = (txd.physical_rows || []).length;
    const row = txd.selectedRow;
    const noSel = row == null || row < 0 || row >= total;
    const cur = !noSel ? row + 1 : null;
    ensureTxGridSelection(txd);
    ensureTxGridCurrentCol(txd);
    $$(`.tx-table[data-tx="${CSS.escape(tx)}"] tbody tr[data-tx-row]`, page).forEach((tr) => {
      const ri = parseInt(tr.dataset.txRow, 10);
      tr.classList.toggle("selected", txd.selectedRows.has(ri));
      tr.classList.toggle("current-row", txd.selectedRow === ri);
      tr.querySelectorAll("td:not(.tx-row-gutter)").forEach((td) => {
        const ci = parseInt(td.dataset.colIdx, 10);
        td.classList.toggle(
          "current-cell",
          txd.selectedRow === ri && Number.isFinite(ci) && txd.currentCol === ci
        );
      });
    });
    const navEl = page.querySelector(`.tx-record-nav[data-tx="${CSS.escape(tx)}"]`);
    if (navEl) navEl.textContent = formatRecordNavLabel(total, cur);
    const hasRows = total > 0;
    ["first", "prev", "next", "last"].forEach((nav) => {
      const btn = page.querySelector(`.tx-nav[data-tx="${CSS.escape(tx)}"][data-nav="${nav}"]`);
      if (!btn) return;
      if (nav === "first") btn.disabled = !hasRows || (!noSel && row <= 0);
      else if (nav === "prev") btn.disabled = !hasRows || noSel || row <= 0;
      else if (nav === "next") btn.disabled = !hasRows || noSel || row >= total - 1;
      else if (nav === "last") btn.disabled = !hasRows || (!noSel && row >= total - 1);
    });
  }

  function scrollTxRowIntoView(page, tx, txd) {
    if (txd.selectedRow == null) return;
    const wrap = page.querySelector(`.tx-table[data-tx="${CSS.escape(tx)}"]`)?.closest(".tx-table-wrap");
    const tr = page.querySelector(`.tx-table[data-tx="${CSS.escape(tx)}"] tr[data-tx-row="${txd.selectedRow}"]`);
    if (!wrap || !tr) return;
    scrollRowInContainer(wrap, tr);
  }

  function selectTxRow(page, detail, tx, row, opts = {}) {
    const txd = detail.txData[tx];
    if (!txd) return false;
    collectTxPhysicalRowsFromPage(page, detail);
    ensureTxGridSelection(txd);
    const mode = opts.mode || "single";
    const total = txd.physical_rows.length;
    if (!total) {
      txd.selectedRow = null;
      txd.selectedRows.clear();
    } else if (row == null || row < 0 || row >= total) {
      return false;
    } else {
      txd.selectedRow = row;
      if (opts.col != null) txd.currentCol = clampTxGridCol(txd, opts.col);
      else ensureTxGridCurrentCol(txd);
      if (mode === "single") {
        txd.selectedRows.clear();
        txd.selectedRows.add(row);
        txd.selectionAnchor = row;
      } else if (mode === "toggle") {
        if (txd.selectedRows.has(row)) txd.selectedRows.delete(row);
        else txd.selectedRows.add(row);
        if (!txd.selectedRows.size) txd.selectedRows.add(row);
        txd.selectionAnchor = row;
      } else if (mode === "range") {
        const anchor = opts.anchor ?? txd.selectionAnchor ?? txd.selectedRow ?? 0;
        const lo = Math.min(anchor, row);
        const hi = Math.max(anchor, row);
        txd.selectedRows.clear();
        for (let i = lo; i <= hi; i++) txd.selectedRows.add(i);
        txd.selectionAnchor = anchor;
      }
    }
    updateTxSelectionUi(page, tx, txd);
    if (opts.scroll !== false) scrollTxRowIntoView(page, tx, txd);
    if (opts.focus !== false) {
      const wrap = page.querySelector(`.tx-table[data-tx="${CSS.escape(tx)}"]`)?.closest(".tx-table-wrap");
      if (wrap) wrap.focus({ preventScroll: true });
    }
    return true;
  }

  function navigateTxGrid(page, detail, tx, nav) {
    const txd = detail.txData[tx];
    if (!txd || !txd.physical_rows.length) return;
    collectTxPhysicalRowsFromPage(page, detail);
    const n = txd.physical_rows.length;
    const row = txd.selectedRow;
    const noSel = row == null || row < 0 || row >= n;
    if (nav === "first") selectTxRow(page, detail, tx, 0);
    else if (nav === "last") selectTxRow(page, detail, tx, n - 1);
    else if (nav === "prev" && !noSel && row > 0) selectTxRow(page, detail, tx, row - 1);
    else if (nav === "next" && !noSel && row < n - 1) selectTxRow(page, detail, tx, row + 1);
  }

  function focusTxCell(page, detail, tx, row, col) {
    const tr = page.querySelector(
      `.tx-table[data-tx="${CSS.escape(tx)}"] tr[data-tx-row="${row}"]`
    );
    if (!tr) return false;
    const cells = [...tr.querySelectorAll(".tx-cell")];
    const el = cells[col];
    if (!el) return false;
    collectTxPhysicalRowsFromPage(page, detail);
    selectTxRow(page, detail, tx, row, { col, scroll: false, focus: false });
    el.focus();
    el.select?.();
    return true;
  }

  function bindTxCellInputs(page, detail) {
    $$(".tx-cell", page).forEach((inp) => {
      inp.addEventListener("mousedown", (e) => e.stopPropagation());
      inp.addEventListener("click", (e) => e.stopPropagation());
      inp.addEventListener("dblclick", (e) => e.stopPropagation());
      inp.addEventListener("focus", (e) => {
        e.stopPropagation();
        if (inp.dataset.raw != null) {
          inp.value = inp.dataset.raw;
        }
        const tr = inp.closest("tr[data-tx-row]");
        if (!tr) return;
        const tx = tr.dataset.tx;
        const ri = parseInt(tr.dataset.txRow, 10);
        const col = parseInt(inp.dataset.colIdx, 10);
        const cells = [...tr.querySelectorAll(".tx-cell")];
        const ci = Number.isFinite(col) ? col : cells.indexOf(inp);
        selectTxRow(page, detail, tx, ri, { col: ci >= 0 ? ci : 0, scroll: false, focus: false });
      });
      inp.addEventListener("keydown", (e) => {
        if (e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return;
        const tr = inp.closest("tr[data-tx-row]");
        if (!tr) return;
        const tx = tr.dataset.tx;
        const txd = detail.txData[tx];
        if (!txd) return;
        const row = parseInt(tr.dataset.txRow, 10);
        const cells = [...tr.querySelectorAll(".tx-cell")];
        const col = cells.indexOf(inp);
        if (col < 0) return;
        const ncols = cells.length;
        const nrows = (txd.physical_rows || []).length;

        if (e.key === "Enter") {
          e.preventDefault();
          let nr = row;
          let nc = col + 1;
          if (nc >= ncols) {
            nc = 0;
            nr += 1;
          }
          if (nr >= nrows) {
            collectTxPhysicalRowsFromPage(page, detail);
            inp.blur();
            return;
          }
          focusTxCell(page, detail, tx, nr, nc);
          return;
        }

        const moves = {
          ArrowUp: [-1, 0],
          ArrowDown: [1, 0],
          ArrowLeft: [0, -1],
          ArrowRight: [0, 1],
        };
        const delta = moves[e.key];
        if (!delta) return;
        // 左右：游標未到邊界時保留欄內移動
        if (e.key === "ArrowLeft" && !formCaretAtStart(inp)) return;
        if (e.key === "ArrowRight" && !formCaretAtEnd(inp)) return;
        e.preventDefault();
        const nr = row + delta[0];
        const nc = col + delta[1];
        if (nr < 0 || nr >= nrows || nc < 0 || nc >= ncols) {
          return;
        }
        focusTxCell(page, detail, tx, nr, nc);
      });
    });
  }

  function renderTxPanel(detail, tx, index, opts = {}) {
    const embedded = opts.embedded === true;
    const txd = detail.txData[tx] || normalizeTxData({ tx_table: tx, fields: [], physical_fields: [], physical_rows: [] });
    initTxColumnWidths(txd);
    const cols = txd.columns || [];
    const thead =
      `<th class="tx-row-gutter" aria-hidden="true"></th>` +
      (txd.fields || [])
        .map((f, j) => {
          const ws = txColWidthStyle(txd, f);
          const sortInd = gridSortIndicatorHtml(txd.sortStack || [], j);
          return `<th class="grid-sortable" data-col="${escapeHtml(f)}" data-col-idx="${j}"${ws}><span class="th-text">${escapeHtml((cols[j] && cols[j].title) || f)}${sortInd}</span><span class="col-resizer" title="拖曳調整欄寬"></span></th>`;
        })
        .join("");

    const tbodyRows = (txd.physical_rows || []).length
      ? txd.physical_rows
          .map((prow, ri) => {
            const isCurRow = txd.selectedRow === ri;
            const curCol = txd.currentCol == null ? 0 : txd.currentCol;
            const cells = (txd.fields || []).map((f, j) => {
              const pi = txd.physical_fields.indexOf(f);
              const rawVal = pi >= 0 && prow[pi] !== undefined ? prow[pi] : "";
              const displayVal =
                txd.rows && txd.rows[ri] && txd.rows[ri][j] !== undefined
                  ? txd.rows[ri][j]
                  : rawVal;
              const meta = cols.find((c) => c.name === f) || cols[j] || {};
              const alignCls = gridCellAlignClass(meta) ? " num-field" : "";
              const ws = txColWidthStyle(txd, f);
              const curCell = isCurRow && curCol === j ? " current-cell" : "";
              return `<td class="${curCell.trim()}" data-col-idx="${j}"${ws}><input class="tx-cell${alignCls}" type="text" data-phys-idx="${pi}" data-col-idx="${j}" data-raw="${escapeHtml(String(rawVal))}" value="${escapeHtml(String(displayVal))}"></td>`;
            });
            const sel =
              txd.selectedRows instanceof Set
                ? txd.selectedRows.has(ri)
                : txd.selectedRow === ri;
            const cls = [sel ? "selected" : "", isCurRow ? "current-row" : ""].filter(Boolean).join(" ");
            return `<tr data-tx-row="${ri}" data-tx="${escapeHtml(tx)}" class="${cls}"><td class="tx-row-gutter" aria-hidden="true" title="拖曳移動列"><span class="tx-row-gutter-handle">⋮⋮</span></td>${cells.join("")}</tr>`;
          })
          .join("")
      : "";
    // 對齊桌面：固定 6 列可視高度；不足時下方留白（不強制補空白資料列）
    let tbody = tbodyRows;
    if (!tbody) {
      tbody = `<tr><td colspan="99" class="no-data">${t("noData")}</td></tr>`;
    }

    const cur =
      txd.selectedRow != null && txd.selectedRow >= 0 && txd.selectedRow < (txd.physical_rows || []).length
        ? txd.selectedRow + 1
        : null;
    const total = (txd.physical_rows || []).length;
    const navLabel = formatRecordNavLabel(total, cur);
    const tabLabel = detail.txFiles.length > 1 ? `${t("formDetail")} - ${index + 1}` : t("formDetail");
    const hasFields = (txd.fields || []).length > 0;

    const inner = `<div class="tx-toolbar">
        <div class="tx-nav-group">
          ${iconBtnOnly(t("navFirst"), "nav-first", "btn nav-btn tx-nav", `data-tx="${escapeHtml(tx)}" data-nav="first"`)}
          ${iconBtnOnly(t("navPrev"), "nav-prev", "btn nav-btn tx-nav", `data-tx="${escapeHtml(tx)}" data-nav="prev"`)}
          ${iconBtnOnly(t("navNext"), "nav-next", "btn nav-btn tx-nav", `data-tx="${escapeHtml(tx)}" data-nav="next"`)}
          ${iconBtnOnly(t("navLast"), "nav-last", "btn nav-btn tx-nav", `data-tx="${escapeHtml(tx)}" data-nav="last"`)}
          <span class="record-nav tx-record-nav" data-tx="${escapeHtml(tx)}">${navLabel}</span>
        </div>
        <div class="tx-crud-group">
          ${iconBtn(t("add"), "add", "btn action-btn tx-act", `data-tx="${escapeHtml(tx)}" data-tx-act="add"`)}
          ${iconBtn(t("edit"), "edit", "btn action-btn tx-act", `data-tx="${escapeHtml(tx)}" data-tx-act="edit"`)}
          ${iconBtn(t("del"), "delete", "btn action-btn tx-act", `data-tx="${escapeHtml(tx)}" data-tx-act="delete"`)}
          ${iconBtn(t("copy"), "copy", "btn action-btn tx-act", `data-tx="${escapeHtml(tx)}" data-tx-act="copy"`)}
          ${iconBtn(t("txMoveUp"), "nav-prev", "btn action-btn tx-act", `data-tx="${escapeHtml(tx)}" data-tx-act="move-up"`)}
          ${iconBtn(t("txMoveDown"), "nav-next", "btn action-btn tx-act", `data-tx="${escapeHtml(tx)}" data-tx-act="move-down"`)}
        </div>
        <div class="tx-search-group">
          <label class="search-label">${t("searchLabel")}</label>
          <input type="text" class="tx-search-input" data-tx="${escapeHtml(tx)}" value="${escapeHtml(txd.keyword)}">
          ${iconBtn(t("search"), "search", "btn action-btn tx-act", `data-tx="${escapeHtml(tx)}" data-tx-act="search"`)}
        </div>
      </div>
      <div class="work-table-wrap grid-focus-target tx-table-wrap work-grid-6-rows" tabindex="0">
        <table class="work-table tx-table" data-tx="${escapeHtml(tx)}">
          <thead><tr>${hasFields ? thead : `<th>${t("noData")}</th>`}</tr></thead>
          <tbody>${tbody}</tbody>
        </table>
      </div>`;

    if (embedded) return inner;

    return `<div class="tx-tab-panel" data-tx-panel="${escapeHtml(tx)}">
      <div class="tx-tab-title">${escapeHtml(tabLabel)} (${escapeHtml(tx)})</div>
      ${inner}
    </div>`;
  }

  function buildFormFieldMeta(detail) {
    const byName = new Map();
    (detail.formColumns || []).forEach((m) => {
      if (!m || !m.name) return;
      // 對齊桌面 DataDictionary：欄名大小寫不敏感
      byName.set(String(m.name).toUpperCase(), m);
      byName.set(String(m.name), m);
    });
    return (detail.formFields || []).map((name) => {
      const hit =
        byName.get(String(name || "").toUpperCase()) ||
        byName.get(name) ||
        null;
      if (hit) {
        return {
          ...hit,
          name: hit.name || name,
        };
      }
      return { name, title: name, edit_tab: "", edit_type: "", lookup_db: "", lookup_key: "", lookup_ret: "" };
    });
  }

  function formLayoutSpec(totalFields, mode) {
    const n = Math.max(0, Number(totalFields) || 0);
    const planned = String(mode || getFormLayoutMode()) === FORM_LAYOUT_PLANNED;
    if (planned) {
      if (n <= 15) return { cols: 3, fieldsPerPage: 15, rows: 5, mode: FORM_LAYOUT_PLANNED };
      return { cols: 5, fieldsPerPage: 25, rows: 5, mode: FORM_LAYOUT_PLANNED };
    }
    if (n <= 20) return { cols: 2, fieldsPerPage: 20, rows: 10, mode: FORM_LAYOUT_DEFAULT };
    return { cols: 3, fieldsPerPage: 30, rows: 10, mode: FORM_LAYOUT_DEFAULT };
  }

  function editTabKeyIsIndex(tabKey) {
    const key = String(tabKey || "").trim();
    if (!key) return true;
    if (/^\d+$/.test(key)) return true;
    return /^\d+\s*-\s*\d+$/.test(key);
  }

  function formDataTabTitle(base, idx1, totalTabs, tabKey) {
    const key = String(tabKey || "").trim();
    if (key && !editTabKeyIsIndex(key)) return key;
    const b = (base || "").trim();
    if (currentLang === "ENG") {
      return totalTabs <= 1 ? `${b} Data`.trim() : `${b} Data - ${idx1}`.trim();
    }
    return totalTabs <= 1
      ? `${b} ${t("formData")}`.trim()
      : `${b} ${t("formData")} - ${idx1}`.trim();
  }

  function detailTabTitle(base, idx1, totalTabs) {
    const b = (base || "").trim();
    if (currentLang === "ENG") {
      return totalTabs <= 1 ? `${b} Detail`.trim() : `${b} Detail - ${idx1}`.trim();
    }
    return totalTabs <= 1
      ? `${b} ${t("formDetail")}`.trim()
      : `${b} ${t("formDetail")} - ${idx1}`.trim();
  }

  function splitFormFieldPages(detail) {
    const metaList = buildFormFieldMeta(detail);
    const layout = formLayoutSpec(metaList.length, getFormLayoutMode());
    const fieldsPerPage = layout.fieldsPerPage;
    const groups = new Map();
    const ungrouped = [];
    const tabKeys = [];

    metaList.forEach((meta) => {
      const tabKey = (meta.edit_tab || "").trim();
      if (tabKey) {
        if (!groups.has(tabKey)) groups.set(tabKey, []);
        groups.get(tabKey).push(meta);
      } else {
        ungrouped.push(meta);
      }
    });

    let chunks = [];
    if (groups.size > 0) {
      groups.forEach((fields, key) => {
        if (!fields.length) return;
        // EDIT_TAB 指定群組若超過一頁容量，再切分（標題：KEY / KEY - 2…）
        for (let i = 0; i < fields.length; i += fieldsPerPage) {
          const chunk = fields.slice(i, i + fieldsPerPage);
          const pageIdx = Math.floor(i / fieldsPerPage);
          chunks.push(chunk);
          tabKeys.push(pageIdx === 0 ? key : `${key} - ${pageIdx + 1}`);
        }
      });
      for (let i = 0; i < ungrouped.length; i += fieldsPerPage) {
        chunks.push(ungrouped.slice(i, i + fieldsPerPage));
        tabKeys.push("");
      }
    } else {
      for (let i = 0; i < metaList.length; i += fieldsPerPage) {
        chunks.push(metaList.slice(i, i + fieldsPerPage));
        tabKeys.push("");
      }
    }
    if (!chunks.length) {
      chunks.push([]);
      tabKeys.push("");
    }

    const base = detail.title || "";
    const total = chunks.length;
    return {
      cols: layout.cols,
      rows: layout.rows,
      mode: layout.mode,
      pages: chunks.map((fields, i) => ({
        id: String(i),
        title: formDataTabTitle(base, i + 1, total, tabKeys[i]),
        fields,
      })),
    };
  }

  function renderFormTabWidget(detail) {
    const split = splitFormFieldPages(detail);
    const pages = split.pages;
    const planned = split.mode === FORM_LAYOUT_PLANNED;
    const colsClass =
      split.cols === 5
        ? "form-grid-cols-5"
        : split.cols === 4
          ? "form-grid-cols-4"
          : split.cols === 3
            ? "form-grid-cols-3"
            : "form-grid-cols-2";
    const layoutClass = planned ? "form-layout-planned" : "form-layout-default";
    // 對齊桌面：全表單欄位一次量測統一標題寬（跨 EDIT_TAB 分頁不變）；規劃介面不需左標寬
    const allFields = [];
    pages.forEach((p) => {
      (p.fields || []).forEach((f) => allFields.push(f));
    });
    const dims = formLayoutDims(split.mode);
    const tabButtons = pages
      .map(
        (p, i) =>
          `<button type="button" class="inner-tab-btn${i === 0 ? " active" : ""}" data-form-tab="${p.id}" style="color:${tabTitleColor(i)}">${escapeHtml(p.title)}</button>`
      )
      .join("");
    const tabPanels = pages
      .map((p, i) => {
        const slot = renderFormGridSlots(p.fields, detail.formValues || {}, split.cols, split.rows, {
          labelWidthPx: dims.labelW,
          layoutMode: split.mode,
          detailMode: detail.mode,
          detail,
        });
        const styleParts = [
          `--form-editor-w:${dims.editorW}px`,
          `--form-editor-h:${dims.editorH}px`,
          `--form-label-w:${dims.labelW}px`,
        ];
        return `<div class="form-tab-panel${i === 0 ? "" : " hidden"}" data-form-panel="${p.id}">
          <div class="form-grid ${colsClass} ${layoutClass}" style="${styleParts.join(";")}">${slot.html}</div>
        </div>`;
      })
      .join("");

    return `<div class="form-tab-widget">
      <div class="inner-tab-bar form-inner-tab-bar">${tabButtons}</div>
      <div class="form-tab-panels">${tabPanels}</div>
    </div>`;
  }

  function renderTxTabWidget(detail) {
    // 無 TX_FILE 時仍佔 40% 留白，表單區佔 60%
    if (!detail.txFiles.length) {
      return `<div class="tx-section tx-section-empty" aria-hidden="true"></div>`;
    }
    const base = detail.title || "";
    const total = detail.txFiles.length;
    const tabButtons = detail.txFiles
      .map(
        (tx, i) =>
          `<button type="button" class="inner-tab-btn${i === 0 ? " active" : ""}" data-tx-tab="${escapeHtml(tx)}" style="color:${tabTitleColor(i)}">${escapeHtml(detailTabTitle(base, i + 1, total))}</button>`
      )
      .join("");
    const tabPanels = detail.txFiles
      .map((tx, i) => {
        const body = renderTxPanel(detail, tx, i, { embedded: true });
        return `<div class="tx-tab-panel${i === 0 ? "" : " hidden"}" data-tx-panel="${escapeHtml(tx)}">${body}</div>`;
      })
      .join("");

    return `<div class="tx-section"><div class="tx-tab-widget">
      <div class="inner-tab-bar tx-inner-tab-bar">${tabButtons}</div>
      <div class="tx-tab-panels">${tabPanels}</div>
    </div></div>`;
  }

  function activateFormTabForElement(page, el) {
    if (!el) return;
    const panel = el.closest(".form-tab-panel[data-form-panel]");
    if (!panel) return;
    if (!panel.classList.contains("hidden")) return;
    const id = panel.dataset.formPanel;
    const btn = page.querySelector(`.form-inner-tab-bar .inner-tab-btn[data-form-tab="${CSS.escape(id)}"]`);
    if (btn) btn.click();
  }

  function activateTxTabForElement(page, el) {
    if (!el) return;
    const panel = el.closest(".tx-tab-panel[data-tx-panel]");
    if (!panel || !panel.classList.contains("hidden")) return;
    const tx = panel.dataset.txPanel;
    const btn = page.querySelector(`.tx-inner-tab-bar .inner-tab-btn[data-tx-tab="${CSS.escape(tx)}"]`);
    if (btn) btn.click();
  }

  function bindFormTabEvents(page) {
    $$(".form-inner-tab-bar .inner-tab-btn[data-form-tab]", page).forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.dataset.formTab;
        $$(".form-inner-tab-bar .inner-tab-btn[data-form-tab]", page).forEach((b) => {
          b.classList.toggle("active", b.dataset.formTab === id);
        });
        $$(".form-tab-panels .form-tab-panel[data-form-panel]", page).forEach((p) => {
          p.classList.toggle("hidden", p.dataset.formPanel !== id);
        });
        syncFormFieldTabIndex(page);
      });
    });
  }

  function bindTxTabEvents(page, detail) {
    $$(".tx-inner-tab-bar .inner-tab-btn[data-tx-tab]", page).forEach((btn) => {
      btn.addEventListener("click", () => {
        const tx = btn.dataset.txTab;
        $$(".tx-inner-tab-bar .inner-tab-btn[data-tx-tab]", page).forEach((b) => {
          b.classList.toggle("active", b.dataset.txTab === tx);
        });
        $$(".tx-tab-panels .tx-tab-panel[data-tx-panel]", page).forEach((p) => {
          p.classList.toggle("hidden", p.dataset.txPanel !== tx);
        });
        syncFormFieldTabIndex(page);
        const txd = detail.txData[tx];
        if (txd) updateTxSelectionUi(page, tx, txd);
      });
    });
  }

  function renderDetailPage(detail) {
    const formHtml = renderFormTabWidget(detail);
    const txHtml = renderTxTabWidget(detail);
    const workTab = getWorkTabForDetail(detail);
    const wa = workTab
      ? tabWorkActions(workTab)
      : mergeWorkActions(findMenuWorkActions(detail.doProc), detail.workActions || {});
    const attachBtn = isWorkFlagTrue(wa.need_attach)
      ? iconBtn(t("attachment"), "attachment", "btn action-btn", 'data-act="attachment"')
      : "";
    const planned = getFormLayoutMode() === FORM_LAYOUT_PLANNED;
    const layoutBtn = iconBtn(
      planned ? t("formLayoutDefault") : t("formLayoutPlanned"),
      "convert_db",
      "btn secondary form-layout-toggle",
      'data-act="toggle-form-layout"',
      planned ? t("formLayoutTipDefault") : t("formLayoutTipPlanned")
    );

    // 對齊桌面：上半表單 60%／下半 TX 40%
    return `
      <div class="detail-page" data-tab="${detail.id}">
        <div class="detail-split">
          <div class="detail-form-area">
            <div class="detail-form-scroll">${formHtml}</div>
            <div class="detail-actions">
              ${layoutBtn}
              ${attachBtn}
              ${iconBtn(t("save"), "save", "btn primary", 'data-act="save"')}
              ${iconBtn(t("cancel"), "cancel", "btn secondary", 'data-act="cancel"')}
            </div>
          </div>
          ${txHtml}
        </div>
        <p class="error detail-error hidden"></p>
      </div>`;
  }

  function bindWorkPageEvents(tab) {
    const page = $(`.work-page[data-tab="${tab.id}"]`);
    if (!page) return;

    bindWorkGridColumnResize(page, tab);
    bindWorkGridSortHeaders(page, tab);

    const searchInput = $(".search-input", page);
    if (searchInput) {
      searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") doSearch(tab, page);
      });
    }

    $$(".action-btn", page).forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        const act = btn.dataset.act;
        if (act === "search") doSearch(tab, page);
        else if (act === "filter") doFilter(tab, page);
        else if (act === "add") openDetailTab(tab, "add", null);
        else if (act === "edit") {
          if (tab.selectedRow == null) {
            showAlert(t("selectRow"));
            return;
          }
          openDetailTab(tab, "edit", tab.selectedRow);
        } else if (act === "copy") {
          if (tab.selectedRow == null) {
            showAlert(t("selectRow"));
            return;
          }
          openDetailTab(tab, "copy", tab.selectedRow);
        }         else if (act === "delete") doDelete(tab);
        else if (act === "refresh") doRefreshWorkData(tab);
        else if (act === "print") doPrint(tab);
        else if (act === "attachment") doAttachment(tab);
        else if (act === "import") openDataImportModal(tab);
        else if (act === "other") doOther(tab);
        else if (act === "exit") closeTab(tab.id);
      });
    });

    $$("[data-nav]", page).forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        navigateWorkGrid(tab, page, btn.dataset.nav);
      });
    });

    const gridWrap = $(".work-table-wrap:not(.tx-table-wrap)", page);
    if (gridWrap) {
      gridWrap.addEventListener("click", () => gridWrap.focus({ preventScroll: true }));
    }
    bindWorkGridContextMenu(page, tab);

    page.addEventListener("click", (e) => {
      if (e.target.closest(".work-toolbar, .search-input, .action-btn")) return;
      if (e.target.closest(".work-table-wrap")) return;
      if (e.target.closest(".nav-row, .work-page")) focusWorkGridWrap(page);
    });

    $$("tbody tr[data-row]", page).forEach((tr) => {
      tr.addEventListener("click", (e) => {
        const ri = parseInt(tr.dataset.row, 10);
        const td = e.target.closest("td");
        const col = td ? td.cellIndex : tab.currentCol ?? 0;
        if (e.shiftKey) {
          selectWorkGridRow(tab, page, ri, { mode: "range", col });
        } else if (e.ctrlKey || e.metaKey) {
          selectWorkGridRow(tab, page, ri, { mode: "toggle", col });
        } else {
          selectWorkGridRow(tab, page, ri, { col });
        }
        focusWorkGridWrap(page);
      });
      tr.addEventListener("dblclick", () => {
        const ri = parseInt(tr.dataset.row, 10);
        selectWorkGridRow(tab, page, ri, { scroll: false });
        openDetailTab(tab, "edit", ri);
      });
    });

    page.addEventListener("keydown", (e) => {
      if (isGridKeyboardBlockedTarget(e.target)) return;
      const gridActive = isWorkGridKeyboardActive(page, gridWrap);
      if (gridActive && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
        e.preventDefault();
        selectAllWorkGridRows(tab, page);
        return;
      }
      if (gridActive && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c") {
        e.preventDefault();
        copyWorkGridToClipboard(tab);
        return;
      }
      const n = tab.rows.length;
      const ncols = tab.fields.length;
      if (n && gridActive && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
        e.preventDefault();
        const row = tab.selectedRow;
        const noSel = row == null || row < 0 || row >= n;
        if (e.key === "ArrowDown") {
          if (noSel) selectWorkGridRow(tab, page, 0);
          else if (row < n - 1) selectWorkGridRow(tab, page, row + 1);
        } else if (!noSel && row > 0) {
          selectWorkGridRow(tab, page, row - 1);
        }
        return;
      }
      if (n && ncols && gridActive && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
        e.preventDefault();
        const row = tab.selectedRow;
        if (row == null || row < 0 || row >= n) return;
        let col = tab.currentCol ?? 0;
        if (e.key === "ArrowLeft" && col > 0) col -= 1;
        else if (e.key === "ArrowRight" && col < ncols - 1) col += 1;
        else return;
        tab.currentCol = col;
        refreshWorkGridSelectionUi(page, tab);
        scrollWorkGridCellIntoView(tab, page);
        return;
      }
      // 對齊桌面 QTableView：Home/End 移至列首／列末欄；PageUp/Down 依可視列數翻頁
      if (n && ncols && gridActive && e.key === "Home") {
        e.preventDefault();
        if (tab.selectedRow == null || tab.selectedRow < 0) selectWorkGridRow(tab, page, 0, { col: 0 });
        else {
          tab.currentCol = 0;
          refreshWorkGridSelectionUi(page, tab);
          scrollWorkGridCellIntoView(tab, page);
        }
        return;
      }
      if (n && ncols && gridActive && e.key === "End") {
        e.preventDefault();
        const lastCol = Math.max(0, ncols - 1);
        if (tab.selectedRow == null || tab.selectedRow < 0) selectWorkGridRow(tab, page, 0, { col: lastCol });
        else {
          tab.currentCol = lastCol;
          refreshWorkGridSelectionUi(page, tab);
          scrollWorkGridCellIntoView(tab, page);
        }
        return;
      }
      if (n && gridActive && e.key === "PageUp") {
        e.preventDefault();
        const row = tab.selectedRow == null ? 0 : tab.selectedRow;
        const next = Math.max(0, row - GRID_VISIBLE_ROWS);
        selectWorkGridRow(tab, page, next, { col: tab.currentCol ?? 0 });
        return;
      }
      if (n && gridActive && e.key === "PageDown") {
        e.preventDefault();
        const row = tab.selectedRow == null ? 0 : tab.selectedRow;
        const next = Math.min(n - 1, row + GRID_VISIBLE_ROWS);
        selectWorkGridRow(tab, page, next, { col: tab.currentCol ?? 0 });
        return;
      }
      if (gridActive && e.key === "Enter" && tab.selectedRow != null) {
        e.preventDefault();
        openDetailTab(tab, "edit", tab.selectedRow);
      }
    });
    page.setAttribute("tabindex", "-1");
  }

  async function doSearch(tab, page) {
    tab.keyword = $(".search-input", page).value.trim();
    tab.filtered = false;
    await loadWorkData(tab, { asFilter: false });
    renderTabs();
  }

  function resolveAttachmentPath(tab) {
    const wa = tabWorkActions(tab);
    let template = (wa.attach_path || "").trim() || "ATTACH";
    let keyVal = "";
    const row =
      tab.selectedRow != null && tab.physicalRows && tab.physicalRows[tab.selectedRow]
        ? tab.physicalRows[tab.selectedRow]
        : null;
    const keyCandidates = [tab.printKeyColumn, "TX_KEY", "ID"].filter(Boolean);
    const phys = tab.physicalFields || [];
    if (row) {
      for (const k of keyCandidates) {
        const idx = phys.findIndex((n) => String(n).toUpperCase() === String(k).toUpperCase());
        if (idx >= 0 && row[idx]) {
          keyVal = String(row[idx]).trim();
          if (keyVal) break;
        }
      }
    }
    return template
      .replace(/\{KEY\}/g, keyVal)
      .replace(/\{CO_KEY\}/g, currentUser?.company_key || "")
      .replace(/\{DO_PROC\}/g, tab.doProc || "")
      .replace(/\{TABLE\}/g, tab.tableName || "");
  }

  function closeAttachModal() {
    const el = $("#attach-modal-overlay");
    if (el) {
      if (el._attachCleanup) {
        try {
          el._attachCleanup();
        } catch (_) {}
      }
      el.querySelectorAll("iframe, img").forEach((node) => {
        const src = node.getAttribute("src") || "";
        if (src.startsWith("blob:")) {
          try {
            URL.revokeObjectURL(src);
          } catch (_) {}
        }
      });
      el.remove();
    }
    attachModalState = null;
  }

  async function showAttachmentPreview(file) {
    const preview = $("#attach-preview");
    if (!preview || !file) return;
    preview.querySelectorAll("iframe, img").forEach((node) => {
      const src = node.getAttribute("src") || "";
      if (src.startsWith("blob:")) {
        try {
          URL.revokeObjectURL(src);
        } catch (_) {}
      }
    });
    preview.innerHTML = `<p>...</p>`;
    try {
      const res = await fetch(
        `/api/attachments/file?path=${encodeURIComponent(file.path)}`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      if (!res.ok) throw new Error(t("attachSelectRow"));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      if (file.kind === "pdf") {
        preview.innerHTML = `<iframe src="${url}" title="${escapeHtml(file.name)}"></iframe>`;
      } else if (file.kind === "image") {
        preview.innerHTML = `<img src="${url}" alt="${escapeHtml(file.name)}">`;
      } else {
        preview.innerHTML = `<p>${escapeHtml(file.name)}</p>`;
      }
    } catch (e) {
      preview.innerHTML = `<p class="error">${escapeHtml(e.message)}</p>`;
    }
  }

  /** 預設對齊細節頁上半部（表單區）；否則對齊工作區上半。 */
  function getAttachWindowDefaultRect() {
    const detailForm =
      (activeTabId &&
        document.querySelector(`.detail-page[data-tab="${CSS.escape(activeTabId)}"] .detail-form-area`)) ||
      document.querySelector(".detail-page .detail-form-area");
    if (detailForm) {
      const r = detailForm.getBoundingClientRect();
      if (r.width >= 120 && r.height >= 100) {
        return {
          left: Math.round(r.left),
          top: Math.round(r.top),
          width: Math.round(r.width),
          height: Math.round(r.height),
        };
      }
    }
    const content = document.querySelector("#tabs-content") || document.querySelector(".workspace") || document.body;
    const r = content.getBoundingClientRect();
    const pad = 8;
    return {
      left: Math.round(r.left + pad),
      top: Math.round(r.top + pad),
      width: Math.max(360, Math.round(r.width - pad * 2)),
      height: Math.max(260, Math.round(r.height * 0.5 - pad)),
    };
  }

  function attachFloatHeaderHtml(data) {
    const folderLine = data.folder
      ? `<p class="attach-float-folder text-muted">${escapeHtml(data.folder)}</p>`
      : "";
    return `<div class="attach-float-header attach-drag-handle">
      <div class="attach-float-title-wrap">
        <h2>${escapeHtml(t("attachPreview"))} — ${escapeHtml(data.key_value || "")}</h2>
        ${folderLine}
      </div>
      ${iconBtn(t("attachClose"), "exit", "btn secondary btn-sm attach-float-close", 'data-act="attach-close"')}
    </div>`;
  }

  function bindAttachFloatInteract(win, host) {
    if (!win) return;
    const minW = 320;
    const minH = 220;
    let drag = null;

    const onMove = (e) => {
      if (!drag) return;
      e.preventDefault();
      if (drag.mode === "move") {
        const dx = e.clientX - drag.sx;
        const dy = e.clientY - drag.sy;
        win.style.left = `${Math.round(drag.left + dx)}px`;
        win.style.top = `${Math.round(drag.top + dy)}px`;
        return;
      }
      const dx = e.clientX - drag.sx;
      const dy = e.clientY - drag.sy;
      let left = drag.left;
      let top = drag.top;
      let width = drag.width;
      let height = drag.height;
      const dir = drag.mode;
      if (dir.includes("e")) width = Math.max(minW, drag.width + dx);
      if (dir.includes("s")) height = Math.max(minH, drag.height + dy);
      if (dir.includes("w")) {
        width = Math.max(minW, drag.width - dx);
        left = drag.left + (drag.width - width);
      }
      if (dir.includes("n")) {
        height = Math.max(minH, drag.height - dy);
        top = drag.top + (drag.height - height);
      }
      win.style.left = `${Math.round(left)}px`;
      win.style.top = `${Math.round(top)}px`;
      win.style.width = `${Math.round(width)}px`;
      win.style.height = `${Math.round(height)}px`;
    };

    const onUp = () => {
      if (!drag) return;
      drag = null;
      document.body.classList.remove("attach-float-dragging");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    const startDrag = (mode, e) => {
      if (e.button != null && e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      const rect = win.getBoundingClientRect();
      drag = {
        mode,
        sx: e.clientX,
        sy: e.clientY,
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
      };
      document.body.classList.add("attach-float-dragging");
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    };

    const header = win.querySelector(".attach-drag-handle");
    if (header) {
      header.addEventListener("pointerdown", (e) => {
        if (e.target.closest('[data-act="attach-close"], button, a')) return;
        startDrag("move", e);
      });
    }
    win.querySelectorAll("[data-resize]").forEach((h) => {
      h.addEventListener("pointerdown", (e) => startDrag(h.getAttribute("data-resize") || "se", e));
    });

    host._attachCleanup = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      document.body.classList.remove("attach-float-dragging");
    };
  }

  function mountAttachFloatWindow(data, bodyHtml, extraClass) {
    closeAttachModal();
    attachModalState = data;
    const rect = getAttachWindowDefaultRect();
    const host = document.createElement("div");
    host.id = "attach-modal-overlay";
    host.className = "attach-float-host";
    host.innerHTML = `<div class="attach-float-window ${extraClass || ""}" role="dialog" aria-modal="false"
        style="left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px">
      ${attachFloatHeaderHtml(data)}
      <div class="attach-float-body">${bodyHtml}</div>
      <span class="attach-resize-handle n" data-resize="n"></span>
      <span class="attach-resize-handle s" data-resize="s"></span>
      <span class="attach-resize-handle e" data-resize="e"></span>
      <span class="attach-resize-handle w" data-resize="w"></span>
      <span class="attach-resize-handle ne" data-resize="ne"></span>
      <span class="attach-resize-handle nw" data-resize="nw"></span>
      <span class="attach-resize-handle se" data-resize="se"></span>
      <span class="attach-resize-handle sw" data-resize="sw"></span>
    </div>`;
    document.body.appendChild(host);
    const win = host.querySelector(".attach-float-window");
    host.querySelector('[data-act="attach-close"]')?.addEventListener("click", closeAttachModal);
    bindAttachFloatInteract(win, host);
    return host;
  }

  /** 單一附件：可移動／調大小浮窗，預設對齊上半部。 */
  function openAttachmentViewer(data, file) {
    mountAttachFloatWindow(
      { ...data, files: [file] },
      `<div id="attach-preview" class="attach-preview"></div>`,
      "attach-float-single"
    );
    showAttachmentPreview(file);
  }

  /** 多個附件：清單 + 預覽，同樣可移動／調大小。 */
  function openAttachmentPickerModal(data) {
    const listItems = (data.files || [])
      .map(
        (f, i) =>
          `<li><button type="button" class="attach-file-btn btn-has-icon${i === 0 ? " active" : ""}" data-idx="${i}">${uiIcon("attachment", 14)}<span class="btn-label">${escapeHtml(f.name)}</span></button></li>`
      )
      .join("");
    const body = `<p class="attach-pick-hint">${escapeHtml(t("attachPickHint"))}</p>
      <ul class="attach-file-list">${listItems}</ul>
      <div id="attach-preview" class="attach-preview"></div>`;
    const host = mountAttachFloatWindow(data, body, "attach-float-pick");
    if (data.files && data.files.length) showAttachmentPreview(data.files[0]);
    host.querySelectorAll(".attach-file-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        host.querySelectorAll(".attach-file-btn").forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        const idx = parseInt(btn.dataset.idx, 10);
        if (data.files[idx]) showAttachmentPreview(data.files[idx]);
      });
    });
  }

  async function doAttachment(tab) {
    if (tab.selectedRow == null) {
      showCopyableMessage(t("attachment"), t("attachSelectRow"));
      return;
    }
    const oldRow = tab.physicalRows[tab.selectedRow];
    await openAttachmentsForRow(tab.doProc, oldRow);
  }

  async function doAttachmentForDetail(detail, page) {
    const workTab = getWorkTabForDetail(detail);
    const formValues = (page && collectFormValues(page)) || detail.formValues || {};
    let oldRow = [];
    if (workTab && Array.isArray(workTab.physicalFields) && workTab.physicalFields.length) {
      oldRow = workTab.physicalFields.map((f, fi) => {
        if (formValues[f] != null && String(formValues[f]).length) return String(formValues[f]);
        if (detail.oldRow && detail.oldRow[fi] != null) return String(detail.oldRow[fi]);
        return "";
      });
    } else if (Array.isArray(detail.oldRow) && detail.oldRow.length) {
      oldRow = detail.oldRow.slice();
    } else {
      showCopyableMessage(t("attachment"), t("attachSelectRow"));
      return;
    }
    await openAttachmentsForRow(detail.doProc, oldRow);
  }

  async function openAttachmentsForRow(doProc, oldRow) {
    try {
      const data = await api(`/work/${encodeURIComponent(doProc)}/attachments`, {
        method: "POST",
        body: JSON.stringify({ old_row: oldRow || [] }),
      });
      if (!data.files || !data.files.length) {
        const msg =
          data.not_found_message ||
          formatAttachNotFoundMessage(data.folder, data.key_value);
        showCopyableMessage(t("attachment"), msg);
        return;
      }
      if (data.files.length === 1) {
        openAttachmentViewer(data, data.files[0]);
      } else {
        openAttachmentPickerModal(data);
      }
    } catch (e) {
      showCopyableMessage(t("attachment"), e.message || t("attachSelectRow"));
    }
  }

  function closeArapModal() {
    const el = $("#arap-modal-overlay");
    if (el) {
      if (el._arapResize) window.removeEventListener("resize", el._arapResize);
      el.remove();
    }
    arapModalState = null;
  }

  function arapTitle(mode) {
    return mode === "AP" ? t("arapTitleAP") : t("arapTitleAR");
  }

  function arapPartyLabel(mode) {
    return mode === "AP" ? t("arapPartyAP") : t("arapPartyAR");
  }

  function arapPartyText(h) {
    return `${h.party_key || ""} - ${h.party_name || ""}`.replace(/^[\s-]+|[\s-]+$/g, "").trim();
  }

  function arapLineSearchBlob(ln) {
    return [
      ln.tx_key,
      ln.inv_no,
      ln.date,
      ln.currency,
      ln.net_amt,
      ln.paid_amt,
      ln.balance,
      ln.pay_amount,
      ln.discount,
    ]
      .map((x) => String(x || ""))
      .join(" ")
      .toLowerCase();
  }

  function arapLineMatches(ln, keyword) {
    const kw = String(keyword || "").trim().toLowerCase();
    if (!kw) return false;
    return arapLineSearchBlob(ln).includes(kw);
  }

  function arapFilterLines(allLines, keyword) {
    const kw = String(keyword || "").trim().toLowerCase();
    if (!kw) return allLines.slice();
    return allLines.filter((ln) => arapLineMatches(ln, kw));
  }

  function arapFindLineIndex(allLines, keyword) {
    const kw = String(keyword || "").trim().toLowerCase();
    if (!kw) return null;
    for (let i = 0; i < allLines.length; i++) {
      if (arapLineMatches(allLines[i], kw)) return i;
    }
    return null;
  }

  function arapHeaderCells() {
    if (currentLang === "CHN") {
      return [
        `<th class="arap-col-tx-key">發票編號</th>`,
        "<th>日期</th>",
        "<th>貨幣</th>",
        "<th>滙率</th>",
        "<th>發票金額</th>",
        "<th>已付金額</th>",
        "<th>發票餘額</th>",
        '<th class="arap-col-pay">付款金額</th>',
        '<th class="arap-col-disc">折扣金額</th>',
      ];
    }
    return [
      `<th class="arap-col-tx-key">Invoice No.</th>`,
      "<th>Date</th>",
      "<th>Curr.</th>",
      "<th>Rate</th>",
      "<th>Invoice Amt.</th>",
      "<th>Paid Amt.</th>",
      "<th>Balance</th>",
      '<th class="arap-col-pay">Payment</th>',
      '<th class="arap-col-disc">Discount</th>',
    ];
  }

  function arapFormatDate(val) {
    return formatAppDateDisplay(val || "");
  }

  function arapParseNum(s) {
    const t = String(s ?? "")
      .replace(/,/g, "")
      .trim();
    const n = parseFloat(t);
    return Number.isFinite(n) ? n : 0;
  }

  function arapFormatAmt2(n) {
    return arapParseNum(n).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function arapFormatRate4(n) {
    return arapParseNum(n).toLocaleString("en-US", {
      minimumFractionDigits: 4,
      maximumFractionDigits: 4,
    });
  }

  function queryFormatInt(n) {
    const raw = String(n ?? "").trim();
    if (!raw) return "";
    const cleaned = raw.replace(/,/g, "");
    if (!/^-?\d+(\.\d+)?$/.test(cleaned)) return raw;
    return Math.round(arapParseNum(raw)).toLocaleString("en-US", { maximumFractionDigits: 0 });
  }

  function computeArapTotalsFromState(state) {
    const lines = state.allLines || state.document?.lines || [];
    const header = state.document?.header || state.header || {};
    let bal = 0;
    let pay = 0;
    let disc = 0;
    for (const ln of lines) {
      bal += arapParseNum(ln.balance);
      pay += arapParseNum(ln.pay_amount);
      disc += arapParseNum(ln.discount);
    }
    const settle = arapParseNum(header.settle_amount);
    const exch = arapParseNum(header.exchange_diff);
    const remaining = settle - pay - disc - exch;
    return {
      total_balance: arapFormatAmt2(bal),
      total_pay: arapFormatAmt2(pay),
      total_discount: arapFormatAmt2(disc),
      remaining: arapFormatAmt2(remaining),
    };
  }

  function computeArapTotalsFromDoc(doc) {
    return computeArapTotalsFromState({ allLines: doc.lines, document: doc });
  }

  function syncArapDomToAllLines(overlay) {
    if (!arapModalState) return;
    const visible = arapModalState.document.lines || [];
    overlay.querySelectorAll("[data-arap-col]").forEach((inp) => {
      const ri = parseInt(inp.dataset.arapRow, 10);
      const col = inp.dataset.arapCol;
      const vis = visible[ri];
      if (!vis) return;
      const ai = arapModalState.allLines.findIndex(
        (l) => l.tx_key === vis.tx_key && l.inv_no === vis.inv_no
      );
      if (ai >= 0) arapModalState.allLines[ai][col] = inp.value;
    });
    const exch = $("#arap-exchange-diff", overlay);
    if (exch && arapModalState.document.header) {
      arapModalState.document.header.exchange_diff = exch.value;
    }
  }

  function collectArapDocumentForSave(overlay) {
    syncArapDomToAllLines(overlay);
    return {
      mode: arapModalState.document.mode,
      header: arapModalState.document.header,
      lines: arapModalState.allLines,
    };
  }

  function applyArapVisibleLines(state, selectRow) {
    state.document.lines = arapFilterLines(state.allLines, state.filterKeyword);
    state.totals = computeArapTotalsFromState(state);
    const n = state.document.lines.length;
    if (n <= 0) {
      state.selectedRow = null;
      return;
    }
    const r =
      selectRow != null && selectRow >= 0 && selectRow < n
        ? selectRow
        : state.selectedRow != null && state.selectedRow < n
          ? state.selectedRow
          : 0;
    state.selectedRow = r;
  }

  function refreshArapModalBody(tab) {
    const overlay = $("#arap-modal-overlay");
    if (!overlay || !arapModalState) return;
    const body = overlay.querySelector(".arap-modal-body");
    if (!body) return;
    body.innerHTML = renderArapModalBody(arapModalState);
    bindArapModalBodyEvents(tab);
    requestAnimationFrame(() => syncArapFooterWidths(overlay));
  }

  function syncArapFooterWidths(overlay) {
    const block = overlay?.querySelector(".arap-grid-block");
    const table = overlay?.querySelector(".arap-table-main");
    const grid = overlay?.querySelector(".arap-foot-grid");
    if (!block || !table || !grid) return;
    const ths = table.querySelectorAll("thead th");
    if (ths.length < 9) return;
    const bRect = block.getBoundingClientRect();
    const balTh = ths[6].getBoundingClientRect();
    const payTh = ths[7].getBoundingClientRect();
    const discTh = ths[8].getBoundingClientRect();
    const titleW = Math.max(0, Math.floor(balTh.left - bRect.left));
    grid.style.setProperty("--foot-title-w", `${titleW}px`);
    grid.style.setProperty("--col-bal-w", `${Math.max(90, Math.floor(balTh.width))}px`);
    grid.style.setProperty("--col-pay-w", `${Math.max(90, Math.floor(payTh.width))}px`);
    grid.style.setProperty("--col-disc-w", `${Math.max(90, Math.floor(discTh.width))}px`);
  }

  function arapViewState(state) {
    const doc = state.document || state;
    return {
      mode: doc.mode || state.mode,
      header: doc.header || state.header || {},
      lines: doc.lines || state.lines || [],
      totals: state.totals || {},
      selectedRow: state.selectedRow,
      keyword: state.keyword || "",
    };
  }

  function arapCellDisplay(col, ln) {
    if (col === "tx_key") {
      const key = String(ln.tx_key || "").trim();
      return escapeHtml(key || String(ln.inv_no || "").trim());
    }
    if (col === "date") return escapeHtml(arapFormatDate(ln.date));
    if (col === "currency") return escapeHtml(ln.currency || "");
    if (col === "rate") return escapeHtml(arapFormatRate4(ln.rate));
    if (col === "net_amt") return escapeHtml(arapFormatAmt2(ln.net_amt));
    if (col === "paid_amt") return escapeHtml(arapFormatAmt2(ln.paid_amt));
    if (col === "balance") return escapeHtml(arapFormatAmt2(ln.balance));
    return escapeHtml(ln[col] || "");
  }

  function renderArapFooterPanel(state) {
    const totals = state.totals || computeArapTotalsFromState(state);
    const h = (state.document || state).header || state.header || {};
    const exchVal = String(h.exchange_diff ?? "0").trim() || "0";
    return `<div class="arap-footer-panel">
      <div class="arap-foot-grid">
        <span class="arap-foot-label">${escapeHtml(t("arapTotal"))}</span>
        <div class="arap-sum-box arap-sum-balance num-field">${escapeHtml(totals.total_balance || "0.00")}</div>
        <div class="arap-sum-box arap-sum-pay num-field">${escapeHtml(totals.total_pay || "0.00")}</div>
        <div class="arap-sum-box arap-sum-disc num-field">${escapeHtml(totals.total_discount || "0.00")}</div>
        <div class="arap-foot-stretch"></div>
        <span class="arap-foot-label">${escapeHtml(t("arapExchDiff"))}</span>
        <div class="arap-foot-gap"></div>
        <div class="arap-foot-exchange"><input type="text" id="arap-exchange-diff" class="num-field" value="${escapeHtml(exchVal)}"></div>
        <div class="arap-foot-gap"></div>
        <div class="arap-foot-stretch"></div>
        <span class="arap-foot-label">${escapeHtml(t("arapRemain"))}</span>
        <div class="arap-foot-gap"></div>
        <div class="arap-sum-box arap-sum-remain num-field">${escapeHtml(totals.remaining || "0.00")}</div>
        <div class="arap-foot-gap"></div>
        <div class="arap-foot-stretch"></div>
      </div>
    </div>`;
  }

  function renderArapModalBody(state) {
    const view = arapViewState(state);
    const h = view.header;
    const partyText = arapPartyText(h);
    const cols = ["tx_key", "date", "currency", "rate", "net_amt", "paid_amt", "balance", "pay_amount", "discount"];
    const lines = view.lines || [];
    const cur =
      view.selectedRow != null && view.selectedRow >= 0 && view.selectedRow < lines.length
        ? view.selectedRow + 1
        : null;
    const navText = formatRecordNavLabel(lines.length, cur);
    const disFirst = !lines.length || (cur != null && cur <= 1);
    const disPrev = !lines.length || cur == null || cur <= 1;
    const disNext = !lines.length || cur == null || cur >= lines.length;
    const disLast = !lines.length || (cur != null && cur >= lines.length);
    const emptyCells = cols.map(() => `<td class="arap-pad-cell"></td>`).join("");
    let rows = lines
      .map((ln, ri) => {
        const sel = view.selectedRow === ri ? " selected" : "";
        const alt = ri % 2 === 1 ? " arap-row-alt" : "";
        const cells = cols
          .map((c) => {
            if (c === "pay_amount" || c === "discount") {
              return `<td class="num-field arap-editable-col"><input type="text" class="arap-cell-input num-field" data-arap-row="${ri}" data-arap-col="${c}" value="${escapeHtml(ln[c] || "")}"></td>`;
            }
            const cls = ["rate", "net_amt", "paid_amt", "balance"].includes(c) ? " num-field" : "";
            return `<td class="${cls.trim()}">${arapCellDisplay(c, ln)}</td>`;
          })
          .join("");
        return `<tr class="arap-row${sel}${alt}" data-arap-row="${ri}">${cells}</tr>`;
      })
      .join("");
    const padCount = Math.max(0, ARAP_GRID_VISIBLE_ROWS - lines.length);
    for (let i = 0; i < padCount; i++) {
      const alt = (lines.length + i) % 2 === 1 ? " arap-row-alt" : "";
      rows += `<tr class="arap-row-pad${alt}" aria-hidden="true">${emptyCells}</tr>`;
    }
    const headerCells = arapHeaderCells();
    return `
      <div class="arap-header-grid">
        <div class="arap-header-field"><label>${escapeHtml(t("arapVouKey"))}</label><input readonly value="${escapeHtml(h.vou_key || "")}"></div>
        <div class="arap-header-field"><label>${escapeHtml(t("arapSettleDate"))}</label><input readonly value="${escapeHtml(arapFormatDate(h.settle_date || ""))}"></div>
        <div class="arap-header-field"><label>${escapeHtml(arapPartyLabel(view.mode))}</label><input readonly value="${escapeHtml(partyText)}"></div>
        <div class="arap-header-field"><label>${escapeHtml(t("arapSettleAmt"))}</label><input readonly class="num-field" value="${escapeHtml(arapFormatAmt2(h.settle_amount || ""))}"></div>
      </div>
      <div class="arap-search-row">
        <label class="search-label">${t("searchLabel")}</label>
        <input type="text" id="arap-search-input" value="${escapeHtml(view.keyword || "")}">
        ${iconBtn(t("search"), "search", "btn action-btn", 'data-arap-act="search"')}
        ${iconBtn(t("filter"), "filter", "btn action-btn", 'data-arap-act="filter"')}
      </div>
      <div class="arap-toolbar-row">
        ${iconBtnOnly(t("navFirst"), "nav-first", "btn nav-btn", `data-arap-nav="first"${disFirst ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navPrev"), "nav-prev", "btn nav-btn", `data-arap-nav="prev"${disPrev ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navNext"), "nav-next", "btn nav-btn", `data-arap-nav="next"${disNext ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navLast"), "nav-last", "btn nav-btn", `data-arap-nav="last"${disLast ? " disabled" : ""}`)}
        <span class="arap-record-nav">${escapeHtml(navText)}</span>
        ${iconBtn(t("arapAuto"), "filter", "btn action-btn", 'data-arap-act="auto"')}
        ${iconBtn(t("save"), "save", "btn action-btn", 'data-arap-act="save"')}
        ${iconBtn(t("cancel"), "cancel", "btn action-btn", 'data-arap-act="cancel"')}
      </div>
      <div class="arap-grid-block arap-grid-15-rows">
        <div class="arap-table-scroll">
          <table class="arap-table arap-table-main">
            <colgroup>
              <col class="arap-col-tx-key">
              <col class="arap-col-date">
              <col class="arap-col-curr">
              <col class="arap-col-rate">
              <col class="arap-col-amt">
              <col class="arap-col-amt">
              <col class="arap-col-balance">
              <col class="arap-col-pay">
              <col class="arap-col-disc">
            </colgroup>
            <thead><tr>${headerCells.join("")}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        ${renderArapFooterPanel(state)}
      </div>`;
  }

  function collectArapDocumentFromDom(overlay) {
    return collectArapDocumentForSave(overlay);
  }

  function arapUpdateFooterTotals(overlay) {
    if (!arapModalState) return;
    syncArapDomToAllLines(overlay);
    const totals = computeArapTotalsFromState(arapModalState);
    arapModalState.totals = totals;
    const panel = overlay.querySelector(".arap-footer-panel");
    if (!panel) return;
    const set = (sel, val) => {
      const el = panel.querySelector(sel);
      if (el) el.textContent = val;
    };
    set(".arap-sum-balance", totals.total_balance);
    set(".arap-sum-pay", totals.total_pay);
    set(".arap-sum-disc", totals.total_discount);
    set(".arap-sum-remain", totals.remaining);
  }

  function arapNavSelect(tab, row) {
    if (!arapModalState) return;
    const total = (arapModalState.document.lines || []).length;
    if (total <= 0) return;
    arapModalState.selectedRow = Math.max(0, Math.min(total - 1, row));
    refreshArapModalBody(tab);
    const overlay = $("#arap-modal-overlay");
    const tr = overlay?.querySelector(`tr[data-arap-row="${arapModalState.selectedRow}"]`);
    if (tr) tr.scrollIntoView({ block: "nearest" });
  }

  function arapOnSearch(tab) {
    const overlay = $("#arap-modal-overlay");
    if (!overlay || !arapModalState) return;
    const kw = ($("#arap-search-input", overlay) || {}).value?.trim() || "";
    if (!kw) return;
    syncArapDomToAllLines(overlay);
    arapModalState.keyword = kw;
    if (arapModalState.filterKeyword) {
      arapModalState.filterKeyword = "";
      arapModalState.document.lines = arapModalState.allLines.slice();
    }
    const idx = arapFindLineIndex(arapModalState.allLines, kw);
    if (idx == null) return;
    arapModalState.document.lines = arapModalState.allLines.slice();
    arapModalState.filterKeyword = "";
    arapModalState.selectedRow = idx;
    arapModalState.totals = computeArapTotalsFromState(arapModalState);
    refreshArapModalBody(tab);
    const tr = overlay.querySelector(`tr[data-arap-row="${idx}"]`);
    if (tr) tr.scrollIntoView({ block: "nearest" });
  }

  function arapOnFilter(tab) {
    const overlay = $("#arap-modal-overlay");
    if (!overlay || !arapModalState) return;
    syncArapDomToAllLines(overlay);
    const kw = ($("#arap-search-input", overlay) || {}).value?.trim() || "";
    arapModalState.keyword = kw;
    arapModalState.filterKeyword = kw;
    applyArapVisibleLines(arapModalState, 0);
    refreshArapModalBody(tab);
  }

  function bindArapModalBodyEvents(tab) {
    const overlay = $("#arap-modal-overlay");
    if (!overlay || !arapModalState) return;
    const body = overlay.querySelector(".arap-modal-body");
    const scrollHost = overlay?.querySelector(".arap-table-scroll");
    if (scrollHost) {
      scrollHost.addEventListener("scroll", () => syncArapFooterWidths(overlay), { passive: true });
    }
    body.querySelectorAll(".arap-row").forEach((tr) => {
      tr.addEventListener("click", () => {
        arapNavSelect(tab, parseInt(tr.dataset.arapRow, 10));
      });
    });
    body.querySelectorAll(".arap-cell-input").forEach((inp) => {
      inp.addEventListener("click", (e) => e.stopPropagation());
      inp.addEventListener("change", () => arapUpdateFooterTotals(overlay));
      inp.addEventListener("input", () => arapUpdateFooterTotals(overlay));
    });
    const exch = $("#arap-exchange-diff", body);
    if (exch) {
      exch.addEventListener("change", () => arapUpdateFooterTotals(overlay));
      exch.addEventListener("input", () => arapUpdateFooterTotals(overlay));
    }
    body.querySelectorAll("[data-arap-nav]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        const lines = arapModalState.document.lines || [];
        const cur = arapModalState.selectedRow ?? 0;
        const nav = btn.dataset.arapNav;
        if (nav === "first") arapNavSelect(tab, 0);
        else if (nav === "prev") arapNavSelect(tab, cur - 1);
        else if (nav === "next") arapNavSelect(tab, cur + 1);
        else if (nav === "last") arapNavSelect(tab, lines.length - 1);
      });
    });
    body.querySelectorAll('[data-arap-act="search"]').forEach((btn) => {
      btn.addEventListener("click", () => arapOnSearch(tab));
    });
    body.querySelectorAll('[data-arap-act="filter"]').forEach((btn) => {
      btn.addEventListener("click", () => arapOnFilter(tab));
    });
    const searchInput = $("#arap-search-input", body);
    if (searchInput) {
      searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          arapOnSearch(tab);
        }
      });
    }
    body.querySelectorAll('[data-arap-act="auto"], [data-arap-act="save"], [data-arap-act="cancel"]').forEach((btn) => {
      btn.addEventListener("click", () => handleArapToolbarAction(tab, btn.dataset.arapAct));
    });
  }

  async function handleArapToolbarAction(tab, act) {
    const overlay = $("#arap-modal-overlay");
    if (!overlay || !arapModalState) return;
    if (act === "cancel") {
      closeArapModal();
      return;
    }
    const doc = collectArapDocumentForSave(overlay);
    if (act === "auto") {
      try {
        const res = await api(`/work/${encodeURIComponent(tab.doProc)}/arap/auto`, {
          method: "POST",
          body: JSON.stringify({ document: doc }),
        });
        arapModalState.allLines = res.lines || [];
        arapModalState.document = {
          mode: res.mode,
          header: res.header,
          lines: arapFilterLines(arapModalState.allLines, arapModalState.filterKeyword),
        };
        arapModalState.totals = computeArapTotalsFromState(arapModalState);
        refreshArapModalBody(tab);
      } catch (e) {
        showCopyableMessage(t("notice"), e.message);
      }
      return;
    }
    if (act === "save") {
      try {
        await api(`/work/${encodeURIComponent(tab.doProc)}/arap/save`, {
          method: "PUT",
          body: JSON.stringify({ document: doc }),
        });
        showCopyableMessage(arapTitle(arapModalState.document.mode), t("arapSaved"));
        closeArapModal();
        await loadWorkData(tab, { asFilter: tab.filtered });
        renderTabs();
      } catch (e) {
        showCopyableMessage(t("notice"), e.message);
      }
    }
  }

  function bindArapModalEvents(tab) {
    bindArapModalBodyEvents(tab);
  }

  async function openArapModal(tab) {
    if (tab.selectedRow == null) {
      showAlert(t("arapSelectVoucher"));
      return;
    }
    const oldRow = tab.physicalRows[tab.selectedRow];
    try {
      const data = await api(`/work/${encodeURIComponent(tab.doProc)}/arap/load`, {
        method: "POST",
        body: JSON.stringify({ old_row: oldRow }),
      });
      closeArapModal();
      arapModalState = {
        tab,
        allLines: JSON.parse(JSON.stringify(data.lines || [])),
        document: { mode: data.mode, header: data.header, lines: data.lines || [] },
        totals: null,
        mode: data.mode,
        selectedRow: data.lines && data.lines.length ? 0 : null,
        keyword: "",
        filterKeyword: "",
      };
      arapModalState.totals = computeArapTotalsFromState(arapModalState);
      const overlay = document.createElement("div");
      overlay.id = "arap-modal-overlay";
      overlay.className = "arap-modal-overlay";
      overlay.innerHTML = `<div class="arap-modal" role="dialog" aria-modal="true">
        <div class="arap-modal-header"><h2>${escapeHtml(arapTitle(data.mode))}</h2></div>
        <div class="arap-modal-body">${renderArapModalBody(arapModalState)}</div>
      </div>`;
      document.body.appendChild(overlay);
      bindArapModalEvents(tab);
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) closeArapModal();
      });
      const onResize = () => syncArapFooterWidths(overlay);
      window.addEventListener("resize", onResize);
      overlay._arapResize = onResize;
      requestAnimationFrame(() => syncArapFooterWidths(overlay));
    } catch (e) {
      showAlert(e.message || t("otherNotConfigured"));
    }
  }

  function isAccountQueryProgram(doProc, tableName, otherTitle) {
    const title = String(otherTitle || "");
    const titleU = title.toUpperCase();
    const proc = String(doProc || "").trim().toUpperCase();
    const tbl = String(tableName || "").trim().toUpperCase();
    // 實務：DO_PROC=Account、WORK_FILE=ACCOUNT、OTHER=Enquiry/查詢
    if (proc === "ACCOUNT" || proc === "DO_ACCOUNT" || tbl === "ACCOUNT") {
      if (
        !title.trim() ||
        title.includes("查詢") ||
        titleU.includes("ENQUIRY") ||
        titleU.includes("QUERY") ||
        title.includes("賬戶") ||
        title.includes("帳戶") ||
        titleU.includes("ACCOUNT")
      ) {
        return true;
      }
    }
    const isAccTitle =
      title.includes("賬戶") || title.includes("帳戶") || titleU.includes("ACCOUNT");
    if (title.includes("查詢") || titleU.includes("QUERY")) {
      if (isAccTitle) return true;
      if (tbl === "ACCOUNT") return true;
    }
    const accProcs = [
      "DO_ACC_QUERY",
      "ACC_QUERY",
      "ACCOUNT_QUERY",
      "DO_ACCOUNT_QUERY",
      "DO_ACCQ",
      "ACCQ",
    ];
    if (accProcs.some((p) => proc === p || proc.endsWith(p))) return true;
    if (tbl === "ACCOUNT" && (title.includes("查詢") || titleU.includes("QUERY"))) return true;
    return false;
  }

  function isStockQueryProgram(doProc, tableName, otherTitle) {
    if (isAccountQueryProgram(doProc, tableName, otherTitle)) return false;
    const title = String(otherTitle || "");
    const titleU = title.toUpperCase();
    const proc = String(doProc || "").trim().toUpperCase();
    const tbl = String(tableName || "").trim().toUpperCase();
    const isStockTitle =
      title.includes("存貨") ||
      title.includes("庫存") ||
      titleU.includes("STOCK") ||
      titleU.includes("INVENTORY");
    if (title.includes("查詢") || titleU.includes("QUERY")) {
      if (isStockTitle) return true;
      if (tbl === "STOCK") return true;
    }
    const stockProcs = [
      "DO_STOCK_QUERY",
      "STOCK_QUERY",
      "DO_STKQ",
      "STK_QUERY",
      "STKQUERY",
      "INVENTORY_QUERY",
    ];
    if (stockProcs.some((p) => proc === p || proc.endsWith(p))) return true;
    if (tbl === "STOCK" && (title.includes("查詢") || titleU.includes("QUERY"))) return true;
    return false;
  }

  function isPartyQueryProgram(doProc, tableName, otherTitle) {
    const title = String(otherTitle || "");
    const titleU = title.toUpperCase();
    const proc = String(doProc || "").trim().toUpperCase();
    const tbl = String(tableName || "").trim().toUpperCase();
    if (isStockQueryProgram(doProc, tableName, otherTitle)) return false;
    if (isAccountQueryProgram(doProc, tableName, otherTitle)) return false;
    const isCust =
      title.includes("顧客") ||
      title.includes("客戶") ||
      titleU.includes("CUSTOMER") ||
      titleU.includes("CUST");
    const isVend =
      title.includes("供應") ||
      title.includes("廠商") ||
      titleU.includes("VENDOR") ||
      titleU.includes("VEND") ||
      titleU.includes("SUPPLIER");
    if (title.includes("查詢") || titleU.includes("QUERY")) {
      if (isCust || isVend) return true;
      if (tbl === "CUSTVEND") return true;
      return false;
    }
    const custProcs = [
      "DO_CUST_QUERY",
      "CUST_QUERY",
      "DO_CUSTQ",
      "CUSTOMER_QUERY",
      "CUSTQ",
    ];
    const vendProcs = [
      "DO_VEND_QUERY",
      "VEND_QUERY",
      "DO_VENDQ",
      "VENDOR_QUERY",
      "SUPPLIER_QUERY",
      "VENDQ",
    ];
    if (custProcs.some((p) => proc === p || proc.endsWith(p))) return true;
    if (vendProcs.some((p) => proc === p || proc.endsWith(p))) return true;
    if (tbl === "CUSTVEND" && (title.includes("查詢") || titleU.includes("QUERY"))) {
      return true;
    }
    if (tbl === "CUSTVEND" && (title.includes("顧客-供應商") || title.includes("客戶-供應商"))) {
      return true;
    }
    return false;
  }

  function isArapSettlementProgram(doProc, tableName, otherTitle) {
    const proc = String(doProc || "").trim().toUpperCase();
    if (["DO_ARAP", "DO_AR", "DO_AP", "ARAP"].includes(proc)) return true;
    if (proc === "AR" || proc === "AP") {
      return String(tableName || "").trim().toUpperCase() === "VOUCHER";
    }
    const title = String(otherTitle || "").toUpperCase();
    if (String(tableName || "").trim().toUpperCase() !== "VOUCHER") return false;
    for (const m of ["清賬", "清帳", "SETTLEMENT", "應收應付", "ARAP", "A/R", "A/P"]) {
      if (title.includes(m)) return true;
    }
    return false;
  }

  function isWorkRowFullyPaid(tab) {
    const fields = tab.physicalFields || tab.fields || [];
    const names = new Set(fields.map((f) => String(f || "").trim().toUpperCase()).filter(Boolean));
    if (!names.has("PAID_AMT")) return false;
    if (!names.has("NET_AMT") && !names.has("TX_AMT")) return false;
    const row =
      tab.selectedRow != null && tab.physicalRows && tab.physicalRows[tab.selectedRow]
        ? tab.physicalRows[tab.selectedRow]
        : null;
    if (!row) return false;
    const idx = (name) => fields.findIndex((f) => String(f || "").trim().toUpperCase() === name);
    const num = (name) => {
      const i = idx(name);
      if (i < 0 || i >= row.length) return 0;
      const t = String(row[i] ?? "")
        .replace(/,/g, "")
        .trim();
      const n = parseFloat(t);
      return Number.isFinite(n) ? n : 0;
    };
    let net = num("NET_AMT");
    if (!net) net = num("TX_AMT") - num("DISC_AMT");
    const paid = num("PAID_AMT");
    return net <= paid;
  }

  function refreshWorkOtherButtonState(tab, page) {
    page = page || document.querySelector(`.work-page[data-tab="${tab.id}"]`);
    if (!page) return;
    const btn = page.querySelector('[data-act="other"]');
    if (!btn) return;
    const dis = isWorkRowFullyPaid(tab);
    btn.disabled = dis;
    btn.classList.toggle("disabled", dis);
  }

  function isReceiptPaymentProgram(doProc, tableName, otherTitle) {
    const tbl = String(tableName || "").trim().toUpperCase();
    const title = String(otherTitle || "").trim();
    const titleU = title.toUpperCase();
    void doProc;
    if (tbl === "INVOICE") {
      return title.includes("收款") || titleU.includes("RECEIPT") || titleU.includes("RECEIVE") || titleU.includes("COLLECTION");
    }
    if (tbl === "PURCHASE") {
      return (
        title.includes("付款") ||
        titleU.includes("PAYMENT") ||
        titleU.includes("PAY ") ||
        titleU.trim() === "PAYMENT" ||
        titleU.trim() === "PAY"
      );
    }
    if (title.includes("收款") || titleU.includes("RECEIPT")) return tbl === "";
    if (title.includes("付款") || titleU.includes("PAYMENT")) return tbl === "";
    return false;
  }

  function isReceiptPaymentTab(tab) {
    const wa = tabWorkActions(tab);
    return isReceiptPaymentProgram(tab.doProc, tabTableName(tab), wa.other_title);
  }

  function closeReceiptPaymentModal() {
    const el = $("#rp-modal-overlay");
    if (el) el.remove();
    receiptPaymentModalState = null;
  }

  function rpField(label, inputHtml, opts = {}) {
    const planned = !!opts.planned;
    const wide = !!opts.wide;
    const longCols = planned && wide ? 4 : 2;
    const fieldCls = [
      "form-field",
      planned ? "form-field-stacked" : "",
      wide ? "form-field-wide" : "",
    ]
      .filter(Boolean)
      .join(" ");
    const wideStyle = wide ? ` style="--form-long-cols:${longCols};--form-long-rows:2"` : "";
    return `<div class="${fieldCls}"${wideStyle}><label>${escapeHtml(label)}</label>${inputHtml}</div>`;
  }

  function rpRoInput(value, extraClass = "") {
    const cls = extraClass ? ` ${extraClass}` : "";
    return `<input type="text" readonly class="rp-ro${cls}" value="${escapeHtml(value || "")}">`;
  }

  function rpEditInput(name, value, extraClass = "") {
    const cls = extraClass ? ` ${extraClass}` : "";
    return `<input type="text" data-rp-field="${escapeHtml(name)}" class="rp-edit${cls}" value="${escapeHtml(value || "")}">`;
  }

  const RP_PAY_METHOD_OPTIONS = [
    "CASH",
    "CHEQUE",
    "EPS",
    "VISA",
    "TT",
    "FPS",
    "AliPay",
    "WeChatPay",
  ];
  const RP_DEFAULT_PAY_METHOD = "CHEQUE";

  function rpPayMethodSelect(value) {
    const cur = String(value || "").trim() || RP_DEFAULT_PAY_METHOD;
    const opts = RP_PAY_METHOD_OPTIONS.map((opt) => {
      const sel =
        opt === cur || opt.toUpperCase() === cur.toUpperCase() ? " selected" : "";
      return `<option value="${escapeHtml(opt)}"${sel}>${escapeHtml(opt)}</option>`;
    }).join("");
    return `<select data-rp-field="pay_method" class="rp-edit">${opts}</select>`;
  }

  function rpRemarkInput(value) {
    return `<textarea data-rp-field="remark" class="rp-edit rp-remark" rows="3">${escapeHtml(value || "")}</textarea>`;
  }

  function rpLookupInput(name, value) {
    return `<div class="lookup-field-wrap">
      <input type="text" data-rp-field="${escapeHtml(name)}" class="rp-edit" value="${escapeHtml(value || "")}">
      <button type="button" class="btn secondary lookup-btn" data-rp-lookup="${escapeHtml(name)}" title="${escapeHtml(t("lookup"))}" aria-label="${escapeHtml(t("lookup"))}">…</button>
    </div>`;
  }

  function rpFormatAmt(val) {
    return arapFormatAmt2(val || "0");
  }

  function rpFormatRate(val) {
    return arapFormatRate4(val || "0");
  }

  function rpFormatDate(val) {
    return formatAppDateDisplay(val || "");
  }

  function renderReceiptPaymentBody(state) {
    const h = state.document.header || {};
    const f = state.document.form || {};
    const mode = state.document.mode || h.mode || "AR";
    const layoutMode = getFormLayoutMode();
    const planned = layoutMode === FORM_LAYOUT_PLANNED;
    const dims = formLayoutDims(layoutMode);
    // 收付款：預設二欄；規劃介面四欄
    const colsClass = planned ? "form-grid-cols-4" : "form-grid-cols-2";
    const layoutClass = planned ? "form-layout-planned" : "form-layout-default";
    const styleParts = [
      `--form-editor-w:${dims.editorW}px`,
      `--form-editor-h:${dims.editorH}px`,
      `--form-label-w:${dims.labelW}px`,
      planned ? `--form-long-cols:4` : `--form-long-cols:2`,
    ].join(";");
    const partyKeyLbl = mode === "AP" ? t("rpPartyKeyAP") : t("rpPartyKeyAR");
    const partyNameLbl = mode === "AP" ? t("rpPartyNameAP") : t("rpPartyNameAR");
    const netLbl = mode === "AP" ? t("rpNetAmtAP") : t("rpNetAmtAR");
    const fo = { planned };
    const viewFields = [
      rpField(t("rpInvNo"), rpRoInput(h.inv_no || h.inv_key || ""), fo),
      rpField(t("rpInvDate"), rpRoInput(rpFormatDate(h.inv_date || "")), fo),
      rpField(partyKeyLbl, rpRoInput(h.party_key || ""), fo),
      rpField(partyNameLbl, rpRoInput(h.party_name || ""), fo),
      rpField(t("rpCurrency"), rpRoInput(h.currency || ""), fo),
      rpField(t("rpRate"), rpRoInput(rpFormatRate(h.rate || ""), "num-field"), fo),
      rpField(netLbl, rpRoInput(rpFormatAmt(h.net_amt || ""), "num-field"), fo),
      rpField(t("rpPaidAmt"), rpRoInput(rpFormatAmt(h.paid_amt || ""), "num-field"), fo),
      rpField(t("rpBalance"), rpRoInput(rpFormatAmt(h.balance || ""), "num-field"), fo),
    ].join("");
    const editFields = [
      rpField(t("rpPayAmount"), rpEditInput("pay_amount", rpFormatAmt(f.pay_amount || ""), "num-field"), fo),
      rpField(t("rpPayDate"), rpEditInput("pay_date", rpFormatDate(f.pay_date || "")), fo),
      rpField(t("rpPayMethod"), rpPayMethodSelect(f.pay_method || RP_DEFAULT_PAY_METHOD), fo),
      rpField(t("rpBank"), rpEditInput("bank", f.bank || ""), fo),
      rpField(t("rpCheque"), rpEditInput("cheque", f.cheque || ""), fo),
      rpField(t("rpChqDate"), rpEditInput("chq_date", rpFormatDate(f.chq_date || "")), fo),
      rpField(t("rpDebitAc"), rpLookupInput("debit_ac", f.debit_ac || ""), fo),
      rpField(t("rpCreditAc"), rpLookupInput("credit_ac", f.credit_ac || ""), fo),
      rpField(t("rpRemark"), rpRemarkInput(f.remark || ""), { ...fo, wide: true }),
    ].join("");
    return `<div class="rp-modal-body">
      <fieldset class="rp-group">
        <legend>${escapeHtml(t("rpDocGroup"))}</legend>
        <div class="form-grid ${colsClass} ${layoutClass}" style="${styleParts}">${viewFields}</div>
      </fieldset>
      <fieldset class="rp-group">
        <legend>${escapeHtml(t("rpPayGroup"))}</legend>
        <div class="form-grid ${colsClass} ${layoutClass}" style="${styleParts}">${editFields}</div>
      </fieldset>
      <div class="arap-modal-actions rp-actions">
        ${iconBtn(t("save"), "save", "btn action-btn", 'data-rp-act="save"')}
        ${iconBtn(t("cancel"), "cancel", "btn action-btn", 'data-rp-act="cancel"')}
      </div>
    </div>`;
  }

  function collectReceiptPaymentForm(overlay) {
    if (!receiptPaymentModalState) return null;
    const form = { ...(receiptPaymentModalState.document.form || {}) };
    overlay.querySelectorAll("[data-rp-field]").forEach((inp) => {
      const key = inp.dataset.rpField;
      let val = inp.value;
      if (key === "pay_amount") val = String(val || "").replace(/,/g, "").trim();
      else if (key === "pay_date" || key === "chq_date") val = normalizeAppDateText(val || "");
      else if (key === "remark" && inp.tagName === "TEXTAREA") val = inp.value;
      form[key] = val;
    });
    receiptPaymentModalState.document.form = form;
    return {
      mode: receiptPaymentModalState.document.mode,
      header: receiptPaymentModalState.document.header,
      form,
      vou_key: receiptPaymentModalState.document.vou_key || "",
    };
  }

  async function saveReceiptPaymentModal(tab) {
    const overlay = $("#rp-modal-overlay");
    if (!overlay || !receiptPaymentModalState) return;
    const document = collectReceiptPaymentForm(overlay);
    try {
      const res = await api(`/work/${encodeURIComponent(tab.doProc)}/receipt-payment/save`, {
        method: "PUT",
        body: JSON.stringify({ document }),
      });
      const vouKey = res?.vou_key || "";
      showAlert(res?.message || `${t("rpSavedPrefix")}${vouKey}`);
      closeReceiptPaymentModal();
      await doRefreshWorkData(tab);
    } catch (e) {
      showAlert(e.message || t("otherNotConfigured"));
    }
  }

  function bindReceiptPaymentModalEvents(tab) {
    const overlay = $("#rp-modal-overlay");
    if (!overlay) return;
    overlay.querySelectorAll('[data-rp-act="cancel"]').forEach((btn) => {
      btn.addEventListener("click", () => closeReceiptPaymentModal());
    });
    overlay.querySelectorAll('[data-rp-act="save"]').forEach((btn) => {
      btn.addEventListener("click", () => saveReceiptPaymentModal(tab));
    });
    overlay.querySelectorAll("[data-rp-lookup]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const field = btn.dataset.rpLookup;
        const input = overlay.querySelector(`[data-rp-field="${field}"]`);
        openLookupPicker(null, "AC_KEY", "ACCOUNT", "AC_KEY", {
          doProc: tab.doProc,
          onSelect: (val) => {
            if (input && val != null) input.value = String(val);
          },
        }).catch((err) => showAlert(err.message || t("otherNotConfigured")));
      });
    });
    const payAmt = overlay.querySelector('[data-rp-field="pay_amount"]');
    if (payAmt) {
      payAmt.addEventListener("blur", () => {
        payAmt.value = rpFormatAmt(payAmt.value);
      });
    }
    ["pay_date", "chq_date"].forEach((name) => {
      const el = overlay.querySelector(`[data-rp-field="${name}"]`);
      if (!el) return;
      el.addEventListener("blur", () => {
        el.value = rpFormatDate(el.value);
      });
    });
  }

  async function openReceiptPaymentModal(tab) {
    if (tab.selectedRow == null) {
      showAlert(t("rpSelectRow"));
      return;
    }
    const oldRow = tab.physicalRows[tab.selectedRow];
    try {
      const data = await api(`/work/${encodeURIComponent(tab.doProc)}/receipt-payment/load`, {
        method: "POST",
        body: JSON.stringify({ old_row: oldRow }),
      });
      closeReceiptPaymentModal();
      const mode = data.mode || (data.header && data.header.mode) || "AR";
      const title =
        (data.other_title && String(data.other_title).trim()) ||
        (mode === "AP" ? t("rpTitleAP") : t("rpTitleAR"));
      receiptPaymentModalState = {
        tab,
        document: {
          mode,
          vou_key: data.vou_key || "",
          header: data.header || {},
          form: data.form || {},
        },
      };
      const overlay = document.createElement("div");
      overlay.id = "rp-modal-overlay";
      overlay.className = "arap-modal-overlay";
      overlay.innerHTML = `<div class="arap-modal rp-modal" role="dialog" aria-modal="true">
        <div class="arap-modal-header"><h2>${escapeHtml(title)}</h2></div>
        <div class="arap-modal-body">${renderReceiptPaymentBody(receiptPaymentModalState)}</div>
      </div>`;
      document.body.appendChild(overlay);
      bindReceiptPaymentModalEvents(tab);
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) closeReceiptPaymentModal();
      });
    } catch (e) {
      showAlert(e.message || t("otherNotConfigured"));
    }
  }

  function tabTableName(tab) {
    return String(tab?.tableName || tab?.workFile || tab?.table_name || "").trim();
  }

  function isPartyQueryTab(tab) {
    const wa = tabWorkActions(tab);
    return isPartyQueryProgram(tab.doProc, tabTableName(tab), wa.other_title);
  }

  function isStockQueryTab(tab) {
    const wa = tabWorkActions(tab);
    return isStockQueryProgram(tab.doProc, tabTableName(tab), wa.other_title);
  }

  function isAccountQueryTab(tab) {
    const wa = tabWorkActions(tab);
    return isAccountQueryProgram(tab.doProc, tabTableName(tab), wa.other_title);
  }

  /**
   * 查詢類型登錄表：新增查詢類型時在此加一筆（順序與 core/query_registry.py 一致）。
   * openModal / reloadFromServer 指向各類查詢實作；metadata 可從 GET /api/query-kinds 同步。
   */
  const QUERY_KIND_REGISTRY = [
    {
      kind: "account",
      tabType: "account-query",
      indexField: "account_index",
      keyField: "account_key",
      collectionField: "accounts",
      entityKeyField: "key",
      setModalState(state) {
        accountQueryModalState = state;
      },
      matchWorkTab: isAccountQueryTab,
      openModal(work, opts) {
        const key = pickQueryEntityKey(opts);
        return openAccountQueryModal(work, { accountKey: key, key });
      },
      reloadFromServer(work, tab, index, opts) {
        const key = pickQueryEntityKey(opts);
        return reloadAccountQueryFromServer(work, index, { accountKey: key, key });
      },
    },
    {
      kind: "stock",
      tabType: "stock-query",
      indexField: "stock_index",
      keyField: "stock_key",
      collectionField: "stocks",
      entityKeyField: "key",
      setModalState(state) {
        stockQueryModalState = state;
      },
      matchWorkTab: isStockQueryTab,
      openModal(work, opts) {
        const key = pickQueryEntityKey(opts);
        return openStockQueryModal(work, { stockKey: key, key });
      },
      reloadFromServer(work, tab, index, opts) {
        const key = pickQueryEntityKey(opts);
        return reloadStockQueryFromServer(work, index, { stockKey: key, key });
      },
    },
    {
      kind: "party",
      tabType: "party-query",
      indexField: "party_index",
      keyField: "party_key",
      collectionField: "parties",
      entityKeyField: "key",
      setModalState(state) {
        partyQueryModalState = state;
      },
      matchWorkTab: isPartyQueryTab,
      openModal(work, opts) {
        const key = pickQueryEntityKey(opts);
        return openPartyQueryModal(work, { partyKey: key, key });
      },
      reloadFromServer(work, tab, index, opts) {
        const key = pickQueryEntityKey(opts);
        return reloadPartyQueryFromServer(work, index, { partyKey: key, key });
      },
    },
  ];

  function pickQueryEntityKey(opts = {}) {
    const o = opts || {};
    if (o.key) return String(o.key).trim();
    if (o.entity_key) return String(o.entity_key).trim();
    if (o.keyword) return String(o.keyword).trim();
    for (const def of QUERY_KIND_REGISTRY) {
      const v = o[def.keyField];
      if (v) return String(v).trim();
    }
    return "";
  }

  function pickQueryEntityKeyFromAction(act) {
    const o = act || {};
    if (o.entity_key) return String(o.entity_key).trim();
    if (o.keyword) return String(o.keyword).trim();
    for (const def of QUERY_KIND_REGISTRY) {
      const v = o[def.keyField];
      if (v) return String(v).trim();
    }
    return "";
  }

  function resolveQueryKindDefForWorkTab(work) {
    for (const def of QUERY_KIND_REGISTRY) {
      if (def.matchWorkTab(work)) return def;
    }
    return null;
  }

  function findQueryKindDefByTabType(tabType) {
    return QUERY_KIND_REGISTRY.find((d) => d.tabType === tabType) || null;
  }

  async function openQueryForWorkTab(work, opts = {}) {
    const def = resolveQueryKindDefForWorkTab(work);
    if (!def) return false;
    await def.openModal(work, opts);
    return true;
  }

  function isArapSettlementTab(tab) {
    const wa = tabWorkActions(tab);
    return isArapSettlementProgram(tab.doProc, tabTableName(tab), wa.other_title);
  }

  function partyQueryTitle(mode) {
    return mode === "AP" ? t("partyQueryTitleAP") : t("partyQueryTitleAR");
  }

  function partyQueryColHeaders() {
    return [
      t("partyQueryColDate"),
      t("partyQueryColType"),
      t("partyQueryColKey"),
      t("partyQueryColCurr"),
      t("partyQueryColRate"),
      t("partyQueryColInv"),
      t("partyQueryColPaid"),
      t("partyQueryColRecv"),
      t("partyQueryColSettle"),
    ];
  }

  function partyQueryColAlign(colName) {
    return ["rate", "inv_amt", "paid_amt", "recv_amt", "settle_amt"].includes(colName)
      ? "num-field"
      : "";
  }

  function queryTabId(kind, workId) {
    return `query-${kind}-${workId}`;
  }

  function partyQueryHost() {
    return (
      document.querySelector('.query-page[data-query-kind="party"]') ||
      document.querySelector('.work-page[data-query-type="party-query"]') ||
      document.querySelector(".party-query-page") ||
      $("#party-query-modal-overlay")
    );
  }

  function partyQueryBodyHost(root) {
    if (!root) return null;
    if (root.classList.contains("query-page")) {
      return root.querySelector(".query-page-body") || root;
    }
    return root.querySelector(".arap-modal-body");
  }

  function closePartyQueryModal() {
    const id = partyQueryModalState && partyQueryModalState.id;
    partyQueryModalState = null;
    const el = $("#party-query-modal-overlay");
    if (el) el.remove();
    if (id && openTabs.some((x) => x.id === id)) closeTab(id);
  }

  function partyQueryFilterLines(lines, keyword) {
    const kw = String(keyword || "").trim().toLowerCase();
    if (!kw) return lines.slice();
    return lines.filter((ln) => {
      const blob = [
        ln.date,
        ln.tx_category,
        ln.tx_key,
        ln.currency,
        ln.rate,
        ln.inv_amt,
        ln.paid_amt,
        ln.recv_amt,
        ln.settle_amt,
      ]
        .join(" ")
        .toLowerCase();
      return blob.includes(kw);
    });
  }

  function partyQueryTotals(lines) {
    const sumGroup = (cats, k) =>
      lines
        .filter((ln) => cats.includes(String(ln.tx_category || "").toUpperCase()))
        .reduce((a, ln) => a + (parseFloat(String(ln[k] || "0").replace(/,/g, "")) || 0), 0);
    return {
      inv_amt: arapFormatAmt2(sumGroup(["INV", "REC"], "inv_amt")),
      inv_paid_amt: arapFormatAmt2(sumGroup(["INV", "REC"], "paid_amt")),
      inv_recv_amt: arapFormatAmt2(sumGroup(["INV", "REC"], "recv_amt")),
      inv_settle_amt: arapFormatAmt2(sumGroup(["INV", "REC"], "settle_amt")),
      pur_amt: arapFormatAmt2(sumGroup(["PUR", "PAY"], "inv_amt")),
      pur_paid_amt: arapFormatAmt2(sumGroup(["PUR", "PAY"], "paid_amt")),
      pur_pay_amt: arapFormatAmt2(sumGroup(["PUR", "PAY"], "recv_amt")),
      pur_settle_amt: arapFormatAmt2(sumGroup(["PUR", "PAY"], "settle_amt")),
    };
  }

  async function refreshOpenQueryTabFromServer(tab) {
    if (!tab) return;
    const work = openTabs.find((x) => x.id === tab.parentWorkId) || tab.tab;
    if (!work) return;
    const def = findQueryKindDefByTabType(tab.type);
    if (!def) return;
    def.setModalState(tab);
    const idx = tab[def.indexField] ?? 0;
    await def.reloadFromServer(work, tab, idx);
  }

  function normalizePartyQueryDateText(raw) {
    const s = String(raw || "").trim();
    if (!s) return "";
    return arapFormatDate(s) || s;
  }

  function renderPartyQueryModalBody(state) {
    const mode = state.mode || "AR";
    const party = state.party || {};
    const lines = state.lines || [];
    const totals = state.totals || partyQueryTotals(lines);
    const headers = partyQueryColHeaders();
    const colKeys = [
      "date",
      "tx_category",
      "tx_key",
      "currency",
      "rate",
      "inv_amt",
      "paid_amt",
      "recv_amt",
      "settle_amt",
    ];
    const keyLabel = t("partyQueryCustNo");
    const partyTotal = (state.parties || []).length;
    const partyCur = partyTotal ? state.party_index + 1 : null;
    const partyNav = formatRecordNavLabel(partyTotal, partyCur);
    const lineCur =
      state.selectedRow != null && state.selectedRow >= 0 && state.selectedRow < lines.length
        ? state.selectedRow + 1
        : null;
    const lineNav = formatRecordNavLabel(lines.length, lineCur);
    const disPartyFirst = !partyTotal || (partyCur != null && partyCur <= 1);
    const disPartyPrev = !partyTotal || partyCur == null || partyCur <= 1;
    const disPartyNext = !partyTotal || partyCur == null || partyCur >= partyTotal;
    const disPartyLast = !partyTotal || (partyCur != null && partyCur >= partyTotal);
    const disLineFirst = !lines.length || (lineCur != null && lineCur <= 1);
    const disLinePrev = !lines.length || lineCur == null || lineCur <= 1;
    const disLineNext = !lines.length || lineCur == null || lineCur >= lines.length;
    const disLineLast = !lines.length || (lineCur != null && lineCur >= lines.length);
    const selectedKinds = new Set(
      (Array.isArray(state.tx_kinds) ? state.tx_kinds : ["INV", "REC", "PUR", "PAY"]).map(
        (k) => String(k || "").toUpperCase()
      )
    );
    const kindChecks = [
      ["INV", t("partyQueryKindInv")],
      ["REC", t("partyQueryKindRec")],
      ["PUR", t("partyQueryKindPur")],
      ["PAY", t("partyQueryKindPay")],
    ]
      .map(
        ([v, label]) =>
          `<label class="party-query-kind-check"><input type="checkbox" class="party-query-tx-kind" value="${v}"${
            selectedKinds.has(v) ? " checked" : ""
          }> ${escapeHtml(label)}</label>`
      )
      .join("");
    let rows = lines
      .map((ln, ri) => {
        const sel = state.selectedRow === ri ? " selected" : "";
        const alt = ri % 2 === 1 ? " arap-row-alt" : "";
        const cells = colKeys
          .map((c) => {
            let v = ln[c] || "";
            if (c === "date") v = arapFormatDate(v);
            else if (c === "rate") v = arapFormatRate4(v);
            else if (["inv_amt", "paid_amt", "recv_amt", "settle_amt"].includes(c)) {
              v = arapFormatAmt2(v);
            }
            const cls = partyQueryColAlign(c);
            return `<td class="${cls}">${escapeHtml(v)}</td>`;
          })
          .join("");
        return `<tr class="arap-row party-query-row${sel}${alt}" data-party-query-row="${ri}">${cells}</tr>`;
      })
      .join("");
    const emptyCells = headers
      .map((h, i) => `<td class="arap-pad-cell ${partyQueryColAlign(colKeys[i])}"></td>`)
      .join("");
    const padCount = Math.max(0, PARTY_QUERY_GRID_VISIBLE_ROWS - lines.length);
    for (let i = 0; i < padCount; i++) {
      const alt = (lines.length + i) % 2 === 1 ? " arap-row-alt" : "";
      rows += `<tr class="arap-row-pad${alt}" aria-hidden="true">${emptyCells}</tr>`;
    }
    const head = headers
      .map((h, i) => `<th class="${partyQueryColAlign(colKeys[i])}">${escapeHtml(h)}</th>`)
      .join("");
    return `
      <div class="arap-header-grid party-query-header-grid party-query-header-left">
        <div class="arap-header-field"><label>${escapeHtml(keyLabel)}</label>
          <div class="lookup-field-wrap">
            <input type="text" class="party-query-key-input" value="${escapeHtml(party.key || "")}">
            <button type="button" class="btn secondary lookup-btn" data-party-query-act="lookup-party" title="${escapeHtml(t("lookup"))}" aria-label="${escapeHtml(t("lookup"))}">…</button>
          </div>
        </div>
        <div class="arap-header-field"><label>${escapeHtml(t("partyQueryName"))}</label><input readonly value="${escapeHtml(party.name || "")}"></div>
        <div class="arap-header-field"><label>${escapeHtml(t("partyQueryContact"))}</label><input readonly value="${escapeHtml(party.contact || "")}"></div>
        <div class="arap-header-field"><label>${escapeHtml(t("partyQueryTel"))}</label><input readonly value="${escapeHtml(party.tel || "")}"></div>
        <div class="arap-header-field"><label>${escapeHtml(t("partyQueryCredit"))}</label><input readonly class="num" value="${escapeHtml(party.credit_limit || "")}"></div>
        <div class="arap-header-field"><label>${escapeHtml(t("partyQueryRemainCredit"))}</label><input readonly class="num" value="${escapeHtml(party.remain_credit || "")}"></div>
      </div>
      <div class="arap-toolbar-row party-query-party-nav">
        ${iconBtnOnly(t("navFirst"), "nav-first", "btn nav-btn", `data-party-query-party-nav="first"${disPartyFirst ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navPrev"), "nav-prev", "btn nav-btn", `data-party-query-party-nav="prev"${disPartyPrev ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navNext"), "nav-next", "btn nav-btn", `data-party-query-party-nav="next"${disPartyNext ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navLast"), "nav-last", "btn nav-btn", `data-party-query-party-nav="last"${disPartyLast ? " disabled" : ""}`)}
        <span class="arap-record-nav">${escapeHtml(partyNav)}</span>
      </div>
      <div class="party-query-date-row">
        <label>${escapeHtml(t("partyQueryDateFrom"))}</label>
        <div class="date-field-wrap">
          <input type="text" class="party-query-date-from" value="${escapeHtml(state.date_from || "")}" placeholder="yyyy/MM/dd">
          <button type="button" class="btn secondary date-pick-btn btn-icon-only" data-party-query-date="from" title="${escapeHtml(t("printDatePickBtn"))}">${uiIcon("view-calendar", 14)}</button>
        </div>
        <label>${escapeHtml(t("partyQueryDateTo"))}</label>
        <div class="date-field-wrap">
          <input type="text" class="party-query-date-to" value="${escapeHtml(state.date_to || "")}" placeholder="yyyy/MM/dd">
          <button type="button" class="btn secondary date-pick-btn btn-icon-only" data-party-query-date="to" title="${escapeHtml(t("printDatePickBtn"))}">${uiIcon("view-calendar", 14)}</button>
        </div>
        <label>${escapeHtml(t("partyQueryTxKind"))}</label>
        <div class="party-query-tx-kinds">${kindChecks}</div>
      </div>
      <div class="arap-search-row">
        <label class="search-label">${t("searchLabel")}</label>
        <input type="text" class="party-query-search-input" value="${escapeHtml(state.keyword || "")}">
        ${iconBtn(t("search"), "search", "btn action-btn", 'data-party-query-act="search"')}
        ${iconBtn(t("filter"), "filter", "btn action-btn", 'data-party-query-act="filter"')}
      </div>
      <div class="arap-toolbar-row">
        ${iconBtnOnly(t("navFirst"), "nav-first", "btn nav-btn", `data-party-query-line-nav="first"${disLineFirst ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navPrev"), "nav-prev", "btn nav-btn", `data-party-query-line-nav="prev"${disLinePrev ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navNext"), "nav-next", "btn nav-btn", `data-party-query-line-nav="next"${disLineNext ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navLast"), "nav-last", "btn nav-btn", `data-party-query-line-nav="last"${disLineLast ? " disabled" : ""}`)}
        <span class="arap-record-nav">${escapeHtml(lineNav)}</span>
        ${iconBtn(t("exit"), "exit", "btn action-btn", 'data-party-query-act="exit"')}
      </div>
      <div class="arap-grid-block arap-grid-15-rows">
        <div class="arap-table-scroll">
          <table class="arap-table arap-table-main party-query-table">
            <thead><tr>${head}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
      <div class="party-query-footer">
        <div class="party-query-foot-line">${escapeHtml(t("partyQueryInvTotals"))}：
          ${escapeHtml(t("partyQueryAmt"))} ${escapeHtml(totals.inv_amt || "0.00")}　
          ${escapeHtml(t("partyQueryColPaid"))} ${escapeHtml(totals.inv_paid_amt || "0.00")}　
          ${escapeHtml(t("partyQueryColRecv"))} ${escapeHtml(totals.inv_recv_amt || "0.00")}　
          ${escapeHtml(t("partyQuerySettledTotal"))} ${escapeHtml(totals.inv_settle_amt || "0.00")}
        </div>
        <div class="party-query-foot-line">${escapeHtml(t("partyQueryPurTotals"))}：
          ${escapeHtml(t("partyQueryAmt"))} ${escapeHtml(totals.pur_amt || "0.00")}　
          ${escapeHtml(t("partyQueryColPaid"))} ${escapeHtml(totals.pur_paid_amt || "0.00")}　
          ${escapeHtml(t("partyQueryPayAmt"))} ${escapeHtml(totals.pur_pay_amt || "0.00")}　
          ${escapeHtml(t("partyQuerySettledTotal"))} ${escapeHtml(totals.pur_settle_amt || "0.00")}
        </div>
      </div>`;
  }

  function refreshPartyQueryModalBody(tab) {
    const overlay = partyQueryHost();
    if (!overlay || !partyQueryModalState) return;
    const body = partyQueryBodyHost(overlay);
    if (!body) return;
    body.innerHTML = renderPartyQueryModalBody(partyQueryModalState);
    bindPartyQueryModalEvents(tab);
  }

  async function reloadPartyQueryFromServer(tab, partyIndex, opts = {}) {
    const partyKey = String(opts.partyKey || "").trim();
    const oldRow =
      tab.selectedRow != null && tab.physicalRows[tab.selectedRow]
        ? tab.physicalRows[tab.selectedRow]
        : [];
    const overlay = partyQueryHost();
    let dateFrom = overlay?.querySelector(".party-query-date-from")?.value?.trim() || "";
    let dateTo = overlay?.querySelector(".party-query-date-to")?.value?.trim() || "";
    dateFrom = normalizePartyQueryDateText(dateFrom);
    dateTo = normalizePartyQueryDateText(dateTo);
    const checkedEls = overlay
      ? Array.from(overlay.querySelectorAll(".party-query-tx-kind:checked"))
      : null;
    const txKinds = checkedEls
      ? checkedEls.map((el) => el.value)
      : partyQueryModalState.tx_kinds || ["INV", "REC", "PUR", "PAY"];
    const body = {
      old_row: oldRow,
      party_index: partyIndex,
      date_from: dateFrom,
      date_to: dateTo,
      tx_kinds: txKinds,
    };
    if (partyKey) body.party_key = partyKey;
    const data = await api(`/work/${encodeURIComponent(tab.doProc)}/party-query/load`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    partyQueryModalState.mode = data.mode;
    partyQueryModalState.parties = data.parties || [];
    partyQueryModalState.party_index = data.party_index ?? 0;
    partyQueryModalState.party = data.party || {};
    partyQueryModalState.allLines = JSON.parse(JSON.stringify(data.lines || []));
    partyQueryModalState.date_from = data.date_from || dateFrom;
    partyQueryModalState.date_to = data.date_to || dateTo;
    partyQueryModalState.tx_kinds = Array.isArray(data.tx_kinds) ? data.tx_kinds : txKinds;
    partyQueryModalState.filterKeyword = partyQueryModalState.filterKeyword || "";
    const kw = overlay?.querySelector(".party-query-search-input")?.value?.trim() || "";
    partyQueryModalState.keyword = kw;
    partyQueryModalState.lines = partyQueryFilterLines(
      partyQueryModalState.allLines,
      partyQueryModalState.filterKeyword
    );
    partyQueryModalState.totals = data.totals || partyQueryTotals(partyQueryModalState.lines);
    partyQueryModalState.selectedRow = partyQueryModalState.lines.length ? 0 : null;
    renderTabs();
    refreshPartyQueryModalBody(tab);
  }

  function schedulePartyQueryReload(tab) {
    if (!partyQueryModalState) return;
    clearTimeout(partyQueryModalState._reloadTimer);
    partyQueryModalState._reloadTimer = setTimeout(() => {
      reloadPartyQueryFromServer(tab, partyQueryModalState.party_index ?? 0).catch((e) =>
        showAlert(e.message || t("otherNotConfigured"))
      );
    }, 250);
  }

  function bindPartyQueryModalEvents(tab) {
    const overlay = partyQueryHost();
    if (!overlay || !partyQueryModalState) return;
    overlay.querySelectorAll("[data-party-query-party-nav]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (btn.disabled) return;
        const act = btn.getAttribute("data-party-query-party-nav");
        const total = (partyQueryModalState.parties || []).length;
        let idx = partyQueryModalState.party_index ?? 0;
        if (act === "first") idx = 0;
        else if (act === "prev") idx = Math.max(0, idx - 1);
        else if (act === "next") idx = Math.min(total - 1, idx + 1);
        else if (act === "last") idx = Math.max(0, total - 1);
        try {
          await reloadPartyQueryFromServer(tab, idx);
        } catch (e) {
          showAlert(e.message || t("otherNotConfigured"));
        }
      });
    });
    overlay.querySelectorAll("[data-party-query-line-nav]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        const act = btn.getAttribute("data-party-query-line-nav");
        const n = partyQueryModalState.lines.length;
        if (n <= 0) return;
        let r = partyQueryModalState.selectedRow ?? 0;
        if (act === "first") r = 0;
        else if (act === "prev") r = Math.max(0, r - 1);
        else if (act === "next") r = Math.min(n - 1, r + 1);
        else if (act === "last") r = n - 1;
        partyQueryModalState.selectedRow = r;
        refreshPartyQueryModalBody(tab);
      });
    });
    overlay.querySelectorAll(".party-query-row").forEach((tr) => {
      tr.addEventListener("click", () => {
        const ri = parseInt(tr.getAttribute("data-party-query-row"), 10);
        if (!Number.isNaN(ri)) {
          partyQueryModalState.selectedRow = ri;
          refreshPartyQueryModalBody(tab);
        }
      });
    });
    const dateFrom = overlay.querySelector(".party-query-date-from");
    const dateTo = overlay.querySelector(".party-query-date-to");
    const onDateBlur = (inp) => {
      if (!inp) return;
      const n = normalizePartyQueryDateText(inp.value);
      if (n !== inp.value.trim()) inp.value = n;
      schedulePartyQueryReload(tab);
    };
    dateFrom?.addEventListener("change", () => onDateBlur(dateFrom));
    dateTo?.addEventListener("change", () => onDateBlur(dateTo));
    dateFrom?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onDateBlur(dateFrom);
      }
    });
    dateTo?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onDateBlur(dateTo);
      }
    });
    overlay.querySelectorAll(".party-query-tx-kind").forEach((cb) => {
      cb.addEventListener("change", () => schedulePartyQueryReload(tab));
    });
    overlay.querySelectorAll("[data-party-query-date]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const which = btn.getAttribute("data-party-query-date");
        const inp = which === "to" ? dateTo : dateFrom;
        if (!inp) return;
        // 用原生 date input 暫存選擇
        const picker = document.createElement("input");
        picker.type = "date";
        picker.style.position = "fixed";
        picker.style.left = "-9999px";
        document.body.appendChild(picker);
        const cur = normalizePartyQueryDateText(inp.value);
        if (/^\d{4}\/\d{2}\/\d{2}$/.test(cur)) {
          picker.value = cur.replace(/\//g, "-");
        }
        picker.addEventListener("change", () => {
          if (picker.value) {
            const [y, m, d] = picker.value.split("-");
            inp.value = `${y}/${m}/${d}`;
          } else {
            inp.value = "";
          }
          picker.remove();
          schedulePartyQueryReload(tab);
        });
        picker.showPicker?.();
        picker.click();
      });
    });
    overlay.querySelectorAll("[data-party-query-act]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const act = btn.getAttribute("data-party-query-act");
        if (act === "exit") {
          closePartyQueryModal();
          return;
        }
        if (act === "lookup-party") {
          openPartyKeyLookup(tab).catch((e) => showAlert(e.message || t("otherNotConfigured")));
          return;
        }
        const kw = overlay.querySelector(".party-query-search-input")?.value?.trim() || "";
        partyQueryModalState.keyword = kw;
        if (act === "filter") {
          partyQueryModalState.filterKeyword = kw;
          partyQueryModalState.lines = partyQueryFilterLines(
            partyQueryModalState.allLines,
            kw
          );
          partyQueryModalState.totals = partyQueryTotals(partyQueryModalState.lines);
          partyQueryModalState.selectedRow = partyQueryModalState.lines.length ? 0 : null;
          refreshPartyQueryModalBody(tab);
          return;
        }
        if (act === "search") {
          const idx = partyQueryModalState.allLines.findIndex((ln) => {
            const blob = [
              ln.date,
              ln.tx_category,
              ln.tx_key,
              ln.currency,
              ln.rate,
              ln.inv_amt,
              ln.paid_amt,
              ln.recv_amt,
              ln.settle_amt,
            ]
              .join(" ")
              .toLowerCase();
            return blob.includes(kw.toLowerCase());
          });
          if (idx < 0) {
            showAlert(t("partyQuerySearchMiss"));
            return;
          }
          partyQueryModalState.filterKeyword = "";
          partyQueryModalState.lines = partyQueryModalState.allLines.slice();
          partyQueryModalState.totals = partyQueryTotals(partyQueryModalState.lines);
          partyQueryModalState.selectedRow = idx;
          refreshPartyQueryModalBody(tab);
        }
      });
    });
    const keyInp = overlay.querySelector(".party-query-key-input");
    keyInp?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        gotoPartyKeyFromInput(tab, keyInp.value);
      }
    });
    keyInp?.addEventListener("change", () => gotoPartyKeyFromInput(tab, keyInp.value));
  }

  function gotoPartyKeyFromInput(tab, rawKey) {
    const key = String(rawKey || "").trim().toUpperCase();
    if (!key || !partyQueryModalState) return;
    const parties = partyQueryModalState.parties || [];
    const idx = parties.findIndex(
      (p) => String(p.key || "").trim().toUpperCase() === key
    );
    if (idx < 0) {
      showAlert(
        stateLangIsChn()
          ? "找不到此顧客-供應商編號。"
          : "Customer/Vendor not found."
      );
      refreshPartyQueryModalBody(tab);
      return;
    }
    reloadPartyQueryFromServer(tab, idx).catch((e) =>
      showAlert(e.message || t("otherNotConfigured"))
    );
  }

  function partyPhysicalMatchesMode(physicalFields, physicalRow, mode) {
    const up = (physicalFields || []).map((f) => String(f || "").trim().toUpperCase());
    const flags =
      mode === "AP"
        ? ["IS_VEND", "IS_VENDOR", "VENDOR", "SUPPLIER"]
        : ["IS_CUST", "IS_CUSTOMER", "CUSTOMER"];
    for (const flag of flags) {
      const i = up.indexOf(flag);
      if (i < 0) continue;
      const v = String(physicalRow?.[i] || "")
        .trim()
        .toUpperCase();
      if (!v) return false;
      if (["Y", "YES", "1", "T", "TRUE", "X"].includes(v)) return true;
      if (["N", "NO", "0", "F", "FALSE"].includes(v)) return false;
      return Boolean(v);
    }
    const ti = up.indexOf("TYPE");
    if (ti >= 0) {
      const typ = String(physicalRow?.[ti] || "")
        .trim()
        .toUpperCase();
      if (typ) {
        if (mode === "AP") {
          return (
            ["V", "VE", "VEND", "VENDOR", "SUP", "SUPPLIER", "CV", "B", "BOTH"].includes(typ) ||
            typ.startsWith("V") ||
            typ === "CV"
          );
        }
        return (
          ["C", "CU", "CUST", "CUSTOMER", "CV", "B", "BOTH"].includes(typ) || typ.startsWith("C")
        );
      }
    }
    const keyNames =
      mode === "AP"
        ? ["VEND_KEY", "VEND_CODE", "CUST_KEY", "CV_KEY", "KEY"]
        : ["CUST_KEY", "CUST_CODE", "CV_KEY", "KEY"];
    for (const kn of keyNames) {
      const i = up.indexOf(kn);
      if (i >= 0 && String(physicalRow?.[i] || "").trim()) return true;
    }
    return mode !== "AP";
  }

  async function openPartyKeyLookup(tab) {
    if (!tab?.doProc || !partyQueryModalState) return;
    let data;
    try {
      data = await api(`/work/${encodeURIComponent(tab.doProc)}/lookup/rows`, {
        method: "POST",
        body: JSON.stringify({ lookup_db: "CUSTVEND", keyword: "", as_filter: false }),
      });
    } catch (e) {
      showAlert(e.message || t("otherNotConfigured"));
      return;
    }
    const mode = partyQueryModalState.mode || "AR";
    const physicalFields = data.physical_fields || data.fields || [];
    const physicalRows = (data.physical_rows || []).filter((r) =>
      partyPhysicalMatchesMode(physicalFields, r, mode)
    );
    const fields = data.fields || [];
    const physIdx = fields.map((f) => {
      const u = String(f || "").trim().toUpperCase();
      return physicalFields.findIndex((p) => String(p || "").trim().toUpperCase() === u);
    });
    const rows = physicalRows.map((pr) =>
      physIdx.map((i) => (i >= 0 && i < pr.length ? pr[i] : ""))
    );
    const retCandidates =
      mode === "AP"
        ? ["VEND_KEY", "CV_KEY", "CUST_KEY", "KEY"]
        : ["CUST_KEY", "CV_KEY", "VEND_KEY", "KEY"];
    let retField = retCandidates[0];
    for (const c of retCandidates) {
      if (physicalFields.some((p) => String(p || "").trim().toUpperCase() === c)) {
        retField = c;
        break;
      }
    }
    await openQueryMasterLookup(tab, {
      title: `CUSTVEND`,
      fields,
      columns: data.columns || {},
      rows,
      physical_fields: physicalFields,
      physical_rows: physicalRows,
      retField,
      onPick: (key) => gotoPartyKeyFromInput(tab, key),
    });
  }

  async function openPartyQueryModal(tab, opts = {}) {
    const partyKey = String(opts.partyKey || opts.key || opts.keyword || "").trim();
    const id = queryTabId("party", tab.id);
    const existing = openTabs.find((x) => x.id === id);
    if (existing) {
      partyQueryModalState = existing;
      activeTabId = id;
      renderTabs();
      if (partyKey) {
        const parties = existing.parties || [];
        const idx = parties.findIndex(
          (p) => String(p.key || "").trim().toUpperCase() === partyKey.toUpperCase()
        );
        if (idx < 0) {
          try {
            await reloadPartyQueryFromServer(tab, -1, { partyKey });
          } catch (e) {
            renderTabs();
            showAlert(e.message || t("otherNotConfigured"));
            return;
          }
          return;
        }
        try {
          await reloadPartyQueryFromServer(tab, idx);
        } catch (e) {
          renderTabs();
          showAlert(e.message || t("otherNotConfigured"));
        }
      } else {
        try {
          await reloadPartyQueryFromServer(tab, existing.party_index ?? 0);
        } catch (e) {
          renderTabs();
          showAlert(e.message || t("otherNotConfigured"));
        }
      }
      return;
    }
    const oldRow =
      tab.selectedRow != null && tab.physicalRows[tab.selectedRow]
        ? tab.physicalRows[tab.selectedRow]
        : [];
    try {
      const data = await api(`/work/${encodeURIComponent(tab.doProc)}/party-query/load`, {
        method: "POST",
        body: JSON.stringify({
          old_row: oldRow,
          party_index: -1,
          party_key: partyKey,
          date_from: "",
          date_to: "",
          tx_kinds: ["INV", "REC", "PUR", "PAY"],
        }),
      });
      const title = partyQueryTitle(data.mode);
      partyQueryModalState = {
        type: "party-query",
        id,
        parentWorkId: tab.id,
        doProc: tab.doProc,
        title,
        menuTitle: title,
        tab,
        mode: data.mode,
        parties: data.parties || [],
        party_index: data.party_index ?? 0,
        party: data.party || {},
        allLines: JSON.parse(JSON.stringify(data.lines || [])),
        lines: data.lines || [],
        totals: data.totals || partyQueryTotals(data.lines || []),
        date_from: data.date_from || "",
        date_to: data.date_to || "",
        tx_kinds: data.tx_kinds || ["INV", "REC", "PUR", "PAY"],
        keyword: "",
        filterKeyword: "",
        selectedRow: (data.lines || []).length ? 0 : null,
      };
      openTabs.push(partyQueryModalState);
      activeTabId = id;
      renderTabs();
    } catch (e) {
      showAlert(e.message || t("otherNotConfigured"));
    }
  }

  const STOCK_QUERY_GRID_VISIBLE_ROWS = 15;

  function stockQueryHost() {
    return (
      document.querySelector('.query-page[data-query-kind="stock"]') ||
      $("#stock-query-modal-overlay")
    );
  }

  function stockQueryBodyHost(root) {
    if (!root) return null;
    if (root.classList.contains("query-page")) {
      return root.querySelector(".query-page-body") || root;
    }
    return root.querySelector(".arap-modal-body");
  }

  function closeStockQueryModal() {
    const id = stockQueryModalState && stockQueryModalState.id;
    stockQueryModalState = null;
    const el = $("#stock-query-modal-overlay");
    if (el) el.remove();
    if (id && openTabs.some((x) => x.id === id)) closeTab(id);
  }

  function stockQueryColHeaders() {
    return [
      t("stockQueryColDate"),
      t("stockQueryColType"),
      t("stockQueryColKey"),
      t("stockQueryColQty"),
      t("stockQueryColUnit"),
      t("stockQueryColWeight"),
      t("stockQueryColWgtUnit"),
      t("stockQueryColWh"),
      t("stockQueryColPrice"),
      t("stockQueryColAmt"),
      t("stockQueryColUnitCost"),
      t("stockQueryColCostAmt"),
    ];
  }

  function stockQueryColAlign(colName) {
    return ["qty", "weight", "unit_price", "amount", "unit_cost", "cost_amt"].includes(colName)
      ? "num-field"
      : "";
  }

  function stockQueryFilterLines(lines, keyword) {
    const kw = String(keyword || "").trim().toLowerCase();
    if (!kw) return lines.slice();
    return lines.filter((ln) => {
      const blob = [
        ln.date,
        ln.tx_category,
        ln.tx_key,
        ln.qty,
        ln.unit,
        ln.weight,
        ln.wgt_unit,
        ln.warehouse,
        ln.unit_price,
        ln.amount,
        ln.unit_cost,
        ln.cost_amt,
      ]
        .join(" ")
        .toLowerCase();
      return blob.includes(kw);
    });
  }

  function stockQueryTotals(lines) {
    const sumGroup = (cat, k) =>
      lines
        .filter((ln) => String(ln.tx_category || "").toUpperCase() === cat)
        .reduce((a, ln) => a + (parseFloat(String(ln[k] || "0").replace(/,/g, "")) || 0), 0);
    const pack = (cat, prefix) => ({
      [`${prefix}_qty`]: queryFormatInt(sumGroup(cat, "qty")),
      [`${prefix}_weight`]: queryFormatInt(sumGroup(cat, "weight")),
      [`${prefix}_amt`]: arapFormatAmt2(sumGroup(cat, "amount")),
    });
    return {
      ...pack("PUR", "pur"),
      ...pack("INV", "inv"),
      ...pack("ADJ", "adj"),
      ...pack("TRI", "tri"),
    };
  }

  function renderStockQueryModalBody(state) {
    const stock = state.stock || {};
    const lines = state.lines || [];
    const totals = state.totals || stockQueryTotals(lines);
    const headers = stockQueryColHeaders();
    const colKeys = [
      "date",
      "tx_category",
      "tx_key",
      "qty",
      "unit",
      "weight",
      "wgt_unit",
      "warehouse",
      "unit_price",
      "amount",
      "unit_cost",
      "cost_amt",
    ];
    const stockTotal = (state.stocks || []).length;
    const stockCur = stockTotal ? state.stock_index + 1 : null;
    const stockNav = formatRecordNavLabel(stockTotal, stockCur);
    const lineCur =
      state.selectedRow != null && state.selectedRow >= 0 && state.selectedRow < lines.length
        ? state.selectedRow + 1
        : null;
    const lineNav = formatRecordNavLabel(lines.length, lineCur);
    const disStockFirst = !stockTotal || (stockCur != null && stockCur <= 1);
    const disStockPrev = !stockTotal || stockCur == null || stockCur <= 1;
    const disStockNext = !stockTotal || stockCur == null || stockCur >= stockTotal;
    const disStockLast = !stockTotal || (stockCur != null && stockCur >= stockTotal);
    const disLineFirst = !lines.length || (lineCur != null && lineCur <= 1);
    const disLinePrev = !lines.length || lineCur == null || lineCur <= 1;
    const disLineNext = !lines.length || lineCur == null || lineCur >= lines.length;
    const disLineLast = !lines.length || (lineCur != null && lineCur >= lines.length);
    const selectedKinds = new Set(
      (Array.isArray(state.tx_kinds) ? state.tx_kinds : ["PUR", "INV", "ADJ", "TRI"]).map(
        (k) => String(k || "").toUpperCase()
      )
    );
    const kindChecks = [
      ["PUR", t("stockQueryKindPur")],
      ["INV", t("stockQueryKindInv")],
      ["ADJ", t("stockQueryKindAdj")],
      ["TRI", t("stockQueryKindTri")],
    ]
      .map(
        ([v, label]) =>
          `<label class="party-query-kind-check"><input type="checkbox" class="stock-query-tx-kind" value="${v}"${
            selectedKinds.has(v) ? " checked" : ""
          }> ${escapeHtml(label)}</label>`
      )
      .join("");
    let rows = lines
      .map((ln, ri) => {
        const sel = state.selectedRow === ri ? " selected" : "";
        const alt = ri % 2 === 1 ? " arap-row-alt" : "";
        const cells = colKeys
          .map((c) => {
            let v = ln[c] || "";
            if (c === "date") v = arapFormatDate(v);
            else if (["qty", "weight"].includes(c)) v = queryFormatInt(v);
            else if (["unit_price", "amount", "unit_cost", "cost_amt"].includes(c)) {
              v = arapFormatAmt2(v);
            }
            const cls = stockQueryColAlign(c);
            return `<td class="${cls}">${escapeHtml(v)}</td>`;
          })
          .join("");
        return `<tr class="arap-row stock-query-row${sel}${alt}" data-stock-query-row="${ri}">${cells}</tr>`;
      })
      .join("");
    const emptyCells = headers
      .map((h, i) => `<td class="arap-pad-cell ${stockQueryColAlign(colKeys[i])}"></td>`)
      .join("");
    const padCount = Math.max(0, STOCK_QUERY_GRID_VISIBLE_ROWS - lines.length);
    for (let i = 0; i < padCount; i++) {
      const alt = (lines.length + i) % 2 === 1 ? " arap-row-alt" : "";
      rows += `<tr class="arap-row-pad${alt}" aria-hidden="true">${emptyCells}</tr>`;
    }
    const head = headers
      .map((h, i) => `<th class="${stockQueryColAlign(colKeys[i])}">${escapeHtml(h)}</th>`)
      .join("");
    const footLine = (labelKey, prefix) =>
      `<div class="party-query-foot-line">${escapeHtml(t(labelKey))}：
          ${escapeHtml(t("stockQueryQty"))} ${escapeHtml(totals[prefix + "_qty"] || "0.00")}　
          ${escapeHtml(t("stockQueryWeight"))} ${escapeHtml(totals[prefix + "_weight"] || "0.00")}　
          ${escapeHtml(t("stockQueryAmt"))} ${escapeHtml(totals[prefix + "_amt"] || "0.00")}
        </div>`;
    return `
      <div class="arap-header-grid party-query-header-grid party-query-header-left">
        <div class="arap-header-field"><label>${escapeHtml(t("stockQueryNo"))}</label>
          <div class="lookup-field-wrap">
            <input type="text" class="stock-query-key-input" value="${escapeHtml(stock.key || "")}">
            <button type="button" class="btn secondary lookup-btn" data-stock-query-act="lookup-stock" title="${escapeHtml(t("lookup"))}" aria-label="${escapeHtml(t("lookup"))}">…</button>
          </div>
        </div>
        <div class="arap-header-field"><label>${escapeHtml(t("stockQueryCat"))}</label><input readonly value="${escapeHtml(stock.category || "")}"></div>
        <div class="arap-header-field"><label>${escapeHtml(t("stockQueryBrand"))}</label><input readonly value="${escapeHtml(stock.brand || "")}"></div>
        <div class="arap-header-field"><label>${escapeHtml(t("stockQueryModel"))}</label><input readonly value="${escapeHtml(stock.model || "")}"></div>
        <div class="arap-header-field"><label>${escapeHtml(t("stockQueryDesc"))}</label><input readonly value="${escapeHtml(stock.desc || "")}"></div>
        <div class="arap-header-field party-query-header-spacer"></div>
      </div>
      <div class="arap-toolbar-row party-query-party-nav">
        ${iconBtnOnly(t("navFirst"), "nav-first", "btn nav-btn", `data-stock-query-stock-nav="first"${disStockFirst ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navPrev"), "nav-prev", "btn nav-btn", `data-stock-query-stock-nav="prev"${disStockPrev ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navNext"), "nav-next", "btn nav-btn", `data-stock-query-stock-nav="next"${disStockNext ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navLast"), "nav-last", "btn nav-btn", `data-stock-query-stock-nav="last"${disStockLast ? " disabled" : ""}`)}
        <span class="arap-record-nav">${escapeHtml(stockNav)}</span>
      </div>
      <div class="party-query-date-row">
        <label>${escapeHtml(t("partyQueryDateFrom"))}</label>
        <div class="date-field-wrap">
          <input type="text" class="stock-query-date-from" value="${escapeHtml(state.date_from || "")}" placeholder="yyyy/MM/dd">
          <button type="button" class="btn secondary date-pick-btn btn-icon-only" data-stock-query-date="from" title="${escapeHtml(t("printDatePickBtn"))}">${uiIcon("view-calendar", 14)}</button>
        </div>
        <label>${escapeHtml(t("partyQueryDateTo"))}</label>
        <div class="date-field-wrap">
          <input type="text" class="stock-query-date-to" value="${escapeHtml(state.date_to || "")}" placeholder="yyyy/MM/dd">
          <button type="button" class="btn secondary date-pick-btn btn-icon-only" data-stock-query-date="to" title="${escapeHtml(t("printDatePickBtn"))}">${uiIcon("view-calendar", 14)}</button>
        </div>
        <label>${escapeHtml(t("stockQueryTxKind"))}</label>
        <div class="party-query-tx-kinds">${kindChecks}</div>
      </div>
      <div class="arap-search-row">
        <label class="search-label">${t("searchLabel")}</label>
        <input type="text" class="stock-query-search-input" value="${escapeHtml(state.keyword || "")}">
        ${iconBtn(t("search"), "search", "btn action-btn", 'data-stock-query-act="search"')}
        ${iconBtn(t("filter"), "filter", "btn action-btn", 'data-stock-query-act="filter"')}
      </div>
      <div class="arap-toolbar-row">
        ${iconBtnOnly(t("navFirst"), "nav-first", "btn nav-btn", `data-stock-query-line-nav="first"${disLineFirst ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navPrev"), "nav-prev", "btn nav-btn", `data-stock-query-line-nav="prev"${disLinePrev ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navNext"), "nav-next", "btn nav-btn", `data-stock-query-line-nav="next"${disLineNext ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navLast"), "nav-last", "btn nav-btn", `data-stock-query-line-nav="last"${disLineLast ? " disabled" : ""}`)}
        <span class="arap-record-nav">${escapeHtml(lineNav)}</span>
        ${iconBtn(t("exit"), "exit", "btn action-btn", 'data-stock-query-act="exit"')}
      </div>
      <div class="arap-grid-block arap-grid-15-rows">
        <div class="arap-table-scroll">
          <table class="arap-table arap-table-main party-query-table stock-query-table">
            <thead><tr>${head}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
      <div class="party-query-footer">
        ${footLine("stockQueryPurTotals", "pur")}
        ${footLine("stockQueryInvTotals", "inv")}
        ${footLine("stockQueryAdjTotals", "adj")}
        ${footLine("stockQueryTriTotals", "tri")}
      </div>`;
  }

  function refreshStockQueryModalBody(tab) {
    const overlay = stockQueryHost();
    if (!overlay || !stockQueryModalState) return;
    const body = stockQueryBodyHost(overlay);
    if (!body) return;
    body.innerHTML = renderStockQueryModalBody(stockQueryModalState);
    bindStockQueryModalEvents(tab);
  }

  async function reloadStockQueryFromServer(tab, stockIndex, opts = {}) {
    const stockKey = String(opts.stockKey || "").trim();
    const oldRow =
      tab.selectedRow != null && tab.physicalRows[tab.selectedRow]
        ? tab.physicalRows[tab.selectedRow]
        : [];
    const overlay = stockQueryHost();
    let dateFrom = overlay?.querySelector(".stock-query-date-from")?.value?.trim() || "";
    let dateTo = overlay?.querySelector(".stock-query-date-to")?.value?.trim() || "";
    dateFrom = normalizePartyQueryDateText(dateFrom);
    dateTo = normalizePartyQueryDateText(dateTo);
    const checkedEls = overlay
      ? Array.from(overlay.querySelectorAll(".stock-query-tx-kind:checked"))
      : null;
    const txKinds = checkedEls
      ? checkedEls.map((el) => el.value)
      : stockQueryModalState.tx_kinds || ["PUR", "INV", "ADJ", "TRI"];
    const body = {
      old_row: oldRow,
      stock_index: stockIndex,
      date_from: dateFrom,
      date_to: dateTo,
      tx_kinds: txKinds,
    };
    if (stockKey) body.stock_key = stockKey;
    const data = await api(`/work/${encodeURIComponent(tab.doProc)}/stock-query/load`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    stockQueryModalState.stocks = data.stocks || [];
    stockQueryModalState.stock_index = data.stock_index ?? 0;
    stockQueryModalState.stock = data.stock || {};
    stockQueryModalState.allLines = JSON.parse(JSON.stringify(data.lines || []));
    stockQueryModalState.date_from = data.date_from || dateFrom;
    stockQueryModalState.date_to = data.date_to || dateTo;
    stockQueryModalState.tx_kinds = Array.isArray(data.tx_kinds) ? data.tx_kinds : txKinds;
    stockQueryModalState.filterKeyword = stockQueryModalState.filterKeyword || "";
    const kw = overlay?.querySelector(".stock-query-search-input")?.value?.trim() || "";
    stockQueryModalState.keyword = kw;
    stockQueryModalState.lines = stockQueryFilterLines(
      stockQueryModalState.allLines,
      stockQueryModalState.filterKeyword
    );
    stockQueryModalState.totals = data.totals || stockQueryTotals(stockQueryModalState.lines);
    stockQueryModalState.selectedRow = stockQueryModalState.lines.length ? 0 : null;
    renderTabs();
    refreshStockQueryModalBody(tab);
  }

  function scheduleStockQueryReload(tab) {
    if (!stockQueryModalState) return;
    clearTimeout(stockQueryModalState._reloadTimer);
    stockQueryModalState._reloadTimer = setTimeout(() => {
      reloadStockQueryFromServer(tab, stockQueryModalState.stock_index ?? 0).catch((e) =>
        showAlert(e.message || t("otherNotConfigured"))
      );
    }, 250);
  }

  function bindStockQueryModalEvents(tab) {
    const overlay = stockQueryHost();
    if (!overlay || !stockQueryModalState) return;
    overlay.querySelectorAll("[data-stock-query-stock-nav]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (btn.disabled) return;
        const act = btn.getAttribute("data-stock-query-stock-nav");
        const total = (stockQueryModalState.stocks || []).length;
        let idx = stockQueryModalState.stock_index ?? 0;
        if (act === "first") idx = 0;
        else if (act === "prev") idx = Math.max(0, idx - 1);
        else if (act === "next") idx = Math.min(total - 1, idx + 1);
        else if (act === "last") idx = Math.max(0, total - 1);
        try {
          await reloadStockQueryFromServer(tab, idx);
        } catch (e) {
          showAlert(e.message || t("otherNotConfigured"));
        }
      });
    });
    overlay.querySelectorAll("[data-stock-query-line-nav]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        const act = btn.getAttribute("data-stock-query-line-nav");
        const n = stockQueryModalState.lines.length;
        if (n <= 0) return;
        let r = stockQueryModalState.selectedRow ?? 0;
        if (act === "first") r = 0;
        else if (act === "prev") r = Math.max(0, r - 1);
        else if (act === "next") r = Math.min(n - 1, r + 1);
        else if (act === "last") r = n - 1;
        stockQueryModalState.selectedRow = r;
        refreshStockQueryModalBody(tab);
      });
    });
    overlay.querySelectorAll(".stock-query-row").forEach((tr) => {
      tr.addEventListener("click", () => {
        const ri = parseInt(tr.getAttribute("data-stock-query-row"), 10);
        if (!Number.isNaN(ri)) {
          stockQueryModalState.selectedRow = ri;
          refreshStockQueryModalBody(tab);
        }
      });
    });
    const dateFrom = overlay.querySelector(".stock-query-date-from");
    const dateTo = overlay.querySelector(".stock-query-date-to");
    const onDateBlur = (inp) => {
      if (!inp) return;
      const n = normalizePartyQueryDateText(inp.value);
      if (n !== inp.value.trim()) inp.value = n;
      scheduleStockQueryReload(tab);
    };
    dateFrom?.addEventListener("change", () => onDateBlur(dateFrom));
    dateTo?.addEventListener("change", () => onDateBlur(dateTo));
    dateFrom?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onDateBlur(dateFrom);
      }
    });
    dateTo?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onDateBlur(dateTo);
      }
    });
    overlay.querySelectorAll(".stock-query-tx-kind").forEach((cb) => {
      cb.addEventListener("change", () => scheduleStockQueryReload(tab));
    });
    overlay.querySelectorAll("[data-stock-query-date]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const which = btn.getAttribute("data-stock-query-date");
        const inp = which === "to" ? dateTo : dateFrom;
        if (!inp) return;
        const picker = document.createElement("input");
        picker.type = "date";
        picker.style.position = "fixed";
        picker.style.left = "-9999px";
        document.body.appendChild(picker);
        const cur = normalizePartyQueryDateText(inp.value);
        if (/^\d{4}\/\d{2}\/\d{2}$/.test(cur)) {
          picker.value = cur.replace(/\//g, "-");
        }
        picker.addEventListener("change", () => {
          if (picker.value) {
            const [y, m, d] = picker.value.split("-");
            inp.value = `${y}/${m}/${d}`;
          } else {
            inp.value = "";
          }
          picker.remove();
          scheduleStockQueryReload(tab);
        });
        picker.showPicker?.();
        picker.click();
      });
    });
    overlay.querySelectorAll("[data-stock-query-act]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const act = btn.getAttribute("data-stock-query-act");
        if (act === "exit") {
          closeStockQueryModal();
          return;
        }
        if (act === "lookup-stock") {
          openStockKeyLookup(tab).catch((e) => showAlert(e.message || t("otherNotConfigured")));
          return;
        }
        const kw =
          overlay.querySelector(".stock-query-search-input")?.value?.trim() || "";
        stockQueryModalState.keyword = kw;
        if (act === "filter") {
          stockQueryModalState.filterKeyword = kw;
          stockQueryModalState.lines = stockQueryFilterLines(
            stockQueryModalState.allLines,
            kw
          );
          stockQueryModalState.totals = stockQueryTotals(stockQueryModalState.lines);
          stockQueryModalState.selectedRow = stockQueryModalState.lines.length ? 0 : null;
          refreshStockQueryModalBody(tab);
        } else if (act === "search") {
          const idx = stockQueryModalState.allLines.findIndex((ln) => {
            const blob = [
              ln.date,
              ln.tx_category,
              ln.tx_key,
              ln.qty,
              ln.unit,
              ln.weight,
              ln.wgt_unit,
              ln.warehouse,
              ln.unit_price,
              ln.amount,
              ln.unit_cost,
              ln.cost_amt,
            ]
              .join(" ")
              .toLowerCase();
            return blob.includes(kw.toLowerCase());
          });
          if (idx < 0) {
            showAlert(t("partyQuerySearchMiss"));
            return;
          }
          stockQueryModalState.filterKeyword = "";
          stockQueryModalState.lines = stockQueryModalState.allLines.slice();
          stockQueryModalState.totals = stockQueryTotals(stockQueryModalState.lines);
          stockQueryModalState.selectedRow = idx;
          refreshStockQueryModalBody(tab);
        }
      });
    });
    const keyInp = overlay.querySelector(".stock-query-key-input");
    keyInp?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        gotoStockKeyFromInput(tab, keyInp.value);
      }
    });
    keyInp?.addEventListener("change", () => gotoStockKeyFromInput(tab, keyInp.value));
  }

  function gotoStockKeyFromInput(tab, rawKey) {
    const key = String(rawKey || "").trim().toUpperCase();
    if (!key || !stockQueryModalState) return;
    const stocks = stockQueryModalState.stocks || [];
    const idx = stocks.findIndex(
      (s) => String(s.key || "").trim().toUpperCase() === key
    );
    if (idx < 0) {
      showAlert(stateLangIsChn() ? "找不到此存貨編號。" : "Stock not found.");
      refreshStockQueryModalBody(tab);
      return;
    }
    reloadStockQueryFromServer(tab, idx).catch((e) =>
      showAlert(e.message || t("otherNotConfigured"))
    );
  }

  async function openStockKeyLookup(tab) {
    if (!tab?.doProc || !stockQueryModalState) return;
    let data;
    try {
      data = await api(`/work/${encodeURIComponent(tab.doProc)}/lookup/rows`, {
        method: "POST",
        body: JSON.stringify({ lookup_db: "STOCK", keyword: "", as_filter: false }),
      });
    } catch (e) {
      showAlert(e.message || t("otherNotConfigured"));
      return;
    }
    const physicalFields = data.physical_fields || data.fields || [];
    const physicalRows = data.physical_rows || [];
    const fields = data.fields || [];
    const physIdx = fields.map((f) => {
      const u = String(f || "").trim().toUpperCase();
      return physicalFields.findIndex((p) => String(p || "").trim().toUpperCase() === u);
    });
    const rows = physicalRows.map((pr) =>
      physIdx.map((i) => (i >= 0 && i < pr.length ? pr[i] : ""))
    );
    const retCandidates = ["STK_KEY", "STOCK_KEY", "ITEM_KEY", "KEY"];
    let retField = "STK_KEY";
    for (const c of retCandidates) {
      if (physicalFields.some((p) => String(p || "").trim().toUpperCase() === c)) {
        retField = c;
        break;
      }
    }
    await openQueryMasterLookup(tab, {
      title: "STOCK",
      fields,
      columns: data.columns || {},
      rows,
      physical_fields: physicalFields,
      physical_rows: physicalRows,
      retField,
      onPick: (key) => gotoStockKeyFromInput(tab, key),
    });
  }

  async function openStockQueryModal(tab, opts = {}) {
    const stockKey = String(opts.stockKey || opts.key || opts.keyword || "").trim();
    const id = queryTabId("stock", tab.id);
    const existing = openTabs.find((x) => x.id === id);
    if (existing) {
      stockQueryModalState = existing;
      activeTabId = id;
      renderTabs();
      if (stockKey) {
        const stocks = existing.stocks || [];
        const idx = stocks.findIndex(
          (s) => String(s.key || "").trim().toUpperCase() === stockKey.toUpperCase()
        );
        if (idx < 0) {
          try {
            await reloadStockQueryFromServer(tab, -1, { stockKey });
          } catch (e) {
            renderTabs();
            showAlert(e.message || t("otherNotConfigured"));
          }
          return;
        }
        try {
          await reloadStockQueryFromServer(tab, idx);
        } catch (e) {
          renderTabs();
          showAlert(e.message || t("otherNotConfigured"));
        }
      } else {
        try {
          await reloadStockQueryFromServer(tab, existing.stock_index ?? 0);
        } catch (e) {
          renderTabs();
          showAlert(e.message || t("otherNotConfigured"));
        }
      }
      return;
    }
    const oldRow =
      tab.selectedRow != null && tab.physicalRows[tab.selectedRow]
        ? tab.physicalRows[tab.selectedRow]
        : [];
    try {
      const data = await api(`/work/${encodeURIComponent(tab.doProc)}/stock-query/load`, {
        method: "POST",
        body: JSON.stringify({
          old_row: oldRow,
          stock_index: -1,
          stock_key: stockKey,
          date_from: "",
          date_to: "",
          tx_kinds: ["PUR", "INV", "ADJ", "TRI"],
        }),
      });
      const title = t("stockQueryTitle");
      stockQueryModalState = {
        type: "stock-query",
        id,
        parentWorkId: tab.id,
        doProc: tab.doProc,
        title,
        menuTitle: title,
        tab,
        stocks: data.stocks || [],
        stock_index: data.stock_index ?? 0,
        stock: data.stock || {},
        allLines: JSON.parse(JSON.stringify(data.lines || [])),
        lines: data.lines || [],
        totals: data.totals || stockQueryTotals(data.lines || []),
        date_from: data.date_from || "",
        date_to: data.date_to || "",
        tx_kinds: data.tx_kinds || ["PUR", "INV", "ADJ", "TRI"],
        keyword: "",
        filterKeyword: "",
        selectedRow: (data.lines || []).length ? 0 : null,
      };
      openTabs.push(stockQueryModalState);
      activeTabId = id;
      renderTabs();
    } catch (e) {
      showAlert(e.message || t("otherNotConfigured"));
    }
  }

  const ACCOUNT_QUERY_GRID_VISIBLE_ROWS = 15;

  function accountQueryHost() {
    return (
      document.querySelector('.query-page[data-query-kind="account"]') ||
      $("#account-query-modal-overlay")
    );
  }

  function accountQueryBodyHost(root) {
    if (!root) return null;
    if (root.classList.contains("query-page")) {
      return root.querySelector(".query-page-body") || root;
    }
    return root.querySelector(".arap-modal-body");
  }

  function closeAccountQueryModal() {
    const id = accountQueryModalState && accountQueryModalState.id;
    accountQueryModalState = null;
    const el = $("#account-query-modal-overlay");
    if (el) el.remove();
    if (id && openTabs.some((x) => x.id === id)) closeTab(id);
  }

  function accountQueryColHeaders() {
    return [
      t("accountQueryColDate"),
      t("accountQueryColVou"),
      t("accountQueryColCurr"),
      t("accountQueryColRate"),
      t("accountQueryColDr"),
      t("accountQueryColCr"),
      t("accountQueryColRemark"),
    ];
  }

  function accountQueryColAlign(colName) {
    return ["rate", "dr_amt", "cr_amt"].includes(colName) ? "num-field" : "";
  }

  function accountQueryFilterLines(lines, keyword) {
    const kw = String(keyword || "").trim().toLowerCase();
    if (!kw) return lines.slice();
    return lines.filter((ln) => {
      const blob = [
        ln.date,
        ln.vou_key,
        ln.currency,
        ln.rate,
        ln.dr_amt,
        ln.cr_amt,
        ln.remark,
      ]
        .join(" ")
        .toLowerCase();
      return blob.includes(kw);
    });
  }

  function accountQueryTotals(lines) {
    const sum = (k) =>
      lines.reduce(
        (a, ln) => a + (parseFloat(String(ln[k] || "0").replace(/,/g, "")) || 0),
        0
      );
    return {
      dr_amt: arapFormatAmt2(sum("dr_amt")),
      cr_amt: arapFormatAmt2(sum("cr_amt")),
    };
  }

  function renderAccountQueryModalBody(state) {
    const account = state.account || {};
    const lines = state.lines || [];
    const totals = state.totals || accountQueryTotals(lines);
    const headers = accountQueryColHeaders();
    const colKeys = ["date", "vou_key", "currency", "rate", "dr_amt", "cr_amt", "remark"];
    const accTotal = (state.accounts || []).length;
    const accCur = accTotal ? state.account_index + 1 : null;
    const accNav = formatRecordNavLabel(accTotal, accCur);
    const lineCur =
      state.selectedRow != null && state.selectedRow >= 0 && state.selectedRow < lines.length
        ? state.selectedRow + 1
        : null;
    const lineNav = formatRecordNavLabel(lines.length, lineCur);
    const disAccFirst = !accTotal || (accCur != null && accCur <= 1);
    const disAccPrev = !accTotal || accCur == null || accCur <= 1;
    const disAccNext = !accTotal || accCur == null || accCur >= accTotal;
    const disAccLast = !accTotal || (accCur != null && accCur >= accTotal);
    const disLineFirst = !lines.length || (lineCur != null && lineCur <= 1);
    const disLinePrev = !lines.length || lineCur == null || lineCur <= 1;
    const disLineNext = !lines.length || lineCur == null || lineCur >= lines.length;
    const disLineLast = !lines.length || (lineCur != null && lineCur >= lines.length);
    let rows = lines
      .map((ln, ri) => {
        const sel = state.selectedRow === ri ? " selected" : "";
        const alt = ri % 2 === 1 ? " arap-row-alt" : "";
        const cells = colKeys
          .map((c) => {
            let v = ln[c] || "";
            if (c === "date") v = arapFormatDate(v);
            else if (c === "rate") v = arapFormatRate4(v);
            else if (["dr_amt", "cr_amt"].includes(c)) v = arapFormatAmt2(v);
            return `<td class="${accountQueryColAlign(c)}">${escapeHtml(v)}</td>`;
          })
          .join("");
        return `<tr class="arap-row account-query-row${sel}${alt}" data-account-query-row="${ri}">${cells}</tr>`;
      })
      .join("");
    const emptyCells = headers
      .map((h, i) => `<td class="arap-pad-cell ${accountQueryColAlign(colKeys[i])}"></td>`)
      .join("");
    const padCount = Math.max(0, ACCOUNT_QUERY_GRID_VISIBLE_ROWS - lines.length);
    for (let i = 0; i < padCount; i++) {
      const alt = (lines.length + i) % 2 === 1 ? " arap-row-alt" : "";
      rows += `<tr class="arap-row-pad${alt}" aria-hidden="true">${emptyCells}</tr>`;
    }
    const head = headers
      .map((h, i) => `<th class="${accountQueryColAlign(colKeys[i])}">${escapeHtml(h)}</th>`)
      .join("");
    return `
      <div class="arap-header-grid party-query-header-grid party-query-header-left">
        <div class="arap-header-field"><label>${escapeHtml(t("accountQueryNo"))}</label>
          <div class="lookup-field-wrap">
            <input type="text" class="account-query-key-input" value="${escapeHtml(account.key || "")}">
            <button type="button" class="btn secondary lookup-btn" data-account-query-act="lookup-acc" title="${escapeHtml(t("lookup"))}" aria-label="${escapeHtml(t("lookup"))}">…</button>
          </div>
        </div>
        <div class="arap-header-field"><label>${escapeHtml(t("accountQueryParent"))}</label><input readonly value="${escapeHtml(account.parent_key || "")}"></div>
        <div class="arap-header-field"><label>${escapeHtml(t("accountQueryType"))}</label><input readonly value="${escapeHtml(account.acc_type || "")}"></div>
        <div class="arap-header-field"><label>${escapeHtml(t("accountQueryLevel"))}</label><input readonly value="${escapeHtml(account.acc_level || "")}"></div>
        <div class="arap-header-field"><label>${escapeHtml(t("accountQueryName"))}</label><input readonly value="${escapeHtml(account.name || "")}"></div>
        <div class="arap-header-field party-query-header-spacer"></div>
      </div>
      <div class="arap-toolbar-row party-query-party-nav">
        ${iconBtnOnly(t("navFirst"), "nav-first", "btn nav-btn", `data-account-query-acc-nav="first"${disAccFirst ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navPrev"), "nav-prev", "btn nav-btn", `data-account-query-acc-nav="prev"${disAccPrev ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navNext"), "nav-next", "btn nav-btn", `data-account-query-acc-nav="next"${disAccNext ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navLast"), "nav-last", "btn nav-btn", `data-account-query-acc-nav="last"${disAccLast ? " disabled" : ""}`)}
        <span class="arap-record-nav">${escapeHtml(accNav)}</span>
      </div>
      <div class="party-query-date-row">
        <label>${escapeHtml(t("partyQueryDateFrom"))}</label>
        <div class="date-field-wrap">
          <input type="text" class="account-query-date-from" value="${escapeHtml(state.date_from || "")}" placeholder="yyyy/MM/dd">
          <button type="button" class="btn secondary date-pick-btn btn-icon-only" data-account-query-date="from" title="${escapeHtml(t("printDatePickBtn"))}">${uiIcon("view-calendar", 14)}</button>
        </div>
        <label>${escapeHtml(t("partyQueryDateTo"))}</label>
        <div class="date-field-wrap">
          <input type="text" class="account-query-date-to" value="${escapeHtml(state.date_to || "")}" placeholder="yyyy/MM/dd">
          <button type="button" class="btn secondary date-pick-btn btn-icon-only" data-account-query-date="to" title="${escapeHtml(t("printDatePickBtn"))}">${uiIcon("view-calendar", 14)}</button>
        </div>
      </div>
      <div class="arap-search-row">
        <label class="search-label">${t("searchLabel")}</label>
        <input type="text" class="account-query-search-input" value="${escapeHtml(state.keyword || "")}">
        ${iconBtn(t("search"), "search", "btn action-btn", 'data-account-query-act="search"')}
        ${iconBtn(t("filter"), "filter", "btn action-btn", 'data-account-query-act="filter"')}
      </div>
      <div class="arap-toolbar-row">
        ${iconBtnOnly(t("navFirst"), "nav-first", "btn nav-btn", `data-account-query-line-nav="first"${disLineFirst ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navPrev"), "nav-prev", "btn nav-btn", `data-account-query-line-nav="prev"${disLinePrev ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navNext"), "nav-next", "btn nav-btn", `data-account-query-line-nav="next"${disLineNext ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navLast"), "nav-last", "btn nav-btn", `data-account-query-line-nav="last"${disLineLast ? " disabled" : ""}`)}
        <span class="arap-record-nav">${escapeHtml(lineNav)}</span>
        ${iconBtn(t("exit"), "exit", "btn action-btn", 'data-account-query-act="exit"')}
      </div>
      <div class="arap-grid-block arap-grid-15-rows">
        <div class="arap-table-scroll">
          <table class="arap-table arap-table-main party-query-table account-query-table">
            <thead><tr>${head}</tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
      </div>
      <div class="party-query-footer">
        <div class="party-query-foot-line">${escapeHtml(t("accountQueryTotals"))}：
          ${escapeHtml(t("accountQueryColDr"))} ${escapeHtml(totals.dr_amt || "0.00")}　
          ${escapeHtml(t("accountQueryColCr"))} ${escapeHtml(totals.cr_amt || "0.00")}
        </div>
      </div>`;
  }

  function refreshAccountQueryModalBody(tab) {
    const overlay = accountQueryHost();
    if (!overlay || !accountQueryModalState) return;
    const body = accountQueryBodyHost(overlay);
    if (!body) return;
    body.innerHTML = renderAccountQueryModalBody(accountQueryModalState);
    bindAccountQueryModalEvents(tab);
  }

  async function reloadAccountQueryFromServer(tab, accountIndex, opts = {}) {
    const accountKey = String(opts.accountKey || "").trim();
    const oldRow =
      tab.selectedRow != null && tab.physicalRows[tab.selectedRow]
        ? tab.physicalRows[tab.selectedRow]
        : [];
    const overlay = accountQueryHost();
    let dateFrom = overlay?.querySelector(".account-query-date-from")?.value?.trim() || "";
    let dateTo = overlay?.querySelector(".account-query-date-to")?.value?.trim() || "";
    dateFrom = normalizePartyQueryDateText(dateFrom);
    dateTo = normalizePartyQueryDateText(dateTo);
    const body = {
      old_row: oldRow,
      account_index: accountIndex,
      date_from: dateFrom,
      date_to: dateTo,
    };
    if (accountKey) body.account_key = accountKey;
    const data = await api(`/work/${encodeURIComponent(tab.doProc)}/account-query/load`, {
      method: "POST",
      body: JSON.stringify(body),
    });
    accountQueryModalState.accounts = data.accounts || [];
    accountQueryModalState.account_index = data.account_index ?? 0;
    accountQueryModalState.account = data.account || {};
    accountQueryModalState.allLines = JSON.parse(JSON.stringify(data.lines || []));
    accountQueryModalState.date_from = data.date_from || dateFrom;
    accountQueryModalState.date_to = data.date_to || dateTo;
    accountQueryModalState.tx_kinds = data.tx_kinds || ["ACC"];
    accountQueryModalState.filterKeyword = accountQueryModalState.filterKeyword || "";
    const kw = overlay?.querySelector(".account-query-search-input")?.value?.trim() || "";
    accountQueryModalState.keyword = kw;
    accountQueryModalState.lines = accountQueryFilterLines(
      accountQueryModalState.allLines,
      accountQueryModalState.filterKeyword
    );
    accountQueryModalState.totals =
      data.totals || accountQueryTotals(accountQueryModalState.lines);
    accountQueryModalState.selectedRow = accountQueryModalState.lines.length ? 0 : null;
    renderTabs();
    refreshAccountQueryModalBody(tab);
  }

  function scheduleAccountQueryReload(tab) {
    if (!accountQueryModalState) return;
    clearTimeout(accountQueryModalState._reloadTimer);
    accountQueryModalState._reloadTimer = setTimeout(() => {
      reloadAccountQueryFromServer(tab, accountQueryModalState.account_index ?? 0).catch((e) =>
        showAlert(e.message || t("otherNotConfigured"))
      );
    }, 250);
  }

  function bindAccountQueryModalEvents(tab) {
    const overlay = accountQueryHost();
    if (!overlay || !accountQueryModalState) return;
    overlay.querySelectorAll("[data-account-query-acc-nav]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (btn.disabled) return;
        const act = btn.getAttribute("data-account-query-acc-nav");
        const total = (accountQueryModalState.accounts || []).length;
        let idx = accountQueryModalState.account_index ?? 0;
        if (act === "first") idx = 0;
        else if (act === "prev") idx = Math.max(0, idx - 1);
        else if (act === "next") idx = Math.min(total - 1, idx + 1);
        else if (act === "last") idx = Math.max(0, total - 1);
        try {
          await reloadAccountQueryFromServer(tab, idx);
        } catch (e) {
          showAlert(e.message || t("otherNotConfigured"));
        }
      });
    });
    overlay.querySelectorAll("[data-account-query-line-nav]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        const act = btn.getAttribute("data-account-query-line-nav");
        const n = accountQueryModalState.lines.length;
        if (n <= 0) return;
        let r = accountQueryModalState.selectedRow ?? 0;
        if (act === "first") r = 0;
        else if (act === "prev") r = Math.max(0, r - 1);
        else if (act === "next") r = Math.min(n - 1, r + 1);
        else if (act === "last") r = n - 1;
        accountQueryModalState.selectedRow = r;
        refreshAccountQueryModalBody(tab);
      });
    });
    overlay.querySelectorAll(".account-query-row").forEach((tr) => {
      tr.addEventListener("click", () => {
        const ri = parseInt(tr.getAttribute("data-account-query-row"), 10);
        if (!Number.isNaN(ri)) {
          accountQueryModalState.selectedRow = ri;
          refreshAccountQueryModalBody(tab);
        }
      });
    });
    const dateFrom = overlay.querySelector(".account-query-date-from");
    const dateTo = overlay.querySelector(".account-query-date-to");
    const onDateBlur = (inp) => {
      if (!inp) return;
      const n = normalizePartyQueryDateText(inp.value);
      if (n !== inp.value.trim()) inp.value = n;
      scheduleAccountQueryReload(tab);
    };
    dateFrom?.addEventListener("change", () => onDateBlur(dateFrom));
    dateTo?.addEventListener("change", () => onDateBlur(dateTo));
    dateFrom?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onDateBlur(dateFrom);
      }
    });
    dateTo?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onDateBlur(dateTo);
      }
    });
    const keyInp = overlay.querySelector(".account-query-key-input");
    keyInp?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        gotoAccountKeyFromInput(tab, keyInp.value);
      }
    });
    keyInp?.addEventListener("change", () => gotoAccountKeyFromInput(tab, keyInp.value));
    overlay.querySelectorAll("[data-account-query-date]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const which = btn.getAttribute("data-account-query-date");
        const inp = which === "to" ? dateTo : dateFrom;
        if (!inp) return;
        const picker = document.createElement("input");
        picker.type = "date";
        picker.style.position = "fixed";
        picker.style.left = "-9999px";
        document.body.appendChild(picker);
        const cur = normalizePartyQueryDateText(inp.value);
        if (/^\d{4}\/\d{2}\/\d{2}$/.test(cur)) {
          picker.value = cur.replace(/\//g, "-");
        }
        picker.addEventListener("change", () => {
          if (picker.value) {
            const [y, m, d] = picker.value.split("-");
            inp.value = `${y}/${m}/${d}`;
          } else {
            inp.value = "";
          }
          picker.remove();
          scheduleAccountQueryReload(tab);
        });
        picker.showPicker?.();
        picker.click();
      });
    });
    overlay.querySelectorAll("[data-account-query-act]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const act = btn.getAttribute("data-account-query-act");
        if (act === "exit") {
          closeAccountQueryModal();
          return;
        }
        if (act === "lookup-acc") {
          openAccountKeyLookup(tab).catch((e) =>
            showAlert(e.message || t("otherNotConfigured"))
          );
          return;
        }
        const kw =
          overlay.querySelector(".account-query-search-input")?.value?.trim() || "";
        accountQueryModalState.keyword = kw;
        if (act === "filter") {
          accountQueryModalState.filterKeyword = kw;
          accountQueryModalState.lines = accountQueryFilterLines(
            accountQueryModalState.allLines,
            kw
          );
          accountQueryModalState.totals = accountQueryTotals(accountQueryModalState.lines);
          accountQueryModalState.selectedRow = accountQueryModalState.lines.length ? 0 : null;
          refreshAccountQueryModalBody(tab);
        } else if (act === "search") {
          const idx = accountQueryModalState.allLines.findIndex((ln) => {
            const blob = [
              ln.date,
              ln.vou_key,
              ln.currency,
              ln.rate,
              ln.dr_amt,
              ln.cr_amt,
              ln.remark,
            ]
              .join(" ")
              .toLowerCase();
            return blob.includes(kw.toLowerCase());
          });
          if (idx < 0) {
            showAlert(t("partyQuerySearchMiss"));
            return;
          }
          accountQueryModalState.filterKeyword = "";
          accountQueryModalState.lines = accountQueryModalState.allLines.slice();
          accountQueryModalState.totals = accountQueryTotals(accountQueryModalState.lines);
          accountQueryModalState.selectedRow = idx;
          refreshAccountQueryModalBody(tab);
        }
      });
    });
  }

  function accountPhysicalIsDetail(physicalFields, physicalRow) {
    const fields = physicalFields || [];
    const up = fields.map((f) => String(f || "").trim().toUpperCase());
    let i = up.indexOf("AC_TYPE");
    if (i < 0) i = up.indexOf("ACC_TYPE");
    if (i < 0) return true;
    const v = String(physicalRow?.[i] || "")
      .trim()
      .toUpperCase();
    if (!v) return true;
    if (v === "DETAIL" || v === "DET" || v === "D" || v.startsWith("DETAIL") || v.includes("明細")) {
      return true;
    }
    if (
      ["HEADER", "TITLE", "GROUP", "SUMMARY", "TOTAL", "H", "T", "G", "S"].includes(v) ||
      v.startsWith("HEADER") ||
      v.startsWith("TITLE")
    ) {
      return false;
    }
    return true;
  }

  function gotoAccountKeyFromInput(tab, rawKey) {
    const key = String(rawKey || "").trim();
    if (!key || !accountQueryModalState) return;
    const accounts = accountQueryModalState.accounts || [];
    const idx = accounts.findIndex(
      (a) => String(a.key || "").trim().toUpperCase() === key.toUpperCase()
    );
    if (idx < 0) {
      reloadAccountQueryFromServer(tab, -1, { accountKey: key }).catch((e) =>
        showAlert(
          e.message ||
            (stateLangIsChn()
              ? "找不到此賬戶編號（僅顯示 AC_TYPE=DETAIL）。"
              : "Account not found (DETAIL accounts only).")
        )
      );
      return;
    }
    reloadAccountQueryFromServer(tab, idx).catch((e) =>
      showAlert(e.message || t("otherNotConfigured"))
    );
  }

  function stateLangIsChn() {
    try {
      return String(t("accountQueryTitle") || "").includes("賬戶");
    } catch (_) {
      return true;
    }
  }

  async function openAccountKeyLookup(tab) {
    if (!tab?.doProc) return;
    let data;
    try {
      data = await api(`/work/${encodeURIComponent(tab.doProc)}/lookup/rows`, {
        method: "POST",
        body: JSON.stringify({ lookup_db: "ACCOUNT", keyword: "", as_filter: false }),
      });
    } catch (e) {
      showAlert(e.message || t("otherNotConfigured"));
      return;
    }
    const physicalFields = data.physical_fields || data.fields || [];
    const physicalRows = (data.physical_rows || []).filter((r) =>
      accountPhysicalIsDetail(physicalFields, r)
    );
    // 依篩選後的 physical 重建 display rows
    const fields = data.fields || [];
    const physIdx = fields.map((f) => {
      const u = String(f || "").trim().toUpperCase();
      return physicalFields.findIndex((p) => String(p || "").trim().toUpperCase() === u);
    });
    const rows = physicalRows.map((pr) =>
      physIdx.map((i) => (i >= 0 && i < pr.length ? pr[i] : ""))
    );
    const retCandidates = ["ACC_KEY", "ACCOUNT_KEY", "ACC_CODE", "KEY"];
    let retField = "ACC_KEY";
    for (const c of retCandidates) {
      if (physicalFields.some((p) => String(p || "").trim().toUpperCase() === c)) {
        retField = c;
        break;
      }
    }
    // 直接在自訂 overlay 選取（COLUMNS 定義欄位，僅 AC_TYPE=DETAIL）
    await openFilteredAccountLookup(tab, {
      fields,
      columns: data.columns || {},
      rows,
      physical_fields: physicalFields,
      physical_rows: physicalRows,
      retField,
    });
  }

  async function openQueryMasterLookup(tab, pack) {
    const fields = pack.fields || [];
    const rows = pack.rows || [];
    const physicalFields = pack.physical_fields || [];
    const physicalRows = pack.physical_rows || [];
    const retField = String(pack.retField || "").toUpperCase();
    const retIdx = physicalFields.findIndex(
      (p) => String(p || "").trim().toUpperCase() === retField
    );
    const title = pack.title || retField || "Lookup";
    let selected = 0;
    const renderBody = () => {
      const head = fields
        .map((f) => {
          const meta = (pack.columns && pack.columns[f]) || {};
          const titleCell = meta.title || f;
          return `<th>${escapeHtml(titleCell)}</th>`;
        })
        .join("");
      const body = rows
        .map((r, i) => {
          const sel = i === selected ? " selected" : "";
          const cells = r.map((c) => `<td>${escapeHtml(c || "")}</td>`).join("");
          return `<tr class="arap-row${sel}" data-qlookup-row="${i}">${cells}</tr>`;
        })
        .join("");
      return `<div class="arap-table-scroll"><table class="arap-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>
        <div class="arap-toolbar-row" style="margin-top:8px">
          <button type="button" class="btn action-btn" data-qlookup-ok="1">${escapeHtml(t("msgOk"))}</button>
          <button type="button" class="btn secondary" data-qlookup-cancel="1">${escapeHtml(t("cancel"))}</button>
        </div>`;
    };
    const existing = $("#query-master-lookup-overlay");
    if (existing) existing.remove();
    const overlay = document.createElement("div");
    overlay.id = "query-master-lookup-overlay";
    overlay.className = "arap-modal-overlay";
    overlay.innerHTML = `<div class="arap-modal" role="dialog" aria-modal="true">
      <div class="arap-modal-header"><h2>${escapeHtml(t("lookup"))} — ${escapeHtml(title)}</h2></div>
      <div class="arap-modal-body">${renderBody()}</div>
    </div>`;
    document.body.appendChild(overlay);
    const bodyHost = overlay.querySelector(".arap-modal-body");
    const bind = () => {
      bodyHost.querySelectorAll("[data-qlookup-row]").forEach((tr) => {
        tr.addEventListener("click", () => {
          selected = parseInt(tr.getAttribute("data-qlookup-row"), 10) || 0;
          bodyHost.innerHTML = renderBody();
          bind();
        });
        tr.addEventListener("dblclick", () => {
          selected = parseInt(tr.getAttribute("data-qlookup-row"), 10) || 0;
          pick();
        });
      });
      bodyHost.querySelector("[data-qlookup-ok]")?.addEventListener("click", pick);
      bodyHost.querySelector("[data-qlookup-cancel]")?.addEventListener("click", () =>
        overlay.remove()
      );
    };
    const pick = () => {
      const pr = physicalRows[selected];
      const key =
        retIdx >= 0 && pr ? String(pr[retIdx] || "").trim() : String(rows[selected]?.[0] || "").trim();
      overlay.remove();
      if (!key) return;
      if (typeof pack.onPick === "function") pack.onPick(key);
    };
    bind();
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) overlay.remove();
    });
  }

  async function openFilteredAccountLookup(tab, pack) {
    await openQueryMasterLookup(tab, {
      ...pack,
      title: "ACCOUNT",
      onPick: (key) => {
        const idx = (accountQueryModalState.accounts || []).findIndex(
          (a) => String(a.key || "").trim().toUpperCase() === key.toUpperCase()
        );
        if (idx < 0) {
          showAlert(
            stateLangIsChn()
              ? "找不到此賬戶編號（僅顯示 AC_TYPE=DETAIL）。"
              : "Account not found (DETAIL accounts only)."
          );
          return;
        }
        reloadAccountQueryFromServer(tab, idx).catch((e) =>
          showAlert(e.message || t("otherNotConfigured"))
        );
      },
    });
  }

  function accountKeysMatch(a, b) {
    const norm = (s) =>
      String(s || "")
        .trim()
        .toUpperCase()
        .replace(/[－—–_]/g, "-")
        .replace(/\s+/g, "");
    const x = norm(a);
    const y = norm(b);
    if (!x || !y) return false;
    if (x === y) return true;
    const xc = x.replace(/-/g, "");
    const yc = y.replace(/-/g, "");
    if (xc === yc) return true;
    return x.split("-", 1)[0] === yc || y.split("-", 1)[0] === xc;
  }

  async function openAccountQueryModal(tab, opts = {}) {
    const accountKey = String(opts.accountKey || opts.key || opts.keyword || "").trim();
    const id = queryTabId("account", tab.id);
    const existing = openTabs.find((x) => x.id === id);
    if (existing) {
      accountQueryModalState = existing;
      activeTabId = id;
      renderTabs();
      if (accountKey) {
        const accounts = existing.accounts || [];
        const idx = accounts.findIndex((a) => accountKeysMatch(a.key, accountKey));
        if (idx < 0) {
          try {
            await reloadAccountQueryFromServer(tab, -1, { accountKey });
          } catch (e) {
            renderTabs();
            showAlert(e.message || t("otherNotConfigured"));
          }
          return;
        }
        try {
          await reloadAccountQueryFromServer(tab, idx);
        } catch (e) {
          renderTabs();
          showAlert(e.message || t("otherNotConfigured"));
        }
      } else {
        try {
          await reloadAccountQueryFromServer(tab, existing.account_index ?? 0);
        } catch (e) {
          renderTabs();
          showAlert(e.message || t("otherNotConfigured"));
        }
      }
      return;
    }
    const oldRow =
      tab.selectedRow != null && tab.physicalRows[tab.selectedRow]
        ? tab.physicalRows[tab.selectedRow]
        : [];
    try {
      const data = await api(`/work/${encodeURIComponent(tab.doProc)}/account-query/load`, {
        method: "POST",
        body: JSON.stringify({
          old_row: oldRow,
          account_index: -1,
          account_key: accountKey,
          date_from: "",
          date_to: "",
          tx_kinds: ["ACC"],
        }),
      });
      const title = t("accountQueryTitle");
      accountQueryModalState = {
        type: "account-query",
        id,
        parentWorkId: tab.id,
        doProc: tab.doProc,
        title,
        menuTitle: title,
        tab,
        accounts: data.accounts || [],
        account_index: data.account_index ?? 0,
        account: data.account || {},
        allLines: JSON.parse(JSON.stringify(data.lines || [])),
        lines: data.lines || [],
        totals: data.totals || accountQueryTotals(data.lines || []),
        date_from: data.date_from || "",
        date_to: data.date_to || "",
        tx_kinds: data.tx_kinds || ["ACC"],
        keyword: "",
        filterKeyword: "",
        selectedRow: (data.lines || []).length ? 0 : null,
      };
      openTabs.push(accountQueryModalState);
      activeTabId = id;
      renderTabs();
      if (
        accountKey &&
        !accountKeysMatch((data.account && data.account.key) || "", accountKey)
      ) {
        showAlert(
          currentLang === "CHN"
            ? `找不到此賬戶編號「${accountKey}」。`
            : `Account "${accountKey}" not found.`
        );
      }
    } catch (e) {
      showAlert(e.message || t("otherNotConfigured"));
    }
  }

  const IMPORT_FOLDER_KEY = "wolee_dataimport_folders_v2";

  function loadSavedImportFolders() {
    try {
      const raw = JSON.parse(localStorage.getItem(IMPORT_FOLDER_KEY) || "{}");
      return raw && typeof raw === "object" ? raw : {};
    } catch (_) {
      return {};
    }
  }

  function saveImportFolder(kind, folder) {
    const k = String(kind || "").trim().toUpperCase() || "_";
    const map = loadSavedImportFolders();
    map[k] = String(folder || "").trim();
    try {
      localStorage.setItem(IMPORT_FOLDER_KEY, JSON.stringify(map));
    } catch (_) {}
  }

  function looksLikeAppDirTransferFolder(folder) {
    const f = String(folder || "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
    if (!f) return true;
    // 舊預設常指向應用目錄，其 TRANSFER.sqlite 多為已匯入副本，不是業務來源
    return /(^|\/)woleeweb$/i.test(f);
  }

  async function loadDataImportPending(doProc, kind, folder) {
    const key = String(kind || "").trim().toUpperCase();
    const folderQ = folder ? `&folder=${encodeURIComponent(folder)}` : "";
    if (key !== "PURCHASE" && key !== "INVOICE") {
      return {
        rows: [],
        columns: [],
        source_table: "",
        stock: true,
        db_path: "",
        db_mtime: "",
        warning: "",
        folder: folder || "",
      };
    }
    const bust = Date.now();
    const res = await api(
      `/work/${encodeURIComponent(doProc)}/import/pending?kind=${encodeURIComponent(key)}${folderQ}&_=${bust}`,
      {
        cache: "no-store",
        headers: {
          "Cache-Control": "no-cache, no-store, must-revalidate",
          Pragma: "no-cache",
          "If-Modified-Since": "0",
        },
      }
    );
    return {
      rows: res.rows || [],
      columns: res.columns || [],
      source_table: res.source_table || "",
      stock: false,
      db_path: res.db_path || "",
      db_mtime: res.db_mtime || "",
      db_size: res.db_size || 0,
      pending_count: res.pending_count != null ? res.pending_count : (res.rows || []).length,
      warning: res.warning || "",
      folder: res.folder || folder || "",
    };
  }

  function renderDataImportPendingList(overlay, pending, kind) {
    const rows = pending.rows || [];
    const columns = pending.columns || [];
    const host = overlay.querySelector(".data-import-pending-list");
    const label = overlay.querySelector(".data-import-pending-label");
    const meta = overlay.querySelector(".data-import-source-meta");
    const tools = overlay.querySelector(".data-import-pending-tools");
    const key = String(kind || "").trim().toUpperCase();
    const VISIBLE_ROWS = 10;
    if (!host || !label) return;
    if (meta) {
      const path = pending.db_path || "";
      const mtime = pending.db_mtime || "";
      const size = Number(pending.db_size || 0);
      const count = pending.pending_count != null ? pending.pending_count : rows.length;
      const warn = pending.warning || "";
      let text = "";
      if (path) {
        const sizeTxt = size > 0 ? `，${Math.round(size / 1024)} KB` : "";
        const countTxt = key === "STOCK" ? "" : `，待匯入 ${count} 筆`;
        text = `${t("dataImportSource")}: ${path}${mtime ? ` (${mtime}${sizeTxt}${countTxt})` : `${sizeTxt}${countTxt}`}`;
      }
      if (warn) text = (text ? text + "\n" : "") + warn;
      meta.textContent = text;
      meta.classList.toggle("hidden", !text);
    }
    if (key === "STOCK") {
      label.textContent = t("dataImportStockHint");
      host.innerHTML = "";
      if (tools) tools.classList.add("hidden");
      return;
    }
    const src = pending.source_table || (key === "PURCHASE" ? "PUR_HEADER" : "INV_HEADER");
    label.textContent = `${t("dataImportPending")}（TRANSFER.${src} GRID）`;
    if (tools) tools.classList.remove("hidden");
    const cols = columns.length
      ? columns
      : [{ name: "TX_KEY", title: "TX_KEY", numeric: false }, { name: "TX_TYPE", title: "TX_TYPE", numeric: false }];
    const alignClass = (col) => (col && col.numeric ? " cell-num" : " cell-text");
    const head = cols
      .map((c) => `<th class="${alignClass(c).trim()}">${escapeHtml(c.title || c.name || "")}</th>`)
      .join("");
    const dataBody = rows
      .map((row) => {
        const cells = Array.isArray(row.cells) ? row.cells : [];
        const tds = cols
          .map((c, i) => {
            const v = cells[i] != null ? String(cells[i]) : "";
            return `<td class="${alignClass(c).trim()}">${escapeHtml(v)}</td>`;
          })
          .join("");
        return `<tr data-import-key="${escapeHtml(row.key || "")}">
          <td class="data-import-check-col"><input type="checkbox" class="import-pending-cb" value="${escapeHtml(
            row.key || ""
          )}" checked></td>
          ${tds}
        </tr>`;
      })
      .join("");
    // 少於 10 筆時補空白列，保留可視空白列空間；超過 10 筆由外層捲軸瀏覽
    const padCount = Math.max(0, VISIBLE_ROWS - rows.length);
    const padCols = cols.map((c) => `<td class="${alignClass(c).trim()}">&nbsp;</td>`).join("");
    const padBody = Array.from({ length: padCount }, () =>
      `<tr class="data-import-pad-row" aria-hidden="true">
        <td class="data-import-check-col"></td>${padCols}
      </tr>`
    ).join("");
    const emptyNote = !rows.length
      ? `<p class="data-import-pending-empty">${escapeHtml(t("dataImportPendingEmpty"))}</p>`
      : "";
    host.innerHTML = `${emptyNote}<div class="data-import-grid-wrap" style="--import-visible-rows:${VISIBLE_ROWS}">
      <table class="data-import-grid">
        <thead><tr><th class="data-import-check-col"></th>${head}</tr></thead>
        <tbody>${dataBody}${padBody}</tbody>
      </table>
    </div>
    <p class="data-import-grid-count">${escapeHtml(
      currentLang === "CHN" ? `共 ${rows.length} 筆未處理資料` : `${rows.length} unposted row(s)`
    )}</p>`;
  }

  const RUN_QUERY_VISIBLE_ROWS = 12;

  function runQueryConnPayload(tab) {
    return {
      kind: tab.connKind || "SQLITE",
      path: tab.connPath || "",
      host: tab.connHost || "localhost",
      port: Number(tab.connPort || 0),
      database: tab.connDatabase || "",
      user: tab.connUser || "",
      password: tab.connPassword || "",
      driver: "",
    };
  }

  function isFileDbKind(kind) {
    const k = String(kind || "").toUpperCase();
    return k === "SQLITE" || k === "ACCESS";
  }

  async function openRunQueryTab(doProc, title) {
    let meta;
    try {
      meta = await api("/run-query/prepare", { method: "POST", body: "{}" });
    } catch (e) {
      showAlert(e.message || String(e));
      return;
    }
    const id = `run-query-${String(doProc || "RUNQUERY").trim()}`;
    let tab = openTabs.find((x) => x.id === id);
    if (!tab) {
      tab = {
        type: "run-query",
        id,
        doProc: doProc || meta.do_proc || "RUNQUERY",
        title: title || meta.title || t("runQueryTitle"),
        menuTitle: title || meta.title || "",
        sql: "",
        columns: [],
        allRows: [],
        viewRows: [],
        keyword: "",
        selectedRow: null,
        status: "",
        connMsg: "",
        connected: false,
        dbKinds: meta.db_kinds || [],
        connKind: meta.default_kind || "SQLITE",
        connPath: meta.default_path || "",
        connHost: "localhost",
        connPort: 0,
        connDatabase: "",
        connUser: "",
        connPassword: "",
      };
      openTabs.push(tab);
    } else {
      if (title) {
        tab.title = title;
        tab.menuTitle = title;
      }
      tab.dbKinds = meta.db_kinds || tab.dbKinds || [];
      if (!tab.connPath && meta.default_path) tab.connPath = meta.default_path;
      if (!tab.connKind && meta.default_kind) tab.connKind = meta.default_kind;
    }
    activeTabId = id;
    renderTabs();
  }

  function filterRunQueryRows(rows, keyword) {
    const kw = String(keyword || "").trim().toLowerCase();
    if (!kw) return rows.map((r) => [...r]);
    return rows.filter((r) => r.some((c) => String(c || "").toLowerCase().includes(kw)));
  }

  function renderRunQueryPage(tab) {
    const cols = tab.columns || [];
    const rows = tab.viewRows || [];
    const padCount = Math.max(0, RUN_QUERY_VISIBLE_ROWS - rows.length);
    const thead =
      cols.length > 0
        ? cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("")
        : `<th>&nbsp;</th>`;
    const dataBody = rows
      .map((r, ri) => {
        const sel = tab.selectedRow === ri ? " selected" : "";
        const cells = (cols.length ? cols : [""])
          .map((_, ci) => `<td>${escapeHtml(r[ci] != null ? r[ci] : "")}</td>`)
          .join("");
        return `<tr class="run-query-row${sel}" data-run-query-row="${ri}">${cells}</tr>`;
      })
      .join("");
    const padBody = Array.from({ length: padCount }, () => {
      const cells = (cols.length ? cols : [""]).map(() => `<td class="grid-pad-cell">&nbsp;</td>`).join("");
      return `<tr class="run-query-pad">${cells}</tr>`;
    }).join("");
    const total = rows.length;
    const cur = tab.selectedRow != null && tab.selectedRow >= 0 ? tab.selectedRow + 1 : null;
    const navLabel = formatRecordNavLabel(total, cur);
    const disFirst = !(total > 0 && (tab.selectedRow || 0) > 0);
    const disPrev = disFirst;
    const disNext = !(total > 0 && tab.selectedRow != null && tab.selectedRow < total - 1);
    const disLast = disNext;
    const kinds = tab.dbKinds || [];
    const kindOpts = kinds
      .map(
        (k) =>
          `<option value="${escapeHtml(k.kind)}"${
            String(tab.connKind || "").toUpperCase() === String(k.kind || "").toUpperCase()
              ? " selected"
              : ""
          }>${escapeHtml(k.label || k.kind)}</option>`
      )
      .join("");
    const fileMode = isFileDbKind(tab.connKind);
    const connFields = fileMode
      ? `<div class="run-query-conn-file">
          <label>${escapeHtml(t("runQueryFile"))}</label>
          <input type="text" class="run-query-path" value="${escapeHtml(tab.connPath || "")}">
        </div>`
      : `<div class="run-query-conn-server">
          <label>${escapeHtml(t("runQueryHost"))}<input type="text" class="run-query-host" value="${escapeHtml(tab.connHost || "localhost")}"></label>
          <label>${escapeHtml(t("runQueryPort"))}<input type="number" class="run-query-port" value="${escapeHtml(String(tab.connPort || 0))}"></label>
          <label>${escapeHtml(t("runQueryDbName"))}<input type="text" class="run-query-database" value="${escapeHtml(tab.connDatabase || "")}"></label>
          <label>${escapeHtml(t("runQueryUser"))}<input type="text" class="run-query-user" value="${escapeHtml(tab.connUser || "")}"></label>
          <label>${escapeHtml(t("runQueryPassword"))}<input type="password" class="run-query-password" value="${escapeHtml(tab.connPassword || "")}"></label>
        </div>`;
    return `<div class="run-query-page work-page" data-tab="${escapeHtml(tab.id)}">
      <h2 class="run-query-title">${escapeHtml(tab.menuTitle || tab.title || t("runQueryTitle"))}</h2>
      <div class="run-query-db-row">
        <label>${escapeHtml(t("runQueryDb"))}</label>
        <select class="run-query-kind">${kindOpts}</select>
        ${iconBtn(t("runQueryConnect"), "connect", "btn action-btn", 'data-run-query-act="connect"')}
        <span class="run-query-conn-msg">${escapeHtml(tab.connMsg || "")}</span>
      </div>
      ${connFields}
      <label class="run-query-sql-label">${escapeHtml(t("runQuerySql"))}</label>
      <textarea class="run-query-sql" rows="5" placeholder="${escapeHtml(t("runQuerySqlHint"))}">${escapeHtml(tab.sql || "")}</textarea>
      <div class="run-query-actions">
        ${iconBtn(t("runQueryLookup"), "search", "btn action-btn", 'data-run-query-act="lookup"')}
        ${iconBtn(t("save"), "save", "btn action-btn", 'data-run-query-act="save"')}
        ${iconBtn(t("runQueryRun"), "search", "btn action-btn", 'data-run-query-act="run"')}
        ${iconBtn(t("runQueryExport"), "print", "btn action-btn", 'data-run-query-act="export"')}
        ${iconBtn(t("runQueryExit"), "exit", "btn secondary", 'data-run-query-act="close"')}
      </div>
      <div class="search-row run-query-search-row">
        <label>${escapeHtml(t("searchLabel"))}</label>
        <input type="text" class="run-query-search-input" value="${escapeHtml(tab.keyword || "")}">
        ${iconBtn(t("search"), "search", "btn action-btn", 'data-run-query-act="search"')}
        ${iconBtn(t("runQueryClearSearch"), "edit-clear", "btn secondary", 'data-run-query-act="clear-search"')}
      </div>
      <div class="nav-row run-query-nav-row">
        ${iconBtnOnly(t("navFirst"), "nav-first", "btn nav-btn", `data-run-query-nav="first"${disFirst ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navPrev"), "nav-prev", "btn nav-btn", `data-run-query-nav="prev"${disPrev ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navNext"), "nav-next", "btn nav-btn", `data-run-query-nav="next"${disNext ? " disabled" : ""}`)}
        ${iconBtnOnly(t("navLast"), "nav-last", "btn nav-btn", `data-run-query-nav="last"${disLast ? " disabled" : ""}`)}
        <span class="record-nav">${escapeHtml(navLabel)}</span>
      </div>
      <div class="work-table-wrap run-query-grid-wrap" style="--run-query-visible-rows:${RUN_QUERY_VISIBLE_ROWS}">
        <table class="work-table run-query-grid">
          <thead><tr>${thead}</tr></thead>
          <tbody>${dataBody}${padBody}</tbody>
        </table>
      </div>
      <p class="run-query-status">${escapeHtml(tab.status || "")}</p>
    </div>`;
  }

  function syncRunQueryConnFromPage(tab, page) {
    const kindEl = page.querySelector(".run-query-kind");
    if (kindEl) tab.connKind = kindEl.value || tab.connKind;
    const pathEl = page.querySelector(".run-query-path");
    if (pathEl) tab.connPath = pathEl.value || "";
    const hostEl = page.querySelector(".run-query-host");
    if (hostEl) tab.connHost = hostEl.value || "localhost";
    const portEl = page.querySelector(".run-query-port");
    if (portEl) tab.connPort = Number(portEl.value || 0);
    const dbEl = page.querySelector(".run-query-database");
    if (dbEl) tab.connDatabase = dbEl.value || "";
    const userEl = page.querySelector(".run-query-user");
    if (userEl) tab.connUser = userEl.value || "";
    const pwdEl = page.querySelector(".run-query-password");
    if (pwdEl) tab.connPassword = pwdEl.value || "";
    const sqlEl = page.querySelector(".run-query-sql");
    if (sqlEl) tab.sql = sqlEl.value || "";
  }

  function bindRunQueryPageEvents(tab) {
    const page = document.querySelector(`.run-query-page[data-tab="${tab.id}"]`);
    if (!page) return;
    page.querySelector(".run-query-kind")?.addEventListener("change", (e) => {
      tab.connKind = e.target.value;
      tab.connected = false;
      tab.connMsg = "";
      if (String(tab.connKind).toUpperCase() === "MYSQL" && !tab.connPort) tab.connPort = 3306;
      if (String(tab.connKind).toUpperCase() === "SQLSERVER" && (!tab.connPort || tab.connPort === 3306)) {
        tab.connPort = 1433;
      }
      renderTabs();
    });
    page.querySelectorAll("[data-run-query-act]").forEach((btn) => {
      btn.addEventListener("click", () => {
        syncRunQueryConnFromPage(tab, page);
        const act = btn.getAttribute("data-run-query-act");
        if (act === "connect") connectRunQuery(tab).catch((e) => showAlert(e.message || String(e)));
        else if (act === "lookup") openRunQueryLookup(tab).catch((e) => showAlert(e.message || String(e)));
        else if (act === "save") saveRunQuerySql(tab).catch((e) => showAlert(e.message || String(e)));
        else if (act === "run") runRunQuerySql(tab).catch((e) => showAlert(e.message || String(e)));
        else if (act === "export") exportRunQueryXlsx(tab).catch((e) => showAlert(e.message || String(e)));
        else if (act === "search") {
          tab.keyword = page.querySelector(".run-query-search-input")?.value || "";
          tab.viewRows = filterRunQueryRows(tab.allRows || [], tab.keyword);
          tab.selectedRow = tab.viewRows.length ? 0 : null;
          renderTabs();
        } else if (act === "clear-search") {
          tab.keyword = "";
          tab.viewRows = filterRunQueryRows(tab.allRows || [], "");
          tab.selectedRow = tab.viewRows.length ? 0 : null;
          renderTabs();
        } else if (act === "close") closeTab(tab.id);
      });
    });
    page.querySelectorAll("[data-run-query-nav]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const nav = btn.getAttribute("data-run-query-nav");
        const n = (tab.viewRows || []).length;
        if (!n) return;
        let row = tab.selectedRow == null ? 0 : tab.selectedRow;
        if (nav === "first") row = 0;
        else if (nav === "prev") row = Math.max(0, row - 1);
        else if (nav === "next") row = Math.min(n - 1, row + 1);
        else if (nav === "last") row = n - 1;
        tab.selectedRow = row;
        renderTabs();
      });
    });
    page.querySelectorAll("[data-run-query-row]").forEach((tr) => {
      tr.addEventListener("click", () => {
        const ri = Number(tr.getAttribute("data-run-query-row"));
        if (!Number.isFinite(ri)) return;
        tab.selectedRow = ri;
        renderTabs();
      });
    });
  }

  async function connectRunQuery(tab) {
    const res = await api("/run-query/connect", {
      method: "POST",
      body: JSON.stringify({ conn: runQueryConnPayload(tab) }),
    });
    tab.connected = !!res.ok;
    tab.connMsg = res.message || "";
    if (!res.ok) showAlert(res.message || "Connect failed");
    renderTabs();
  }

  async function openRunQueryLookup(tab) {
    const data = await api("/run-query/saved", {
      method: "POST",
      body: JSON.stringify({ keyword: "", as_filter: false }),
    });
    const fields = Array.isArray(data?.fields) ? data.fields : [];
    const columns = Array.isArray(data?.columns) ? data.columns : [];
    const rows = Array.isArray(data?.rows) ? data.rows : [];
    const physicalRows = Array.isArray(data?.physical_rows) ? data.physical_rows : rows;
    const physicalFields = Array.isArray(data?.physical_fields) ? data.physical_fields : fields;
    const titleBy = new Map(columns.map((c) => [c.name, c.title || c.name]));
    let selected = rows.length ? 0 : -1;
    const overlay = document.createElement("div");
    overlay.className = "arap-modal-overlay";
    const renderBody = () => {
      const thead = fields.map((f) => `<th>${escapeHtml(titleBy.get(f) || f)}</th>`).join("");
      const tbody = rows.length
        ? rows
            .map((r, i) => {
              const cells = r.map((c) => `<td>${escapeHtml(c)}</td>`).join("");
              return `<tr data-lu-row="${i}" class="${i === selected ? "selected" : ""}">${cells}</tr>`;
            })
            .join("")
        : `<tr><td colspan="99">${t("noData")}</td></tr>`;
      return `<div class="work-table-wrap" style="max-height:360px;overflow:auto"><table class="work-table"><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table></div>`;
    };
    overlay.innerHTML = `<div class="arap-modal" role="dialog" aria-modal="true">
      <div class="arap-modal-header"><h2>${escapeHtml(t("runQueryLookup"))} — RUN_QUERY</h2></div>
      <div class="arap-modal-body"><div class="lookup-modal-body">${renderBody()}</div></div>
      <div class="arap-modal-footer">
        <button type="button" class="btn secondary" data-lu="cancel">${t("cancel")}</button>
        <button type="button" class="btn action-btn" data-lu="ok">${t("msgOk") || "OK"}</button>
      </div>
    </div>`;
    document.body.appendChild(overlay);
    const bodyHost = overlay.querySelector(".lookup-modal-body");
    const apply = () => {
      if (selected < 0 || !rows.length) {
        overlay.remove();
        return;
      }
      let idx = physicalFields.findIndex((f) => String(f).toUpperCase() === "QRY_COMMAND");
      if (idx < 0) idx = fields.findIndex((f) => String(f).toUpperCase() === "QRY_COMMAND");
      const prow = physicalRows[selected] || rows[selected] || [];
      tab.sql = idx >= 0 && prow[idx] != null ? String(prow[idx]) : "";
      overlay.remove();
      renderTabs();
    };
    bodyHost?.addEventListener("click", (e) => {
      const tr = e.target.closest("[data-lu-row]");
      if (!tr) return;
      selected = Number(tr.getAttribute("data-lu-row"));
      bodyHost.innerHTML = renderBody();
    });
    bodyHost?.addEventListener("dblclick", (e) => {
      const tr = e.target.closest("[data-lu-row]");
      if (!tr) return;
      selected = Number(tr.getAttribute("data-lu-row"));
      apply();
    });
    overlay.querySelector('[data-lu="cancel"]')?.addEventListener("click", () => overlay.remove());
    overlay.querySelector('[data-lu="ok"]')?.addEventListener("click", apply);
  }

  async function saveRunQuerySql(tab) {
    const sql = String(tab.sql || "").trim();
    if (!sql) {
      showAlert(currentLang === "CHN" ? "請先輸入 SQL 指令。" : "Please enter SQL first.");
      return;
    }
    const desc = window.prompt(currentLang === "CHN" ? "說明：" : "Description:", "");
    if (desc == null) return;
    const res = await api("/run-query/save", {
      method: "POST",
      body: JSON.stringify({ sql, description: desc || "" }),
    });
    showAlert(res.message || (currentLang === "CHN" ? "已儲存。" : "Saved."));
    tab.status = res.qry_code || "";
    renderTabs();
  }

  async function runRunQuerySql(tab) {
    const res = await api("/run-query/execute", {
      method: "POST",
      body: JSON.stringify({ sql: tab.sql || "", conn: runQueryConnPayload(tab) }),
    });
    tab.columns = res.columns || [];
    tab.allRows = (res.rows || []).map((r) => [...r]);
    tab.keyword = "";
    tab.viewRows = filterRunQueryRows(tab.allRows, "");
    tab.selectedRow = tab.viewRows.length ? 0 : null;
    tab.status = res.message || "";
    tab.connected = true;
    renderTabs();
  }

  async function exportRunQueryXlsx(tab) {
    const rows = (tab.viewRows && tab.viewRows.length ? tab.viewRows : tab.allRows) || [];
    if (!rows.length) {
      showAlert(currentLang === "CHN" ? "沒有可匯出的結果。" : "No result to export.");
      return;
    }
    const headers = { "Content-Type": "application/json" };
    if (token) headers.Authorization = `Bearer ${token}`;
    const resp = await fetch("/api/run-query/export/xlsx", {
      method: "POST",
      headers,
      body: JSON.stringify({
        columns: tab.columns || [],
        rows,
        filename_stem: "run_query",
      }),
    });
    if (!resp.ok) {
      let msg = "Export failed";
      try {
        const j = await resp.json();
        msg = j.detail || msg;
      } catch (_e) {
        /* ignore */
      }
      throw new Error(msg);
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "run_query.xlsx";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function openDataImportModal(tab) {
    if (!isDataImportTab(tab)) return;
    closeDataImportModal();
    let kinds = [];
    let defaultFolder = "";
    let defaultNote = "";
    try {
      const res = await api(`/work/${encodeURIComponent(tab.doProc)}/import/kinds`);
      kinds = res.kinds || [];
      defaultFolder = String(res.default_folder || "").trim();
      defaultNote = String(res.default_note || "").trim();
    } catch (e) {
      showAlert(e.message || t("dataImportFail"));
      return;
    }
    const overlay = document.createElement("div");
    overlay.id = "data-import-modal-overlay";
    overlay.className = "arap-modal-overlay data-import-modal-overlay";
    const options = kinds
      .map(
        (k, i) =>
          `<option value="${escapeHtml(k.kind)}"${i === 0 ? " selected" : ""}>${escapeHtml(
            (k.label || k.kind) + (k.detail ? " — " + k.detail : "")
          )}</option>`
      )
      .join("");
    overlay.innerHTML = `<div class="arap-modal data-import-modal" role="dialog" aria-modal="true">
      <div class="arap-modal-header"><h2>${escapeHtml(t("dataImportTitle"))}</h2></div>
      <div class="arap-modal-body data-import-modal-body">
        <p class="data-import-hint">${escapeHtml(t("dataImportHint"))}</p>
        <div class="data-import-folder-row">
          <label class="data-import-folder-label">${escapeHtml(t("dataImportFolder"))}
            <input type="text" class="data-import-folder-input" value="" placeholder="S:\\Share\\docBiz\\Transfer 或含 TRANSFER.sqlite 之路徑">
          </label>
          <div class="data-import-folder-actions">
            ${iconBtn(t("dataImportFolderBrowse"), "document-open", "btn secondary btn-sm", 'data-import-act="browse-folder"')}
            ${iconBtn(t("dataImportFolderApply"), "convert_db", "btn secondary btn-sm", 'data-import-act="apply-folder"')}
          </div>
        </div>
        <div class="data-import-kind-row">
          <label class="data-import-kind-label">${escapeHtml(t("dataImportKind"))}
            <select class="data-import-kind-select" name="import-kind">${options}</select>
          </label>
        </div>
        <p class="data-import-pending-label">${escapeHtml(t("dataImportPending"))}</p>
        <p class="data-import-source-meta hidden"></p>
        <div class="data-import-pending-tools">
          ${iconBtn(t("dataImportReload"), "convert_db", "btn secondary btn-sm", 'data-import-act="reload"')}
          ${iconBtn(t("dataImportSelectAll"), "filter", "btn secondary btn-sm", 'data-import-act="select-all"')}
          ${iconBtn(t("dataImportSelectNone"), "filter", "btn secondary btn-sm", 'data-import-act="select-none"')}
        </div>
        <div class="data-import-pending-list"></div>
        <pre class="data-import-result hidden" aria-live="polite"></pre>
      </div>
      <div class="arap-modal-actions">
        ${iconBtn(t("dataImportRun"), "database", "btn action-btn", 'data-import-act="run"')}
        ${iconBtn(t("cancel"), "cancel", "btn secondary", 'data-import-act="cancel"')}
      </div>
    </div>`;
    document.body.appendChild(overlay);

    // 每次重新開啟 DO_DATAIMPORT：一律用伺服器規格預設（S:\Share\docBiz\Transfer），
    // 不沿用 localStorage 舊路徑；使用者在本次對話內手動改資料夾仍可記憶於 folderByKind。
    const folderByKind = {};
    const folderInput = overlay.querySelector(".data-import-folder-input");
    const getFolder = () => (folderInput?.value || "").trim();
    const rememberFolder = (kind) => {
      const k = String(kind || "").trim().toUpperCase();
      if (k) {
        folderByKind[k] = getFolder();
        saveImportFolder(k, getFolder());
      }
    };
    const kindSelect = overlay.querySelector(".data-import-kind-select");
    const currentKind = () => {
      const v = kindSelect?.value || "";
      return v || kinds[0]?.kind || "";
    };

    const initialKind = currentKind();
    if (folderInput) {
      folderInput.value = defaultFolder || "";
    }
    if (defaultFolder) {
      for (const k of kinds) {
        const key = String(k.kind || "").trim().toUpperCase();
        if (key) folderByKind[key] = defaultFolder;
      }
      if (initialKind) saveImportFolder(initialKind, defaultFolder);
    }

    const openFolderBrowser = async () => {
      const start = getFolder();
      let browsePath = start; // 目前列出的目錄
      let curPath = start; // 「使用此資料夾」的目標
      const parentOfPath = (p) => {
        const s = String(p || "").replace(/[\\/]+$/, "");
        if (!s) return "";
        const idx = Math.max(s.lastIndexOf("\\"), s.lastIndexOf("/"));
        if (idx < 0) return "";
        // Windows 磁碟根目錄：S:\
        if (/^[A-Za-z]:$/i.test(s.slice(0, idx))) {
          return s.slice(0, idx + 1);
        }
        if (idx === 0) return s[0] === "/" ? "/" : "";
        return s.slice(0, idx);
      };
      const picker = document.createElement("div");
      picker.className = "arap-modal-overlay data-import-folder-picker-overlay";
      picker.innerHTML = `<div class="arap-modal data-import-folder-picker" role="dialog" aria-modal="true">
        <div class="arap-modal-header"><h2>${escapeHtml(t("dataImportFolderPick"))}</h2></div>
        <div class="arap-modal-body">
          <p class="data-import-folder-picker-path"></p>
          <p class="data-import-folder-picker-status"></p>
          <div class="data-import-folder-picker-list"></div>
        </div>
        <div class="arap-modal-actions">
          ${iconBtn(t("dataImportFolderUp"), "nav-prev", "btn secondary btn-sm", 'data-folder-act="up"')}
          ${iconBtn(t("dataImportFolderUse"), "dialog-ok", "btn action-btn", 'data-folder-act="use"')}
          ${iconBtn(t("cancel"), "cancel", "btn secondary", 'data-folder-act="cancel"')}
        </div>
      </div>`;
      document.body.appendChild(picker);
      const pathEl = picker.querySelector(".data-import-folder-picker-path");
      const statusEl = picker.querySelector(".data-import-folder-picker-status");
      const listEl = picker.querySelector(".data-import-folder-picker-list");
      const upBtn = picker.querySelector('[data-folder-act="up"]');
      const closePicker = () => picker.remove();

      const updateUpButton = (parent) => {
        const canUp = !!(parent && parent !== browsePath);
        if (upBtn) {
          upBtn.disabled = !canUp;
          upBtn.title = canUp
            ? parent
            : currentLang === "CHN"
              ? "已到最上層"
              : "Already at top";
        }
        picker._parentPath = canUp ? parent : "";
      };

      const renderBrowse = async (path) => {
        try {
          const q = path ? `?path=${encodeURIComponent(path)}` : "";
          const res = await api(`/work/${encodeURIComponent(tab.doProc)}/import/folders${q}`);
          browsePath = res.path || path || "";
          curPath = browsePath;
          const parent = (res.parent || "").trim() || parentOfPath(browsePath);
          updateUpButton(parent);
          if (pathEl) pathEl.textContent = browsePath;
          if (statusEl) {
            statusEl.textContent = res.has_transfer
              ? `${t("dataImportFolderHasDb")}: ${res.transfer_path || ""}`
              : t("dataImportFolderNoDb");
            statusEl.classList.toggle("ok", !!res.has_transfer);
          }
          const folders = res.folders || [];
          if (!listEl) return;
          // 注意：即使沒有子資料夾，也必須先設好 parent，否則「上一層」會失效
          if (!folders.length) {
            listEl.innerHTML = `<p class="data-import-pending-empty">${escapeHtml(
              currentLang === "CHN" ? "沒有子資料夾（仍可使用此資料夾或上一層）" : "No subfolders (you can still use this folder or go up)"
            )}</p>`;
            return;
          }
          listEl.innerHTML = folders
            .map(
              (f) =>
                `<button type="button" class="data-import-folder-pick-item" data-path="${escapeHtml(f)}">${escapeHtml(
                  f
                )}</button>`
            )
            .join("");
          listEl.querySelectorAll(".data-import-folder-pick-item").forEach((btn) => {
            btn.addEventListener("dblclick", () => renderBrowse(btn.dataset.path || ""));
            btn.addEventListener("click", () => {
              listEl.querySelectorAll(".data-import-folder-pick-item").forEach((b) => b.classList.remove("selected"));
              btn.classList.add("selected");
              // 單擊只選定「使用」目標；列出的目錄不變，上一層仍對 browsePath
              curPath = btn.dataset.path || browsePath;
              if (pathEl) {
                pathEl.textContent = `${browsePath}\n→ ${curPath}`;
              }
            });
          });
        } catch (e) {
          showAlert(e.message || t("dataImportFail"));
        }
      };

      picker.querySelector('[data-folder-act="cancel"]')?.addEventListener("click", closePicker);
      upBtn?.addEventListener("click", () => {
        const parent = picker._parentPath || parentOfPath(browsePath);
        if (parent && parent !== browsePath) {
          renderBrowse(parent);
        }
      });
      picker.querySelector('[data-folder-act="use"]')?.addEventListener("click", () => {
        if (folderInput) folderInput.value = curPath || browsePath || "";
        rememberFolder(currentKind());
        closePicker();
        refreshPending();
      });
      picker.addEventListener("click", (e) => {
        if (e.target === picker) closePicker();
      });
      await renderBrowse(start);
    };

    const refreshPending = async () => {
      const kind = currentKind();
      rememberFolder(kind);
      const host = overlay.querySelector(".data-import-pending-list");
      if (host) {
        host.innerHTML = `<p class="data-import-pending-empty">${escapeHtml(t("dataImportReloading"))}</p>`;
      }
      try {
        const pending = await loadDataImportPending(tab.doProc, kind, getFolder());
        if (pending.folder && folderInput && !getFolder()) folderInput.value = pending.folder;
        if (pending.folder) saveImportFolder(kind, pending.folder || getFolder());
        renderDataImportPendingList(overlay, pending, kind);
        const listHost = overlay.querySelector(".data-import-pending-list");
        listHost?.querySelectorAll("tbody tr[data-import-key]").forEach((tr) => {
          tr.addEventListener("click", (e) => {
            if (e.target.closest("input.import-pending-cb")) return;
            const cb = tr.querySelector("input.import-pending-cb");
            if (cb) cb.checked = !cb.checked;
          });
        });
      } catch (e) {
        const errHost = overlay.querySelector(".data-import-pending-list");
        if (errHost) errHost.innerHTML = `<p class="data-import-pending-empty">${escapeHtml(e.message)}</p>`;
      }
    };

    kindSelect?.addEventListener("change", () => {
      const kind = currentKind();
      const remembered = folderByKind[String(kind || "").toUpperCase()];
      if (remembered != null && folderInput) folderInput.value = remembered;
      refreshPending();
    });
    folderInput?.addEventListener("change", () => {
      rememberFolder(currentKind());
      refreshPending();
    });
    folderInput?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        rememberFolder(currentKind());
        refreshPending();
      }
    });
    overlay.querySelector('[data-import-act="browse-folder"]')?.addEventListener("click", () => {
      openFolderBrowser().catch((e) => showAlert(e?.message || String(e)));
    });
    overlay.querySelector('[data-import-act="apply-folder"]')?.addEventListener("click", () => {
      rememberFolder(currentKind());
      refreshPending();
    });
    overlay.querySelector('[data-import-act="reload"]')?.addEventListener("click", () => {
      rememberFolder(currentKind());
      refreshPending();
    });
    overlay.querySelector('[data-import-act="select-all"]')?.addEventListener("click", () => {
      overlay.querySelectorAll(".import-pending-cb").forEach((cb) => {
        cb.checked = true;
      });
    });
    overlay.querySelector('[data-import-act="select-none"]')?.addEventListener("click", () => {
      overlay.querySelectorAll(".import-pending-cb").forEach((cb) => {
        cb.checked = false;
      });
    });
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeDataImportModal();
    });
    overlay.querySelector('[data-import-act="cancel"]').addEventListener("click", closeDataImportModal);
    overlay.querySelector('[data-import-act="run"]').addEventListener("click", async () => {
      const kind = currentKind();
      if (!kind) return;
      const detail = kinds.find((x) => x.kind === kind);
      const maps = detail?.detail || kind;
      const selectedKeys = Array.from(overlay.querySelectorAll(".import-pending-cb:checked"))
        .map((cb) => cb.value)
        .filter(Boolean);
      const folder = getFolder();
      rememberFolder(kind);
      if ((kind === "PURCHASE" || kind === "INVOICE") && !selectedKeys.length) {
        showAlert(t("dataImportSelectRows"));
        return;
      }
      const extra =
        selectedKeys.length > 0
          ? currentLang === "CHN"
            ? `\n\n已選 ${selectedKeys.length} 筆主檔。\n來源資料夾：${folder || "(預設)"}`
            : `\n\n${selectedKeys.length} header row(s) selected.\nFolder: ${folder || "(default)"}`
          : currentLang === "CHN"
            ? `\n\n來源資料夾：${folder || "(預設)"}`
            : `\n\nFolder: ${folder || "(default)"}`;
      if (
        !confirm(
          currentLang === "CHN"
            ? `確定執行「${kind}」匯入？\n\n${maps}${extra}`
            : `Run import for「${kind}」?\n\n${maps}${extra}`
        )
      ) {
        return;
      }
      const resultEl = overlay.querySelector(".data-import-result");
      if (resultEl) {
        resultEl.textContent = currentLang === "CHN" ? "處理中…" : "Processing…";
        resultEl.classList.remove("hidden");
      }
      try {
        const res = await api(`/work/${encodeURIComponent(tab.doProc)}/import/run`, {
          method: "POST",
          body: JSON.stringify({ kind, selected_keys: selectedKeys, folder }),
        });
        const logLines = Array.isArray(res.progress_log) ? res.progress_log.filter(Boolean) : [];
        const msg =
          res.message ||
          (logLines.length ? logLines.join("\n") : "") ||
          (res.ok ? t("dataImportSuccess") : t("dataImportFail"));
        if (resultEl) {
          resultEl.textContent = msg;
          resultEl.classList.remove("hidden");
        }
        if (res.ok) {
          showCopyableMessage(t("dataImportTitle"), msg);
          await refreshPending();
        } else {
          showCopyableMessage(t("dataImportFail"), msg);
          await refreshPending();
        }
      } catch (e) {
        const errMsg = e.message || t("dataImportFail");
        if (resultEl) {
          resultEl.textContent = errMsg;
          resultEl.classList.remove("hidden");
        }
        showAlert(errMsg);
      }
    });
    await refreshPending();
  }

  function closeDataImportModal() {
    const el = $("#data-import-modal-overlay");
    if (el) el.remove();
  }

  async function doOther(tab) {
    if (isDataImportTab(tab)) {
      await openDataImportModal(tab);
      return;
    }
    const wa = tabWorkActions(tab);
    const ot = String(wa.other_title || "");
    const otU = ot.toUpperCase();
    const isQueryTitle = ot.includes("查詢") || otU.includes("QUERY");

    if (await openQueryForWorkTab(tab, {})) return;
    if (isQueryTitle) {
      showAlert(t("queryUnsupported"));
      return;
    }
    if (isReceiptPaymentTab(tab)) {
      await openReceiptPaymentModal(tab);
      return;
    }
    if (isArapSettlementTab(tab)) {
      await openArapModal(tab);
      return;
    }
    showAlert(t("otherNotConfigured"));
  }

  async function doFilter(tab, page) {
    tab.keyword = $(".search-input", page).value.trim();
    await loadWorkData(tab, { asFilter: true });
    tab.selectedRow = tab.rows.length ? 0 : null;
    renderTabs();
  }

  async function doDelete(tab) {
    if (tab.selectedRow == null) {
      showAlert(t("selectRow"));
      return;
    }
    if (!confirm(t("confirmDel"))) return;
    const oldRow = tab.physicalRows[tab.selectedRow];
    try {
      await api(`/work/${encodeURIComponent(tab.doProc)}/delete`, {
        method: "DELETE",
        body: JSON.stringify({ old_row: oldRow }),
      });
      tab.selectedRow = null;
      await loadWorkData(tab, { asFilter: tab.filtered });
      renderTabs();
    } catch (e) {
      showAlert(e.message || t("delFail"));
    }
  }

  async function doRefreshWorkData(tab) {
    try {
      await loadWorkData(tab, {
        asFilter: !!tab.filtered,
        preserveAnchor: true,
        anchorRow:
          tab.selectedRow != null && tab.physicalRows
            ? tab.physicalRows[tab.selectedRow]
            : null,
      });
      renderTabs();
    } catch (e) {
      showAlert(e && e.message ? e.message : String(e));
    }
  }

  function doPrint(tab) {
    if (!tab.rows.length) {
      showAlert(t("noPrint"));
      return;
    }
    openPrintModal(tab);
  }

  let printModalState = null;
  let printPreviewState = null;

  function ensurePrintPreviewOverlay() {
    let el = $("#print-preview-overlay");
    if (el) return el;
    el = document.createElement("div");
    el.id = "print-preview-overlay";
    el.className = "print-preview-overlay hidden";
    el.innerHTML = `<div class="print-preview-panel" role="dialog" aria-modal="true">
      <div class="print-preview-header">
        <h3 class="print-preview-title"></h3>
        <div class="print-preview-header-actions">
          <div class="print-preview-pdf-nav hidden">
            ${iconBtnOnly(t("navPrev"), "nav-prev", "btn secondary btn-icon-only", 'data-preview-act="prev"')}
            <span class="print-preview-pdf-index"></span>
            ${iconBtnOnly(t("navNext"), "nav-next", "btn secondary btn-icon-only", 'data-preview-act="next"')}
          </div>
          ${iconBtn(t("printPreviewOpenWindow"), "window-new", "btn secondary", 'data-preview-act="window"')}
          ${iconBtn(t("printPreviewClose"), "window-close", "btn secondary", 'data-preview-act="close"')}
        </div>
      </div>
      <iframe class="print-preview-frame" title="Print preview"></iframe>
    </div>`;
    document.body.appendChild(el);
    el.addEventListener("click", (e) => {
      if (e.target === el) closePrintPreview();
    });
    $(".print-preview-title", el).textContent = t("printPreviewTitle");
    el.querySelector('[data-preview-act="window"]').addEventListener("click", () => {
      openPrintPreviewInNewWindow();
    });
    el.querySelector('[data-preview-act="close"]').addEventListener("click", closePrintPreview);
    el.querySelector('[data-preview-act="prev"]').addEventListener("click", () => {
      shiftPrintPreviewPdf(-1);
    });
    el.querySelector('[data-preview-act="next"]').addEventListener("click", () => {
      shiftPrintPreviewPdf(1);
    });
    return el;
  }

  function revokePrintPreviewBlobUrls() {
    if (!printPreviewState || !printPreviewState.blobUrls) return;
    printPreviewState.blobUrls.forEach((url) => {
      try {
        URL.revokeObjectURL(url);
      } catch (_) {
        /* ignore */
      }
    });
  }

  function renderPrintPreviewPdfAt(index) {
    if (!printPreviewState || printPreviewState.kind !== "pdf-list") return;
    const overlay = $("#print-preview-overlay");
    const frame = overlay.querySelector(".print-preview-frame");
    const nav = overlay.querySelector(".print-preview-pdf-nav");
    const idxEl = overlay.querySelector(".print-preview-pdf-index");
    const total = printPreviewState.pdfs.length;
    const i = Math.max(0, Math.min(index, total - 1));
    printPreviewState.index = i;
    frame.removeAttribute("srcdoc");
    frame.src = printPreviewState.blobUrls[i];
    if (total > 1) {
      nav.classList.remove("hidden");
      idxEl.textContent = t("printPreviewPdfNav", i + 1, total);
    } else {
      nav.classList.add("hidden");
    }
  }

  function shiftPrintPreviewPdf(delta) {
    if (!printPreviewState || printPreviewState.kind !== "pdf-list") return;
    renderPrintPreviewPdfAt((printPreviewState.index || 0) + delta);
  }

  function showPrintPreviewPdfList(b64List) {
    revokePrintPreviewBlobUrls();
    const blobUrls = b64List.map((b64) => {
      const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
      const blob = new Blob([bytes], { type: "application/pdf" });
      return URL.createObjectURL(blob);
    });
    printPreviewState = {
      kind: "pdf-list",
      pdfs: b64List,
      blobUrls,
      index: 0,
      content: blobUrls[0],
    };
    const overlay = ensurePrintPreviewOverlay();
    overlay.classList.remove("hidden");
    renderPrintPreviewPdfAt(0);
  }

  function closePrintPreview() {
    const el = $("#print-preview-overlay");
    if (!el) return;
    const frame = el.querySelector(".print-preview-frame");
    if (frame) {
      frame.removeAttribute("src");
      frame.removeAttribute("srcdoc");
    }
    revokePrintPreviewBlobUrls();
    printPreviewState = null;
    el.classList.add("hidden");
  }

  function showPrintPreview(content, kind) {
    revokePrintPreviewBlobUrls();
    const overlay = ensurePrintPreviewOverlay();
    const frame = overlay.querySelector(".print-preview-frame");
    const nav = overlay.querySelector(".print-preview-pdf-nav");
    if (nav) nav.classList.add("hidden");
    printPreviewState = { content, kind, blobUrls: [] };
    if (kind === "pdf") {
      frame.removeAttribute("srcdoc");
      frame.src = content;
      printPreviewState.blobUrls = [content];
    } else {
      frame.removeAttribute("src");
      frame.srcdoc = content;
    }
    overlay.classList.remove("hidden");
  }

  function openPrintPreviewInNewWindow() {
    if (!printPreviewState) return;
    const { content, kind, blobUrls, index } = printPreviewState;
    if (kind === "pdf-list" && blobUrls && blobUrls.length) {
      window.open(blobUrls[index || 0], "_blank", "noopener,noreferrer");
      return;
    }
    if (kind === "pdf") {
      window.open(content, "_blank", "noopener,noreferrer");
      return;
    }
    const w = window.open("", "_blank", "noopener,noreferrer");
    if (!w) {
      showAlert(t("printPreviewBlocked"));
      return;
    }
    w.document.write(content);
    w.document.close();
  }

  function syncPrintDateFromYm(state, dateText) {
    const parsed = parseAppDate(normalizeAppDateText(dateText || ""));
    state.printDateFromYm = parsed ? [parsed.y, parsed.mo] : null;
  }

  function isPrintReportListOrDocument(state) {
    return !!(state && (state.isList || state.isDocument));
  }

  function onPrintDateFromInput(body, state) {
    if (isPrintReportListOrDocument(state)) return;
    const fromEl = $("#print-date-from", body);
    if (!fromEl) return;
    fromEl.value = normalizeAppDateText(fromEl.value);
    const parsed = parseAppDate(fromEl.value);
    if (!parsed) {
      state.printDateFromYm = null;
      return;
    }
    const ymKey = `${parsed.y}-${parsed.mo}`;
    const lastKey = state.printDateFromYm
      ? `${state.printDateFromYm[0]}-${state.printDateFromYm[1]}`
      : null;
    if (ymKey === lastKey) return;
    state.printDateFromYm = [parsed.y, parsed.mo];
    const lastDay = lastDayOfMonth(parsed.y, parsed.mo);
    const toEl = $("#print-date-to", body);
    if (toEl) {
      toEl.value = `${parsed.y}/${String(parsed.mo).padStart(2, "0")}/${String(lastDay).padStart(2, "0")}`;
    }
  }

  function openPrintDatePicker(targetKey) {
    const overlay = $("#print-modal-overlay");
    if (!overlay) return;
    const inputId = targetKey === "date-to" ? "#print-date-to" : "#print-date-from";
    const targetEl = overlay.querySelector(inputId);
    if (!targetEl) return;
    openAppDatePicker(targetEl, () => {
      if (targetKey === "date-from") {
        onPrintDateFromInput(overlay.querySelector(".print-modal-body"), printModalState);
      }
    });
  }

  function getPrintParams() {
    const overlay = $("#print-modal-overlay");
    if (overlay && !overlay.classList.contains("hidden")) {
      return getPrintParamsFromModal(overlay);
    }
    if (printModalState && printModalState.init) {
      const init = printModalState.init;
      return {
        report_index: init.report_index ?? 0,
        printer_index: init.printer_index ?? 0,
        inv_from: init.inv_from || "",
        inv_to: init.inv_to || "",
        date_from: normalizeAppDateText(init.date_from || ""),
        date_to: normalizeAppDateText(init.date_to || ""),
      };
    }
    return {
      report_index: 0,
      printer_index: 0,
      inv_from: "",
      inv_to: "",
      date_from: "",
      date_to: "",
    };
  }

  function getPrintParamsFromModal(root) {
    const reportEl = root.querySelector("#print-report");
    const printerEl = root.querySelector("#print-printer");
    return {
      report_index: reportEl ? parseInt(reportEl.value, 10) || 0 : 0,
      printer_index: printerEl ? parseInt(printerEl.value, 10) || 0 : 0,
      inv_from: (root.querySelector("#print-inv-from") || {}).value || "",
      inv_to: (root.querySelector("#print-inv-to") || {}).value || "",
      date_from: normalizeAppDateText((root.querySelector("#print-date-from") || {}).value || ""),
      date_to: normalizeAppDateText((root.querySelector("#print-date-to") || {}).value || ""),
    };
  }

  function closePrintModal() {
    closePrintPreview();
    const el = $("#print-modal-overlay");
    if (el) el.remove();
    printModalState = null;
  }

  function ensurePrintModalOverlay() {
    let el = $("#print-modal-overlay");
    if (el) return el;
    el = document.createElement("div");
    el.id = "print-modal-overlay";
    el.className = "print-modal-overlay hidden";
    el.innerHTML = `<div class="print-modal" role="dialog" aria-modal="true">
      <div class="print-modal-header"><h2 class="print-modal-title"></h2></div>
      <div class="print-modal-body"></div>
      <div class="print-modal-actions"></div>
    </div>`;
    document.body.appendChild(el);
    el.addEventListener("click", (e) => {
      if (e.target !== el) return;
      const pick = $("#print-pick-overlay");
      if (pick && !pick.classList.contains("hidden")) return;
      closePrintModal();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      const pick = $("#print-pick-overlay");
      if (pick && !pick.classList.contains("hidden")) {
        pick.classList.add("hidden");
        return;
      }
      const preview = $("#print-preview-overlay");
      if (preview && !preview.classList.contains("hidden")) {
        closePrintPreview();
        return;
      }
      const modal = $("#print-modal-overlay");
      if (modal && !modal.classList.contains("hidden")) closePrintModal();
    });
    return el;
  }

  async function openPrintModal(tab) {
    try {
      const init = await api(`/work/${encodeURIComponent(tab.doProc)}/print/init`, {
        method: "POST",
        body: JSON.stringify({ selected_row: tab.selectedRow }),
      });
      printModalState = {
        tab,
        init,
        isList: !!init.is_list,
        isDocument: !!init.is_document,
        isFinance: !!init.is_finance,
        printDateFromYm: null,
      };
      syncPrintDateFromYm(printModalState, init.date_from);
      if (init.no_report) {
        showAlert(init.message || t("printNoReport"));
        await doPrintPreview();
        printModalState = null;
        return;
      }
      renderPrintModal(init);
    } catch (e) {
      showAlert(e.message || t("printPreviewFail"));
    }
  }

  function renderPrintModal(init) {
    const overlay = ensurePrintModalOverlay();
    overlay.classList.remove("hidden");
    const modal = overlay.querySelector(".print-modal");
    $(".print-modal-title", modal).textContent = t("printTitle");
    const body = $(".print-modal-body", modal);
    const docLabel = init.doc_no_label || (currentLang === "CHN" ? "記錄" : "record");
    const reportOpts = (init.reports || [])
      .map((r) => `<option value="${r.index}">${escapeHtml(r.title || "Report")}</option>`)
      .join("");
    const printerOpts = (init.printers || [])
      .map((p) => `<option value="${p.index}">${escapeHtml(p.name || "Printer")}</option>`)
      .join("");
    const reportEmptyNote =
      !(init.reports || []).length && !init.no_report
        ? `<p class="print-report-empty">${escapeHtml(t("printPreviewFail"))}</p>`
        : "";
    body.innerHTML = `
      <div class="print-form-grid">
        <label>${escapeHtml(t("printPrinter"))}</label>
        <select id="print-printer">${printerOpts}</select>
        <label>${escapeHtml(t("printReport"))}</label>
        <select id="print-report">${reportOpts || `<option value="0">${escapeHtml(currentLang === "CHN" ? "資料清單" : "Data list")}</option>`}</select>
        ${reportEmptyNote}
        <label>${escapeHtml(t("printFromNo", docLabel))}</label>
        <div class="print-field-row">
          <input type="text" id="print-inv-from" value="${escapeHtml(init.inv_from || "")}">
          ${iconBtnOnly(t("printPickBtn"), "document-open", "btn secondary print-pick-btn btn-icon-only", 'data-pick="inv-from"')}
        </div>
        <label>${escapeHtml(t("printToNo", docLabel))}</label>
        <div class="print-field-row">
          <input type="text" id="print-inv-to" value="${escapeHtml(init.inv_to || "")}">
          ${iconBtnOnly(t("printPickBtn"), "document-open", "btn secondary print-pick-btn btn-icon-only", 'data-pick="inv-to"')}
        </div>
        <label>${escapeHtml(t("printFromDate"))}</label>
        <div class="print-field-row">
          <input type="text" class="app-date-input" id="print-date-from" placeholder="yyyy/MM/dd" value="${escapeHtml(normalizeAppDateText(init.date_from || ""))}">
          ${iconBtnOnly(t("printDatePickBtn"), "view-calendar", "btn secondary print-pick-btn btn-icon-only", 'data-pick="date-from"')}
          ${iconBtnOnly(t("printClearDate"), "edit-clear", "btn secondary print-clear-btn btn-icon-only", 'data-clear="date-from"')}
        </div>
        <label>${escapeHtml(t("printToDate"))}</label>
        <div class="print-field-row">
          <input type="text" class="app-date-input" id="print-date-to" placeholder="yyyy/MM/dd" value="${escapeHtml(normalizeAppDateText(init.date_to || ""))}">
          ${iconBtnOnly(t("printDatePickBtn"), "view-calendar", "btn secondary print-pick-btn btn-icon-only", 'data-pick="date-to"')}
          ${iconBtnOnly(t("printClearDate"), "edit-clear", "btn secondary print-clear-btn btn-icon-only", 'data-clear="date-to"')}
        </div>
      </div>`;
    $("#print-printer", body).value = String(init.printer_index ?? 0);
    $("#print-report", body).value = String(init.report_index ?? 0);

    const actions = $(".print-modal-actions", modal);
    actions.innerHTML = `
      ${iconBtn(t("printPreview"), "print", "btn action-btn", 'data-print-act="preview"')}
      ${iconBtn(t("printBtn"), "document-print", "btn action-btn", 'data-print-act="print"')}
      ${iconBtn(t("printExportPdf"), "application-pdf", "btn action-btn", 'data-print-act="pdf"')}
      ${iconBtn(t("printExportXlsx"), "x-office-spreadsheet", "btn action-btn", 'data-print-act="xlsx"')}
      ${iconBtn(t("printExportDocx"), "x-office-document", "btn action-btn", 'data-print-act="docx"')}
      ${iconBtn(t("printEmail"), "mail-message", "btn action-btn", 'data-print-act="email"')}
      ${iconBtn(t("printExit"), "exit", "btn action-btn", 'data-print-act="exit"')}`;

    $("#print-report", body).addEventListener("change", async () => {
      try {
        const reportIndex = parseInt($("#print-report", body).value, 10) || 0;
        const defs = await api(
          `/work/${encodeURIComponent(printModalState.tab.doProc)}/print/defaults`,
          { method: "POST", body: JSON.stringify({ report_index: reportIndex }) }
        );
        $("#print-inv-from", body).value = defs.inv_from || "";
        $("#print-inv-to", body).value = defs.inv_to || "";
        $("#print-date-from", body).value = normalizeAppDateText(defs.date_from || "");
        $("#print-date-to", body).value = normalizeAppDateText(defs.date_to || "");
        if (printModalState) {
          printModalState.isList = !!defs.is_list;
          printModalState.isDocument = !!defs.is_document;
          printModalState.isFinance = !!defs.is_finance;
          syncPrintDateFromYm(printModalState, defs.date_from || "");
        }
      } catch (e) {
        showAlert(e.message || t("printPreviewFail"));
      }
    });

    $("#print-date-from", body).addEventListener("input", () => {
      onPrintDateFromInput(body, printModalState);
    });

    $$(".print-pick-btn", body).forEach((btn) => {
      const pick = btn.dataset.pick;
      btn.addEventListener("click", () => {
        if (pick === "date-from" || pick === "date-to") {
          openPrintDatePicker(pick);
          return;
        }
        openPrintPickModal(pick);
      });
    });
    $$(".print-clear-btn", body).forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.dataset.clear;
        const el = body.querySelector(`#print-${key}`);
        if (el) el.value = "";
        if (key === "date-from") {
          const toEl = body.querySelector("#print-date-to");
          if (toEl) toEl.value = "";
          if (printModalState) printModalState.printDateFromYm = null;
        }
      });
    });

    $$("[data-print-act]", actions).forEach((btn) => {
      btn.addEventListener("click", () => handlePrintAction(btn.dataset.printAct));
    });
  }

  async function handlePrintAction(act) {
    if (!printModalState) return;
    if (act === "exit") {
      closePrintModal();
      return;
    }
    if (act === "preview") {
      await doPrintPreview();
      return;
    }
    if (act === "print") {
      await doPrintExecute();
      return;
    }
    if (act === "pdf" || act === "xlsx" || act === "docx") {
      await doPrintExport(act);
      return;
    }
    if (act === "email") {
      await doPrintEmail();
    }
  }

  async function doPrintPreview() {
    if (!printModalState) return;
    const params = getPrintParams();
    try {
      const res = await api(
        `/work/${encodeURIComponent(printModalState.tab.doProc)}/print/preview`,
        { method: "POST", body: JSON.stringify(params) }
      );
      if (!res.ok) {
        showAlert(res.message || t("printPreviewFail"));
        return;
      }
      if (res.kind === "pdf" && res.pdfs_base64 && res.pdfs_base64.length) {
        showPrintPreviewPdfList(res.pdfs_base64);
        return;
      }
      if (res.html) {
        showPrintPreview(res.html, "html");
        return;
      }
      showAlert(res.message || t("printPreviewFail"));
    } catch (e) {
      showAlert(e.message || t("printPreviewFail"));
    }
  }

  async function doPrintExecute() {
    if (!printModalState) return;
    const params = getPrintParams();
    try {
      const res = await api(
        `/work/${encodeURIComponent(printModalState.tab.doProc)}/print/print`,
        { method: "POST", body: JSON.stringify(params) }
      );
      showAlert(t("printSuccess", res.message));
    } catch (e) {
      showAlert(e.message || t("printFail"));
    }
  }

  async function doPrintExport(kind) {
    if (!printModalState) return;
    const params = getPrintParams();
    const path = `/work/${encodeURIComponent(printModalState.tab.doProc)}/print/export/${kind}`;
    try {
      const headers = { "Content-Type": "application/json" };
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch(`/api${path}`, {
        method: "POST",
        headers,
        body: JSON.stringify(params),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(apiErrorMessage(data, t("printExportFail")));
      }
      const blob = await res.blob();
      const ext = kind === "pdf" ? "pdf" : kind === "xlsx" ? "xlsx" : "docx";
      const filename = `report.${ext}`;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 5000);
      showAlert(t("printExportOk", filename));
    } catch (e) {
      showAlert(e.message || t("printExportFail"));
    }
  }

  async function doPrintEmail() {
    if (!printModalState) return;
    const params = getPrintParams();
    try {
      const res = await api(
        `/work/${encodeURIComponent(printModalState.tab.doProc)}/print/email-text`,
        { method: "POST", body: JSON.stringify(params) }
      );
      if (!res.plain_text) {
        showAlert(t("printPreviewFail"));
        return;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(res.plain_text);
      }
      showAlert(res.hint || t("printEmailCopied"));
      const sub = encodeURIComponent(res.subject || "Report");
      const body = encodeURIComponent((res.hint || "").slice(0, 600));
      window.location.href = `mailto:?subject=${sub}&body=${body}`;
    } catch (e) {
      showAlert(e.message || t("printPreviewFail"));
    }
  }

  async function openPrintPickModal(targetKey) {
    if (!printModalState) return;
    const params = getPrintParams();
    let pickData;
    try {
      pickData = await api(
        `/work/${encodeURIComponent(printModalState.tab.doProc)}/print/pick-rows`,
        { method: "POST", body: JSON.stringify({ report_index: params.report_index }) }
      );
    } catch (e) {
      showAlert(e.message || t("printPickNoData"));
      return;
    }
    if (!pickData.rows || !pickData.rows.length) {
      showAlert(t("printPickNoData"));
      return;
    }
    const fields = pickData.fields || [];
    const columns = pickData.columns || fields.map((f) => ({ name: f, title: f }));
    let pickOverlay = $("#print-pick-overlay");
    if (!pickOverlay) {
      pickOverlay = document.createElement("div");
      pickOverlay.id = "print-pick-overlay";
      pickOverlay.className = "print-pick-overlay hidden";
      document.body.appendChild(pickOverlay);
      pickOverlay.addEventListener("click", (e) => {
        if (e.target === pickOverlay) pickOverlay.classList.add("hidden");
      });
    }
    document.body.appendChild(pickOverlay);
    pickOverlay.classList.remove("hidden");
    const currentVal = (
      (targetKey === "inv-to"
        ? overlay.querySelector("#print-inv-to")
        : overlay.querySelector("#print-inv-from")) || {}
    ).value || "";
    pickOverlay.innerHTML = `
      <div class="print-pick-modal" role="dialog" aria-modal="true">
        <h3>${escapeHtml(t("printPickRecord"))}</h3>
        <input type="text" class="print-pick-filter" placeholder="${escapeHtml(t("printPickFilter"))}">
        <div class="print-pick-table-wrap">
          <table class="print-pick-table"><thead><tr>
            ${columns.map((c) => `<th>${escapeHtml(c.title || c.name)}</th>`).join("")}
          </tr></thead><tbody></tbody></table>
        </div>
        <div class="print-pick-actions">
          ${iconBtn(t("printPickOk"), "dialog-ok", "btn action-btn", "data-pick-ok")}
          ${iconBtn(t("printPickCancel"), "cancel", "btn action-btn", "data-pick-cancel")}
        </div>
      </div>`;
    const pickModal = pickOverlay.querySelector(".print-pick-modal");
    if (pickModal) {
      pickModal.addEventListener("click", (e) => e.stopPropagation());
    }
    const tbody = pickOverlay.querySelector("tbody");
    const filterEl = pickOverlay.querySelector(".print-pick-filter");
    let filteredSnapshot = [];
    let selectedFilteredIdx = 0;
    const currentNorm = String(currentVal).trim().toLowerCase();

    function renderPickRows(kw) {
      const keyword = (kw || "").trim().toLowerCase();
      filteredSnapshot = [];
      tbody.innerHTML = "";
      let matchedCurrent = false;
      pickData.rows.forEach((row, i) => {
        const line = row.join("\t").toLowerCase();
        if (keyword && !line.includes(keyword)) return;
        const snapIdx = filteredSnapshot.length;
        filteredSnapshot.push(i);
        const tr = document.createElement("tr");
        tr.dataset.filtered = String(snapIdx);
        const keyVal = (pickData.key_values[i] || "").trim();
        if (!matchedCurrent && currentNorm && keyVal.toLowerCase() === currentNorm) {
          selectedFilteredIdx = snapIdx;
          matchedCurrent = true;
        }
        if (snapIdx === selectedFilteredIdx) tr.classList.add("selected");
        tr.innerHTML = row.map((c) => `<td>${escapeHtml(c)}</td>`).join("");
        tr.addEventListener("click", () => {
          selectedFilteredIdx = parseInt(tr.dataset.filtered, 10);
          $$("tr", tbody).forEach((r) =>
            r.classList.toggle("selected", parseInt(r.dataset.filtered, 10) === selectedFilteredIdx)
          );
        });
        tr.addEventListener("dblclick", () => confirmPick());
        tbody.appendChild(tr);
      });
      if (!filteredSnapshot.length) {
        selectedFilteredIdx = 0;
        return;
      }
      if (selectedFilteredIdx >= filteredSnapshot.length) selectedFilteredIdx = 0;
      $$("tr", tbody).forEach((r) =>
        r.classList.toggle("selected", parseInt(r.dataset.filtered, 10) === selectedFilteredIdx)
      );
    }

    function confirmPick() {
      if (!filteredSnapshot.length) return;
      const rowIdx = filteredSnapshot[selectedFilteredIdx];
      if (rowIdx == null || rowIdx < 0) return;
      const val = (pickData.key_values[rowIdx] || "").trim();
      if (!val) {
        showAlert(t("printPickNoKey"));
        return;
      }
      const mainOverlay = $("#print-modal-overlay");
      const inputId = targetKey === "inv-to" ? "#print-inv-to" : "#print-inv-from";
      const input = mainOverlay && mainOverlay.querySelector(inputId);
      if (input) input.value = val;
      pickOverlay.classList.add("hidden");
    }

    filterEl.addEventListener("input", () => {
      selectedFilteredIdx = 0;
      renderPickRows(filterEl.value);
    });
    filterEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        confirmPick();
      }
    });
    pickOverlay.querySelector("[data-pick-ok]").addEventListener("click", confirmPick);
    pickOverlay.querySelector("[data-pick-cancel]").addEventListener("click", () => {
      pickOverlay.classList.add("hidden");
    });
    renderPickRows("");
    requestAnimationFrame(() => filterEl.focus());
  }

  function syncFormFieldTabIndex(page) {
    if (!page) return;
    $$(".form-tab-panel", page).forEach((panel) => {
      const hidden = panel.classList.contains("hidden");
      $$("input, textarea, select", panel).forEach((el) => {
        if (hidden) el.setAttribute("tabindex", "-1");
        else el.removeAttribute("tabindex");
      });
    });
    $$(".tx-tab-panel", page).forEach((panel) => {
      const hidden = panel.classList.contains("hidden");
      $$("input, textarea, select, button", panel).forEach((el) => {
        if (hidden) el.setAttribute("tabindex", "-1");
        else el.removeAttribute("tabindex");
      });
    });
  }

  function getFormFieldElement(page, detail, fieldName) {
    const want = String(fieldName || "").trim().toUpperCase();
    if (!want || !page) return null;
    const nodes = page.querySelectorAll(
      ".detail-form-area input[data-field], .detail-form-area textarea[data-field], .detail-form-area select[data-field]"
    );
    for (const el of nodes) {
      if (String(el.dataset.field || "").trim().toUpperCase() === want) return el;
    }
    return null;
  }

  function getFormFocusOrder(page, detail) {
    const order = [];
    const seen = new Set();
    for (const name of detail.formFields || []) {
      const el = getFormFieldElement(page, detail, name);
      if (el && !seen.has(el)) {
        seen.add(el);
        order.push(el);
      }
    }
    if (!order.length) {
      page
        .querySelectorAll(
          ".detail-form-area input[data-field], .detail-form-area textarea[data-field], .detail-form-area select[data-field]"
        )
        .forEach((el) => {
          if (!seen.has(el)) {
            seen.add(el);
            order.push(el);
          }
        });
    }
    return order;
  }

  function formFieldOrderIndex(order, currentEl) {
    if (!currentEl) return -1;
    let idx = order.indexOf(currentEl);
    if (idx >= 0) return idx;
    const want = String(currentEl.dataset?.field || "").trim().toUpperCase();
    if (!want) return -1;
    return order.findIndex(
      (el) => String(el.dataset?.field || "").trim().toUpperCase() === want
    );
  }

  function isFormFieldControl(el) {
    if (!el || !el.dataset || !el.dataset.field) return false;
    if (!el.closest(".detail-form-area")) return false;
    const tag = el.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
  }

  function isFormNavNextKey(e) {
    return (
      e.key === "Enter" ||
      e.key === "ArrowDown" ||
      e.key === "ArrowRight" ||
      e.code === "ArrowDown" ||
      e.code === "ArrowRight"
    );
  }

  function isFormNavPrevKey(e) {
    return (
      e.key === "ArrowUp" ||
      e.key === "ArrowLeft" ||
      e.code === "ArrowUp" ||
      e.code === "ArrowLeft"
    );
  }

  function formCaretAtStart(el) {
    if (!el || el.tagName === "SELECT") return true;
    if (typeof el.selectionStart !== "number") return true;
    if (el.selectionStart !== el.selectionEnd) return false;
    return el.selectionStart <= 0;
  }

  function formCaretAtEnd(el) {
    if (!el || el.tagName === "SELECT") return true;
    if (typeof el.selectionStart !== "number") return true;
    if (el.selectionStart !== el.selectionEnd) return false;
    const len = String(el.value || "").length;
    return el.selectionEnd >= len;
  }

  function formOnFirstLine(el) {
    if (!el || el.tagName !== "TEXTAREA") return true;
    const val = String(el.value || "");
    const start = el.selectionStart ?? 0;
    return !val.slice(0, start).includes("\n");
  }

  function formOnLastLine(el) {
    if (!el || el.tagName !== "TEXTAREA") return true;
    const val = String(el.value || "");
    const end = el.selectionEnd ?? 0;
    return !val.slice(end).includes("\n");
  }

  function shouldNavigateFormField(el, e) {
    const key = e.key || e.code || "";
    if (key === "Enter") return el.tagName !== "TEXTAREA";
    if (key === "ArrowLeft") return formCaretAtStart(el);
    if (key === "ArrowRight") return formCaretAtEnd(el);
    if (key === "ArrowUp") return formOnFirstLine(el);
    if (key === "ArrowDown") return formOnLastLine(el);
    return false;
  }

  function focusFormFieldElement(page, el) {
    if (!el) return;
    activateFormTabForElement(page, el);
    requestAnimationFrame(() => {
      el.focus({ preventScroll: false });
      if (typeof el.select === "function" && el.tagName !== "SELECT") el.select();
    });
  }

  function focusFormFieldByDirection(page, detail, currentEl, direction) {
    const order = getFormFocusOrder(page, detail);
    const idx = formFieldOrderIndex(order, currentEl);
    if (idx < 0) return false;

    if (direction > 0) {
      if (idx + 1 < order.length) {
        focusFormFieldElement(page, order[idx + 1]);
        return true;
      }
      // 對齊桌面：末欄之後先進入目前 TX 明細區（搜尋框／第一儲存格），再落到儲存鈕
      if (detail.txFiles.length) {
        const activeBtn = page.querySelector(".tx-inner-tab-bar .inner-tab-btn.active[data-tx-tab]");
        const tx = (activeBtn && activeBtn.dataset.txTab) || detail.txFiles[0];
        const search = page.querySelector(`.tx-search-input[data-tx="${CSS.escape(tx)}"]`);
        if (search) {
          activateTxTabForElement(page, search);
          search.focus();
          if (typeof search.select === "function") search.select();
          return true;
        }
        const wrap = page.querySelector(`.tx-table[data-tx="${CSS.escape(tx)}"]`)?.closest(".tx-table-wrap");
        if (wrap) {
          activateTxTabForElement(page, wrap);
          wrap.focus({ preventScroll: true });
          return true;
        }
        const cell = page.querySelector(`.tx-table[data-tx="${CSS.escape(tx)}"] .tx-cell`);
        if (cell) {
          activateTxTabForElement(page, cell);
          cell.focus();
          return true;
        }
      }
      const saveBtn = page.querySelector('[data-act="save"]');
      if (saveBtn) {
        saveBtn.focus();
        return true;
      }
      return false;
    }

    if (idx > 0) {
      focusFormFieldElement(page, order[idx - 1]);
      return true;
    }
    return false;
  }

  function focusNextFormField(page, detail, currentEl) {
    return focusFormFieldByDirection(page, detail, currentEl, 1);
  }

  function focusPrevFormField(page, detail, currentEl) {
    return focusFormFieldByDirection(page, detail, currentEl, -1);
  }

  function bindLockedFieldMouseFocus(page) {
    if (!page) return;
    page
      .querySelectorAll(
        ".form-field-locked input[data-field], .form-field-locked textarea[data-field], .form-field-locked select[data-field]"
      )
      .forEach((el) => {
        if (el._lockedMouseFocusBound) return;
        el._lockedMouseFocusBound = true;
        el.addEventListener("mousedown", (e) => {
          // 唯讀欄仍可用滑鼠點擊取得 FOCUS（不阻止預設選取行為）
          if (e.button !== 0) return;
          if (document.activeElement !== el) {
            el.focus({ preventScroll: false });
          }
        });
        el.addEventListener("click", () => {
          if (document.activeElement !== el) el.focus({ preventScroll: false });
        });
      });
  }

  function setFormFieldDomLocked(page, fieldName, locked) {
    const el =
      page.querySelector(`.detail-form-area [data-field="${CSS.escape(fieldName)}"]`) ||
      page.querySelector(`[data-field="${CSS.escape(fieldName)}"]`);
    if (!el) return;
    const wrap = el.closest(".form-field");
    if (wrap) wrap.classList.toggle("form-field-locked", !!locked);
    if (el.tagName === "SELECT") {
      // 鎖定時改為 readonly 行為：不 disabled，以免失去 FOCUS
      el.disabled = false;
      el.dataset.arapLocked = locked ? "1" : "";
      if (locked) {
        el.setAttribute("aria-readonly", "true");
        if (!el._arapLockBound) {
          el._arapLockBound = true;
          el.addEventListener("mousedown", (e) => {
            if (el.dataset.arapLocked === "1") e.preventDefault();
          });
          el.addEventListener("keydown", (e) => {
            if (el.dataset.arapLocked !== "1") return;
            if (["ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown", " "].includes(e.key)) {
              e.preventDefault();
            }
          });
        }
      } else {
        el.removeAttribute("aria-readonly");
      }
    } else if (locked) {
      el.setAttribute("readonly", "");
      el.tabIndex = 0;
    } else {
      el.removeAttribute("readonly");
    }
    const dateBtn = wrap && wrap.querySelector(`.date-pick-btn[data-date-for="${CSS.escape(fieldName)}"]`);
    if (dateBtn) dateBtn.style.display = locked ? "none" : "";
    const lookupBtn = wrap && wrap.querySelector(`.lookup-btn[data-lookup-field="${CSS.escape(fieldName)}"]`);
    if (lookupBtn) lookupBtn.style.display = locked ? "none" : "";
  }

  function refreshArapVouTypeFieldLocks(page, detail) {
    if (!page || !detail || !isDoArapProc(detail)) return;
    const txEl =
      page.querySelector('.detail-form-area [data-field="TX_TYPE"]') ||
      page.querySelector('[data-field="TX_TYPE"]');
    const vouEl =
      page.querySelector('.detail-form-area [data-field="VOU_TYPE"]') ||
      page.querySelector('[data-field="VOU_TYPE"]');
    const txType = txEl
      ? String(txEl.value || "")
      : String((detail.formValues || {}).TX_TYPE || "");
    const mapped = arapVouTypeForTxType(txType);
    if (mapped && vouEl && vouEl.value !== mapped) {
      vouEl.value = mapped;
      if (detail.formValues) detail.formValues.VOU_TYPE = mapped;
    }
    if (detail.formValues) detail.formValues.TX_TYPE = txType;
    const fields = detail.formFields || [];
    fields.forEach((name) => {
      const meta = formColumnMeta(detail, name) || { name, edit_type: "" };
      const locked = formFieldForceLocked(meta, {
        detailMode: detail.mode,
        detail,
        txType,
        formValues: { ...(detail.formValues || {}), TX_TYPE: txType },
      });
      setFormFieldDomLocked(page, name, locked);
    });
    bindLockedFieldMouseFocus(page);
  }

  function bindArapVouTypeLockHooks(page, detail) {
    if (!page || !detail || !isDoArapProc(detail)) return;
    const txEl =
      page.querySelector('.detail-form-area [data-field="TX_TYPE"]') ||
      page.querySelector('[data-field="TX_TYPE"]');
    if (!txEl || txEl._arapTxLockBound) {
      refreshArapVouTypeFieldLocks(page, detail);
      return;
    }
    txEl._arapTxLockBound = true;
    const fire = () => {
      if (detail.formValues) detail.formValues.TX_TYPE = txEl.value || "";
      refreshArapVouTypeFieldLocks(page, detail);
    };
    txEl.addEventListener("input", fire);
    txEl.addEventListener("change", fire);
    txEl.addEventListener("blur", fire);
    refreshArapVouTypeFieldLocks(page, detail);
  }

  function bindDetailFormFieldNavigation(page, detail) {
    const area = $(".detail-form-area", page);
    if (!area) return;
    if (area._formNavBound) return;
    area._formNavBound = true;
    area.addEventListener(
      "keydown",
      async (e) => {
        if (e.shiftKey || e.ctrlKey || e.altKey || e.metaKey) return;
        const el = e.target;
        if (!isFormFieldControl(el)) return;
        // F4：對齊常見 ERP／桌面查找快捷鍵
        if (e.key === "F4" || e.code === "F4") {
          const fieldName = el.dataset.field || "";
          const wrapBtn = el.closest(".lookup-field-wrap")?.querySelector(".lookup-btn");
          const lookupDb = (wrapBtn && wrapBtn.dataset.lookupDb) || el.dataset.lookupDb || "";
          const lookupRet = (wrapBtn && wrapBtn.dataset.lookupRet) || el.dataset.lookupRet || fieldName;
          if (lookupDb) {
            e.preventDefault();
            e.stopPropagation();
            openLookupPicker(detail, fieldName, lookupDb, lookupRet).catch((err) => {
              showAlert(err?.message || String(err) || "Lookup failed");
            });
          }
          return;
        }
        if (!isFormNavNextKey(e) && !isFormNavPrevKey(e)) return;
        if (!shouldNavigateFormField(el, e)) return;
        // 確定要換欄時立刻攔截（await 前），避免預設游標行為搶先
        e.preventDefault();
        e.stopPropagation();
        if (isFormNavNextKey(e)) {
          const ok = await applyFormFieldSearchRet(page, detail, el);
          if (!ok) return;
          focusNextFormField(page, detail, el);
        } else {
          focusPrevFormField(page, detail, el);
        }
      },
      true
    );
  }

  function formColumnMeta(detail, fieldName) {
    const name = String(fieldName || "").toUpperCase();
    const cols = [...(detail.formColumns || []), ...(detail.columns || [])];
    return cols.find((c) => String(c.name || "").toUpperCase() === name) || null;
  }

  function fieldHasSearchRet(meta) {
    if (!meta) return false;
    const searchRet = String(meta.search_ret || "").trim();
    if (!searchRet) return false;
    if (["Y", "N", "YES", "NO", "TRUE", "FALSE", "1", "0", "-1"].includes(searchRet.toUpperCase())) {
      return false;
    }
    const lookupDb = String(meta.lookup_db || "").trim();
    const lookupKey = String(meta.lookup_key || "").trim();
    return !!(lookupDb && lookupKey);
  }

  function parseSearchRetPairs(searchRet) {
    const raw = String(searchRet || "").trim();
    if (!raw) return [];
    if (["Y", "N", "YES", "NO", "TRUE", "FALSE", "1", "0", "-1"].includes(raw.toUpperCase())) {
      return [];
    }
    const parts = raw
      .replace(/,/g, ";")
      .split(";")
      .map((s) => s.trim())
      .filter(Boolean);
    const out = [];
    for (const part of parts) {
      if (part.includes("=")) {
        const i = part.indexOf("=");
        const dest = part.slice(0, i).trim();
        const src = part.slice(i + 1).trim();
        if (dest) out.push({ dest, src });
      } else {
        out.push({ dest: part, src: "" });
      }
    }
    return out;
  }

  async function applyFormFieldSearchRet(page, detail, el) {
    if (!el || !page || !detail) return true;
    if (page._searchRetApplying) return true;
    const fieldName = el.dataset.field || el.getAttribute("name") || "";
    if (!fieldName) return true;
    const meta = formColumnMeta(detail, fieldName);
    if (!fieldHasSearchRet(meta)) return true;
    const inputVal = String(el.value || "").trim();
    if (!inputVal) return true;

    const lookupDb = String(meta.lookup_db || "").trim();
    const lookupKey = String(meta.lookup_key || "").trim();
    const pairs = parseSearchRetPairs(meta.search_ret || "");
    const doProc = detail.doProc || detail.workDoProc || "";
    if (!doProc || !lookupDb || !lookupKey || !pairs.length) return true;

    const notFound = currentLang === "CHN" ? "找不到符合的資料。" : "No matching data found.";
    let data;
    try {
      data = await api(`/work/${encodeURIComponent(doProc)}/lookup/rows`, {
        method: "POST",
        body: JSON.stringify({ lookup_db: lookupDb, keyword: "", as_filter: false }),
      });
    } catch (e) {
      showAlert(e.message || notFound);
      el.focus();
      if (typeof el.select === "function") el.select();
      return false;
    }

    const physicalFields = data.physical_fields || data.fields || [];
    const physicalRows = data.physical_rows || data.rows || [];
    const keyIdx = physicalFields.findIndex(
      (f) => String(f).toUpperCase() === lookupKey.toUpperCase()
    );
    if (keyIdx < 0) {
      showAlert(notFound);
      el.focus();
      if (typeof el.select === "function") el.select();
      return false;
    }
    const kw = inputVal.toLowerCase();
    let matchedRow = null;
    for (const row of physicalRows) {
      const cell = String(row[keyIdx] ?? "").trim();
      const low = cell.toLowerCase();
      if (low === kw || low.includes(kw)) {
        matchedRow = row;
        break;
      }
    }
    if (!matchedRow) {
      showAlert(notFound);
      el.focus();
      if (typeof el.select === "function") el.select();
      return false;
    }

    page._searchRetApplying = true;
    try {
      for (const { dest, src } of pairs) {
        const srcField = (src || lookupKey).trim();
        const srcIdx = physicalFields.findIndex(
          (f) => String(f).toUpperCase() === srcField.toUpperCase()
        );
        if (srcIdx < 0) continue;
        const value = String(matchedRow[srcIdx] ?? "").trim();
        let destEl =
          page.querySelector(`[data-field="${CSS.escape(dest)}"]`) ||
          page.querySelector(`[name="${CSS.escape(dest)}"]`);
        if (!destEl && dest.toUpperCase() === fieldName.toUpperCase()) destEl = el;
        if (!destEl) continue;
        destEl.value = value;
        destEl.dispatchEvent(new Event("change", { bubbles: true }));
        if (detail.formValues) detail.formValues[dest] = value;
      }
    } finally {
      page._searchRetApplying = false;
    }
    return true;
  }

  function bindFormSearchRetHooks(page, detail) {
    if (!page || !detail) return;
    page.querySelectorAll(".detail-form-area input[data-field], .detail-form-area textarea[data-field]").forEach((el) => {
      if (el._searchRetBound) return;
      const meta = formColumnMeta(detail, el.dataset.field || "");
      if (!fieldHasSearchRet(meta)) return;
      el._searchRetBound = true;
      el.addEventListener("blur", () => {
        applyFormFieldSearchRet(page, detail, el);
      });
    });
  }

  function refreshFormModalUI(detail) {
    const overlay = $("#form-modal-overlay");
    if (!overlay) return;
    const body = overlay.querySelector(".form-modal-body");
    if (!body) return;
    body.innerHTML = renderDetailPage(detail);
    const page = body.querySelector(".detail-page");
    bindDetailPageEvents(detail, {
      onCancel: closeFormModal,
      onSaved: closeFormModal,
      rootPage: page,
    });
    bindDateFields(page);
  }

  function bindDetailPageEvents(detail, opts = {}) {
    const page = opts.rootPage || $(`.detail-page[data-tab="${detail.id}"]`);
    if (!page) return;
    const refreshUi = () => {
      if (detail.inModal) refreshFormModalUI(detail);
      else renderTabs();
    };

    bindDetailFormFieldNavigation(page, detail);
    bindLockedFieldMouseFocus(page);
    bindArapVouTypeLockHooks(page, detail);
    bindFormTabEvents(page);
    bindTxTabEvents(page, detail);
    bindDateFields(page);
    bindLookupButtons(page, detail);
    bindFormSearchRetHooks(page, detail);
    syncFormFieldTabIndex(page);

    detail.txFiles.forEach((tx) => {
      bindTxGridColumnResize(page, detail, tx);
      bindTxGridSortHeaders(page, detail, tx);
    });

    $('[data-act="cancel"]', page)?.addEventListener("click", () => {
      if (opts.onCancel) opts.onCancel();
      else closeTab(detail.id);
    });

    $('[data-act="toggle-form-layout"]', page)?.addEventListener("click", () => {
      const cur = getFormLayoutMode();
      setFormLayoutMode(cur === FORM_LAYOUT_PLANNED ? FORM_LAYOUT_DEFAULT : FORM_LAYOUT_PLANNED);
      // 切換前保留目前輸入值
      try {
        detail.formValues = { ...(detail.formValues || {}), ...collectFormValues(page) };
        collectTxPhysicalRowsFromPage(page, detail);
      } catch (_) {}
      refreshUi();
    });

    $('[data-act="attachment"]', page)?.addEventListener("click", () => {
      doAttachmentForDetail(detail, page).catch((e) =>
        showCopyableMessage(t("attachment"), e?.message || String(e))
      );
    });

    $$(".tx-act", page).forEach((btn) => {
      btn.addEventListener("click", () => {
        const tx = btn.dataset.tx;
        const act = btn.dataset.txAct;
        const txd = detail.txData[tx];
        if (!txd) return;
        collectTxPhysicalRowsFromPage(page, detail);

        if (act === "add") {
          const formValues = collectFormValues(page);
          const mk = resolveMasterKeyForTx(detail, formValues);
          const keyCol = txKeyColOnTable(txd, mk.col);
          txd.physical_rows.push(createEmptyTxRow(txd, keyCol, mk.val));
          renumberTxItemNo(txd);
          txd.selectedRow = txd.physical_rows.length - 1;
          syncTxDisplayRows(txd);
          refreshUi();
        } else if (act === "edit") {
          if (txd.selectedRow == null) {
            showAlert(t("selectRow"));
            return;
          }
          const inp = page.querySelector(
            `.tx-table[data-tx="${CSS.escape(tx)}"] tr[data-tx-row="${txd.selectedRow}"] .tx-cell`
          );
          if (inp) inp.focus();
        } else if (act === "delete") {
          if (txd.selectedRow == null) {
            showAlert(t("selectRow"));
            return;
          }
          if (!confirm(t("confirmTxDel"))) return;
          txd.physical_rows.splice(txd.selectedRow, 1);
          renumberTxItemNo(txd);
          txd.selectedRow = txd.physical_rows.length
            ? Math.min(txd.selectedRow, txd.physical_rows.length - 1)
            : null;
          syncTxDisplayRows(txd);
          refreshUi();
        } else if (act === "copy") {
          if (txd.selectedRow == null) {
            showAlert(t("selectRow"));
            return;
          }
          const copy = [...txd.physical_rows[txd.selectedRow]];
          txd.physical_rows.splice(txd.selectedRow + 1, 0, copy);
          renumberTxItemNo(txd);
          txd.selectedRow = txd.selectedRow + 1;
          syncTxDisplayRows(txd);
          refreshUi();
        } else if (act === "move-up" || act === "move-down") {
          if (txd.selectedRow == null) {
            showAlert(t("selectRow"));
            return;
          }
          const src = txd.selectedRow;
          const dest = act === "move-up" ? src - 1 : src + 1;
          if (dest < 0 || dest >= txd.physical_rows.length) return;
          const newIdx = relocateTxRow(txd, src, dest);
          renumberTxItemNo(txd);
          txd.selectedRow = newIdx;
          txd.selectedRows = new Set([newIdx]);
          syncTxDisplayRows(txd);
          refreshUi();
        } else if (act === "search") {
          const inp = page.querySelector(`.tx-search-input[data-tx="${CSS.escape(tx)}"]`);
          const kw = ((inp && inp.value) || "").trim().toLowerCase();
          txd.keyword = kw;
          if (!kw) return;
          const idx = txd.physical_rows.findIndex((row) =>
            row.some((c) => String(c).toLowerCase().includes(kw))
          );
          if (idx >= 0) {
            selectTxRow(page, detail, tx, idx);
          }
        }
      });
    });

    $$(".tx-nav", page).forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.disabled) return;
        navigateTxGrid(page, detail, btn.dataset.tx, btn.dataset.nav);
      });
    });

    $$(".tx-table tbody tr[data-tx-row]", page).forEach((tr) => {
      tr.addEventListener("click", (e) => {
        if (e.target.closest(".tx-cell")) return;
        const tx = tr.dataset.tx;
        const ri = parseInt(tr.dataset.txRow, 10);
        const td = e.target.closest("td");
        let col = 0;
        if (td && !td.classList.contains("tx-row-gutter")) {
          const raw = parseInt(td.dataset.colIdx, 10);
          col = Number.isFinite(raw) ? raw : Math.max(0, (td.cellIndex || 1) - 1);
        }
        if (e.shiftKey) selectTxRow(page, detail, tx, ri, { mode: "range", col });
        else if (e.ctrlKey || e.metaKey) selectTxRow(page, detail, tx, ri, { mode: "toggle", col });
        else selectTxRow(page, detail, tx, ri, { col });
      });
    });
    bindTxGridRowReorder(page, detail, refreshUi);

    $$(".tx-table-wrap", page).forEach((wrap) => {
      if (wrap.dataset.clipBound) return;
      wrap.dataset.clipBound = "1";
      wrap.addEventListener("click", (e) => {
        if (!e.target.closest(".tx-cell")) wrap.focus({ preventScroll: true });
      });
      wrap.addEventListener("keydown", (e) => {
        if (e.target.closest(".tx-cell")) return;
        const table = wrap.querySelector(".tx-table[data-tx]");
        const tx = table && table.dataset.tx;
        if (!tx) return;
        const txd = detail.txData[tx];
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") {
          e.preventDefault();
          selectAllTxGridRows(page, detail, tx);
        } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c") {
          e.preventDefault();
          copyTxGridToClipboard(page, detail, tx);
        } else if (txd && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
          e.preventDefault();
          const n = (txd.physical_rows || []).length;
          if (!n) return;
          const row = txd.selectedRow;
          const noSel = row == null || row < 0 || row >= n;
          if (e.key === "ArrowDown") {
            if (noSel) selectTxRow(page, detail, tx, 0);
            else if (row < n - 1) selectTxRow(page, detail, tx, row + 1);
          } else if (!noSel && row > 0) {
            selectTxRow(page, detail, tx, row - 1);
          }
        } else if (txd && e.key === "Home") {
          e.preventDefault();
          const n = (txd.physical_rows || []).length;
          if (!n) return;
          if (txd.selectedRow == null || txd.selectedRow < 0) selectTxRow(page, detail, tx, 0, { col: 0 });
          else {
            txd.currentCol = 0;
            updateTxSelectionUi(page, tx, txd);
          }
        } else if (txd && e.key === "End") {
          e.preventDefault();
          const n = (txd.physical_rows || []).length;
          const ncols = (txd.fields || []).length;
          if (!n || !ncols) return;
          const lastCol = Math.max(0, ncols - 1);
          if (txd.selectedRow == null || txd.selectedRow < 0) selectTxRow(page, detail, tx, 0, { col: lastCol });
          else {
            txd.currentCol = lastCol;
            updateTxSelectionUi(page, tx, txd);
          }
        } else if (txd && e.key === "PageUp") {
          e.preventDefault();
          const n = (txd.physical_rows || []).length;
          if (!n) return;
          const row = txd.selectedRow == null ? 0 : txd.selectedRow;
          selectTxRow(page, detail, tx, Math.max(0, row - TX_VISIBLE_ROWS), {
            col: txd.currentCol ?? 0,
          });
        } else if (txd && e.key === "PageDown") {
          e.preventDefault();
          const n = (txd.physical_rows || []).length;
          if (!n) return;
          const row = txd.selectedRow == null ? 0 : txd.selectedRow;
          selectTxRow(page, detail, tx, Math.min(n - 1, row + TX_VISIBLE_ROWS), {
            col: txd.currentCol ?? 0,
          });
        } else if (txd && e.key === "Enter" && txd.selectedRow != null) {
          e.preventDefault();
          const inp = page.querySelector(
            `.tx-table[data-tx="${CSS.escape(tx)}"] tr[data-tx-row="${txd.selectedRow}"] .tx-cell`
          );
          if (inp) inp.focus();
        }
      });
      wrap.addEventListener("contextmenu", (e) => {
        if (e.target.closest(".tx-cell")) return;
        const table = wrap.querySelector(".tx-table[data-tx]");
        const tx = table && table.dataset.tx;
        if (!tx) return;
        handleTxGridContextMenu(e, page, detail, tx);
      });
    });

    detail.txFiles.forEach((tx) => {
      const txd = detail.txData[tx];
      if (txd) updateTxSelectionUi(page, tx, txd);
    });

    bindTxCellInputs(page, detail);

    $$(".tx-search-input", page).forEach((inp) => {
      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          const tx = inp.dataset.tx;
          const btn = page.querySelector(`.tx-act[data-tx="${CSS.escape(tx)}"][data-tx-act="search"]`);
          if (btn) btn.click();
        }
      });
    });

    const saveBtn = $('[data-act="save"]', page);
    const runSave = async () => {
      const errEl = $(".detail-error", page);
      if (errEl) errEl.classList.add("hidden");
      try {
        await persistDetailRecord(detail, page);
        if (opts.onSaved) opts.onSaved();
        else closeTab(detail.id);
      } catch (e) {
        if (errEl) {
          errEl.textContent = e.message;
          errEl.classList.remove("hidden");
        } else {
          showAlert(e.message || String(e));
        }
      }
    };
    if (saveBtn) {
      saveBtn.addEventListener("click", runSave);
      saveBtn.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          runSave();
        }
      });
    }
    bindDateFields(page);
  }

  function submitLogin() {
    login($("#login-user").value, $("#login-password").value, $("#login-company").value);
  }

  function bindLoginNavigation() {
    const userEl = $("#login-user");
    const pwEl = $("#login-password");
    const coEl = $("#login-company");
    const dtEl = $("#login-date");

    userEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        pwEl.focus();
      }
    });
    pwEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        tryLastCompany(userEl.value, pwEl.value).finally(() => coEl.focus());
      }
    });
    coEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        dtEl.focus();
      }
    });
    dtEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        submitLogin();
      }
    });
    dtEl.addEventListener("blur", () => {
      dtEl.value = normalizeAppDateText(dtEl.value);
    });
    pwEl.addEventListener("blur", () => {
      tryLastCompany(userEl.value, pwEl.value);
    });
  }

  $("#login-form").addEventListener("submit", (e) => {
    e.preventDefault();
    submitLogin();
  });
  $("#btn-login-ok").addEventListener("click", submitLogin);
  $("#btn-login-cancel").addEventListener("click", () => {
    hideLoginError();
    $("#login-user").value = "";
    $("#login-password").value = "";
    initLoginDate();
    $("#login-user").focus();
  });
  $("#btn-logout").addEventListener("click", logout);
  $("#btn-ai")?.addEventListener("click", () => openAiTab());
  $("#btn-ai-side")?.addEventListener("click", () => openAiTab());
  $("#btn-reload")?.addEventListener("click", async () => {
    try {
      await refreshMenu();
      for (const tab of openTabs.filter((x) => x.type === "work")) {
        await loadWorkData(tab, { reloadProgram: true, asFilter: !!tab.filtered });
      }
      renderTabs();
      showAlert(currentLang === "CHN" ? "已重新載入資料字典與主選單。" : "Metadata and main menu reloaded.");
    } catch (err) {
      showAlert(err.message || String(err));
    }
  });
  // 舊版 topbar 控件已併入功能表列；保留相容判斷避免找不到節點
  const menuModeSel = $("#menu-mode-select");
  if (menuModeSel) {
    menuModeSel.value = loadMenuMode();
    menuModeSel.addEventListener("change", (e) => {
      saveMenuMode(e.target.value);
      renderMenu();
    });
  }

  function bindLoginDatePicker() {
    const pickBtn = $("#btn-login-date-pick");
    const dtEl = $("#login-date");
    if (pickBtn) {
      pickBtn.innerHTML = uiIcon("view-calendar", 14);
      pickBtn.addEventListener("click", () => openAppDatePicker(dtEl));
    }
    const loginView = $("#login-view");
    if (loginView) bindDateFields(loginView);
  }

  async function init() {
    applyTheme(loadTheme());
    applyFontPtToDocument();
    initLoginDate();
    decorateChromeButtons();
    bindGlobalLookupButtons();
    bindLoginDatePicker();
    bindLoginNavigation();
    try {
      await loadCompanies();
    } catch (_) {}
    if (token && (await restoreSession())) {
      showMain();
      try {
        await refreshMenu();
        updateUserInfo();
      } catch (_) {
        logout();
      }
    } else {
      showLogin();
      $("#login-user").focus();
    }
  }

  init();
})();
