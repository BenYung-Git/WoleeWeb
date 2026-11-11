"""全系統共用的 AI 設定（API Key、模型、端點）。設定一次後所有使用者皆可用。"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from core.ai_assistant_service import resolve_ai_docs_root

_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_BASE = "https://api.openai.com/v1"

# (id, 中文標籤, English label)
_PRESET_MODELS: Tuple[Tuple[str, str, str], ...] = (
    ("gpt-4o-mini", "GPT-4o Mini（快速、省成本）", "GPT-4o Mini (fast, low cost)"),
    ("gpt-4o", "GPT-4o（較強）", "GPT-4o (capable)"),
    ("gpt-4.1-mini", "GPT-4.1 Mini", "GPT-4.1 Mini"),
    ("gpt-4.1", "GPT-4.1", "GPT-4.1"),
    ("gpt-4.1-nano", "GPT-4.1 Nano", "GPT-4.1 Nano"),
    ("o3-mini", "o3-mini（推理）", "o3-mini (reasoning)"),
    ("o1-mini", "o1-mini（推理）", "o1-mini (reasoning)"),
    ("deepseek-chat", "DeepSeek Chat", "DeepSeek Chat"),
    ("deepseek-reasoner", "DeepSeek Reasoner", "DeepSeek Reasoner"),
    ("qwen-plus", "通義千問 Plus", "Qwen Plus"),
    ("qwen-turbo", "通義千問 Turbo", "Qwen Turbo"),
)


def list_model_options(lang: str = "CHN") -> List[Dict[str, str]]:
    chn = str(lang or "").upper().startswith("C")
    return [
        {"id": mid, "label": label_chn if chn else label_eng}
        for mid, label_chn, label_eng in _PRESET_MODELS
    ]


def preset_model_ids() -> set:
    return {mid for mid, _, _ in _PRESET_MODELS}


def normalize_model_choice(model: str) -> str:
    m = (model or "").strip()
    return m if m else _DEFAULT_MODEL


def _settings_file(base_dir: str, user_no: str = "") -> str:
    """全系統共用設定檔（與使用者無關）。"""
    del user_no  # 保留參數以相容舊呼叫
    root = resolve_ai_docs_root(base_dir)
    return os.path.join(root, "ai_settings.json")


def _legacy_user_settings_paths(base_dir: str) -> List[str]:
    """舊版每位使用者一份的 ai_settings.json。"""
    root = resolve_ai_docs_root(base_dir)
    out: List[str] = []
    try:
        names = os.listdir(root)
    except OSError:
        return out
    for name in names:
        path = os.path.join(root, name, "ai_settings.json")
        if os.path.isfile(path):
            out.append(path)
    return out


def _read_settings_dict(path: str) -> Dict[str, str]:
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {
                "api_key": str(data.get("api_key") or "").strip(),
                "model": str(data.get("model") or "").strip(),
                "base_url": str(data.get("base_url") or "").strip(),
            }
    except Exception:
        pass
    return {}


def _migrate_legacy_user_settings(base_dir: str) -> Dict[str, str]:
    """
    若尚無全系統設定檔，從舊版使用者目錄遷移一份（優先含 API Key 者）。
    """
    best: Dict[str, str] = {}
    for path in _legacy_user_settings_paths(base_dir):
        data = _read_settings_dict(path)
        if not data:
            continue
        if data.get("api_key") and not best.get("api_key"):
            best = data
        elif not best:
            best = data
    if best:
        path = _settings_file(base_dir)
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(best, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return best


def load_ai_settings(base_dir: str, user_no: str = "") -> Dict[str, str]:
    path = _settings_file(base_dir, user_no)
    data = _read_settings_dict(path)
    if data:
        return data
    return _migrate_legacy_user_settings(base_dir)


def save_ai_settings(
    base_dir: str,
    user_no: str = "",
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    clear_api_key: bool = False,
) -> Dict[str, str]:
    """儲存全系統 AI 設定；所有登入使用者共用。"""
    cur = load_ai_settings(base_dir, user_no)
    if clear_api_key:
        cur["api_key"] = ""
    elif api_key is not None:
        key = str(api_key).strip()
        if key and not _is_masked_key_placeholder(key):
            cur["api_key"] = key
    if model is not None:
        m = str(model).strip()
        cur["model"] = m if m else _DEFAULT_MODEL
    if base_url is not None:
        u = str(base_url).strip().rstrip("/")
        cur["base_url"] = u if u else _DEFAULT_BASE
    path = _settings_file(base_dir, user_no)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cur, f, ensure_ascii=False, indent=2)
    return cur


def _is_masked_key_placeholder(key: str) -> bool:
    s = (key or "").strip()
    if not s:
        return True
    if set(s) <= {"*", "•", "·", "."}:
        return True
    return bool(re.fullmatch(r"\*+[A-Za-z0-9]{0,8}", s))


def _env_api_key() -> str:
    return (os.environ.get("WOLEE_AI_API_KEY") or os.environ.get("OPENAI_API_KEY") or "").strip()


def _env_model() -> str:
    return (os.environ.get("WOLEE_AI_MODEL") or _DEFAULT_MODEL).strip()


def _env_base_url() -> str:
    return (os.environ.get("WOLEE_AI_BASE_URL") or _DEFAULT_BASE).rstrip("/")


def resolve_llm_config(base_dir: str, user_no: str = "") -> Tuple[str, str, str, str]:
    """
    回傳 (api_key, base_url, model, source)。
    source: system | env | none
    """
    shared = load_ai_settings(base_dir, user_no)
    key = shared.get("api_key") or ""
    if key:
        model = shared.get("model") or _DEFAULT_MODEL
        base = (shared.get("base_url") or _DEFAULT_BASE).rstrip("/")
        return key, base, model, "system"
    env_key = _env_api_key()
    if env_key:
        return env_key, _env_base_url(), _env_model(), "env"
    return "", _DEFAULT_BASE, _DEFAULT_MODEL, "none"


def llm_enabled_for_user(base_dir: str, user_no: str = "") -> bool:
    key, _, _, _ = resolve_llm_config(base_dir, user_no)
    return bool(key)


def api_key_hint(key: str) -> str:
    k = (key or "").strip()
    if not k:
        return ""
    if len(k) <= 4:
        return "****"
    return "…" + k[-4:]


def settings_for_client(base_dir: str, user_no: str = "", *, lang: str = "CHN") -> Dict[str, Any]:
    shared = load_ai_settings(base_dir, user_no)
    key, _, active_model, source = resolve_llm_config(base_dir, user_no)
    saved_key = (shared.get("api_key") or "").strip()
    saved_model = shared.get("model") or _DEFAULT_MODEL
    presets = preset_model_ids()
    models = list_model_options(lang)
    if saved_model and saved_model not in presets:
        chn = str(lang or "").upper().startswith("C")
        models = models + [
            {
                "id": saved_model,
                "label": (f"目前：{saved_model}" if chn else f"Current: {saved_model}"),
            }
        ]
    return {
        "model": saved_model,
        "active_model": active_model,
        "base_url": shared.get("base_url") or _DEFAULT_BASE,
        "has_api_key": bool(key),
        "api_key_hint": api_key_hint(key) if key else "",
        # 相容舊欄位名：代表「已儲存系統共用 Key」
        "user_api_key_set": bool(saved_key),
        "llm_enabled": bool(key),
        "config_source": source,
        "default_model": _DEFAULT_MODEL,
        "default_base_url": _DEFAULT_BASE,
        "models": models,
        "allow_custom_model": True,
        "shared_system_wide": True,
    }
