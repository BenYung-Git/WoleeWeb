/**
 * Web UI 圖示 — 鍵名與 core/ui_icon_map.py ICON_MAP 一致。
 * 導覽、列印、字體等延伸鍵見 EXTRA_ICONS；舊 Freedesktop 名稱經 LEGACY_ALIAS 對應。
 */
(function (global) {
  "use strict";

  /** 與 Python ICON_MAP 同步（維護時兩邊一併更新） */
  const ICON_MAP_KEYS = [
    "alter_structure",
    "create_table",
    "copy_table",
    "delete_table",
    "rename_table",
    "convert_db",
    "add",
    "edit",
    "delete",
    "copy",
    "print",
    "exit",
    "save",
    "cancel",
    "search",
    "filter",
    "connect",
    "table",
    "database",
    "theme",
    "menu",
    "language",
    "attachment",
    "other",
    "ai",
  ];

  const SVG = {
    listDetails:
      '<path d="M3 4h10M3 8h10M3 12h6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><rect x="2" y="2" width="12" height="12" rx="1.2" stroke="currentColor" stroke-width="1.1" fill="none"/>',
    folderNew:
      '<path d="M2 4.5h4.5L8 6h6v7.5H2V4.5z" stroke="currentColor" stroke-width="1.2" fill="none" stroke-linejoin="round"/><path d="M8 9v4M6 11h4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>',
    saveDisk:
      '<rect x="3" y="2" width="10" height="12" rx="1" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M5 2v3h6V2M5 10h6" stroke="currentColor" stroke-width="1.1"/><rect x="6" y="6" width="4" height="3" stroke="currentColor" stroke-width="1" fill="none"/>',
    trash:
      '<path d="M3 4.5h10M5.5 4.5V3.5h5v1M6 4.5v8M10 4.5v8M4.5 4.5l.5 8.5h6.5l.5-8.5" stroke="currentColor" stroke-width="1.1" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
    refresh:
      '<path d="M13 8a5 5 0 1 1-1.5-3.6" stroke="currentColor" stroke-width="1.2" fill="none" stroke-linecap="round"/><path d="M13 3v3h-3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    printInfo:
      '<rect x="3" y="2" width="10" height="4" rx=".8" stroke="currentColor" stroke-width="1.1" fill="none"/><rect x="4" y="6" width="8" height="7" rx=".8" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M6 9h4M6 11h2" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><circle cx="11.5" cy="11.5" r="2.2" stroke="currentColor" stroke-width="1" fill="none"/><path d="M13 13l1.5 1.5" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>',
    close:
      '<rect x="2.5" y="2.5" width="11" height="11" rx="1.2" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>',
    cancel:
      '<circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.2" fill="none"/><path d="M6 6l4 4M10 6l-4 4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>',
    listFilter:
      '<path d="M2 3h12M2 6.5h12M2 10h12M2 13.5h8" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>',
    netDrive:
      '<ellipse cx="8" cy="10" rx="5.5" ry="2.2" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M4.5 10V6.5a3.5 3.5 0 0 1 7 0V10" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M6 6.5h4" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
    file:
      '<path d="M4 2h5l3 3v9H4V2z" stroke="currentColor" stroke-width="1.1" fill="none" stroke-linejoin="round"/><path d="M9 2v3h3" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
    database:
      '<ellipse cx="8" cy="5" rx="5" ry="2" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M3 5v6c0 1.1 2.2 2 5 2s5-.9 5-2V5" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M3 8c0 1.1 2.2 2 5 2s5-.9 5-2" stroke="currentColor" stroke-width="1.1" fill="none"/>',
    desktop:
      '<rect x="2" y="3" width="12" height="8" rx="1" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M5 14h6M8 11v3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>',
    menuBtn:
      '<rect x="3" y="2" width="10" height="12" rx="1" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M6 6h4M6 8.5h4M6 11h2" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>',
    computer:
      '<rect x="2" y="3" width="12" height="8" rx="1" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M5 14h6M8 11v3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>',
  };

  const ICONS = {
    alter_structure: SVG.listDetails,
    create_table: SVG.folderNew,
    copy_table: SVG.saveDisk,
    delete_table: SVG.trash,
    rename_table: SVG.listDetails,
    convert_db: SVG.refresh,
    add: SVG.folderNew,
    edit: SVG.listDetails,
    delete: SVG.trash,
    copy: SVG.saveDisk,
    print: SVG.printInfo,
    exit: SVG.close,
    save: SVG.saveDisk,
    cancel: SVG.cancel,
    search: SVG.listDetails,
    filter: SVG.listFilter,
    connect: SVG.netDrive,
    table: SVG.file,
    database: SVG.database,
    theme: SVG.desktop,
    menu: SVG.menuBtn,
    language: SVG.computer,
    attachment: SVG.file,
    other: SVG.listDetails,
    ai: '<rect x="2" y="3.5" width="12" height="8.5" rx="1.5" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M6 12.5 8 11l2 1.5" stroke="currentColor" stroke-width="1.1" fill="none" stroke-linejoin="round"/><circle cx="6" cy="8" r=".8" fill="currentColor"/><circle cx="10" cy="8" r=".8" fill="currentColor"/><path d="M8 2.2v1.2" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
  };

  const EXTRA_ICONS = {
    "nav-first":
      '<path d="M3 4 7 8 3 12M8 4v8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    "nav-prev":
      '<path d="M10 4 6 8l4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    "nav-next":
      '<path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    "nav-last":
      '<path d="M13 4 9 8l4 4M8 4v8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    "dialog-ok":
      '<circle cx="8" cy="8" r="6" stroke="currentColor" stroke-width="1.2" fill="none"/><path d="M5.2 8.1 7.1 10l3.7-4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    "format-font-size-decrease":
      '<path d="M4 12h5M6.5 12V4M11 12h1.5M14 12h-3l1.5-2 1.5 2z" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    "format-font-size-increase":
      '<path d="M4 12h5M6.5 12V4M11 9v6M9.5 12h3l1.5-2 1.5 2z" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    "document-print":
      '<rect x="3" y="2" width="10" height="4" rx=".8" stroke="currentColor" stroke-width="1.1" fill="none"/><rect x="4" y="6" width="8" height="7" rx=".8" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M6 9h4M6 11h2" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
    "window-new":
      '<rect x="2.5" y="4" width="8" height="9" rx="1" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M8 2.5H13.5V8M13.5 2.5 9 7" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    "window-close": SVG.close,
    "document-open":
      '<path d="M2.5 4.5h4.2L8 6.2h5.5v7.3H2.5V4.5z" stroke="currentColor" stroke-width="1.1" fill="none" stroke-linejoin="round"/><path d="M6 9.5h4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>',
    "view-calendar":
      '<rect x="2.5" y="3.5" width="11" height="10" rx="1" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M2.5 6.5h11M5.5 2v2M10.5 2v2M5 9h2M9 9h2M5 11.5h2" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
    "edit-clear":
      '<circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M6 6l4 4M10 6l-4 4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>',
    "application-pdf":
      '<path d="M4 2h5l3 3v9H4V2z" stroke="currentColor" stroke-width="1.1" fill="none" stroke-linejoin="round"/><path d="M9 2v3h3M6 10h4" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
    "x-office-spreadsheet":
      '<rect x="3" y="2" width="10" height="12" rx="1" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M3 6h10M3 9h10M7 2v12M10 2v12" stroke="currentColor" stroke-width="1"/>',
    "x-office-document":
      '<path d="M4 2h5l3 3v9H4V2z" stroke="currentColor" stroke-width="1.1" fill="none" stroke-linejoin="round"/><path d="M9 2v3h3M6 7h4M6 9.5h4M6 12h2.5" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>',
    "mail-message":
      '<rect x="2" y="4" width="12" height="9" rx="1" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M2 5.5 8 9.5l6-4" stroke="currentColor" stroke-width="1.1" fill="none"/>',
    ai:
      '<rect x="2" y="3.5" width="12" height="8.5" rx="1.5" stroke="currentColor" stroke-width="1.1" fill="none"/><path d="M6 12.5 8 11l2 1.5" stroke="currentColor" stroke-width="1.1" fill="none" stroke-linejoin="round"/><circle cx="6" cy="8" r=".8" fill="currentColor"/><circle cx="10" cy="8" r=".8" fill="currentColor"/><path d="M8 2.2v1.2" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>',
  };

  const LEGACY_ALIAS = {
    "system-search": "search",
    "view-filter": "filter",
    "list-add": "add",
    "folder-new": "add",
    "document-edit": "edit",
    "view-list-details": "edit",
    "edit-delete": "delete",
    "edit-copy": "copy",
    "document-print-preview": "print",
    "application-exit": "exit",
    "document-save": "save",
    "dialog-cancel": "cancel",
    "view-refresh": "convert_db",
    computer: "language",
    "system-log-out": "exit",
    "x-office-document-menu": "menu",
    "system-users": "edit",
    "dialog-password": "filter",
    "office-building": "database",
    package: "table",
    basket: "add",
    "view-pim-tasks": "edit",
    "x-office-spreadsheet": "x-office-spreadsheet",
    "x-office-document": "x-office-document",
    "preferences-system": "theme",
    "server-database": "database",
    "applications-system": "menu",
  };

  const DEFAULT_ICON_KEY = "menu";

  function resolveIconKey(name) {
    const n = name || "";
    if (ICONS[n]) return n;
    if (LEGACY_ALIAS[n]) return LEGACY_ALIAS[n];
    return n;
  }

  function uiIcon(name, size) {
    const px = size || 16;
    const key = resolveIconKey(name);
    const body =
      ICONS[key] || EXTRA_ICONS[key] || EXTRA_ICONS[name] || ICONS[DEFAULT_ICON_KEY];
    return `<svg class="ui-icon" xmlns="http://www.w3.org/2000/svg" width="${px}" height="${px}" viewBox="0 0 16 16" fill="none" aria-hidden="true">${body}</svg>`;
  }

  global.uiIcon = uiIcon;
  global.ICON_MAP_KEYS = ICON_MAP_KEYS;
  global.resolveUiIconKey = resolveIconKey;
})(typeof window !== "undefined" ? window : globalThis);
