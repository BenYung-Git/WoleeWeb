from __future__ import annotations

from typing import Literal, Optional

LanguageCode = Literal["CHN", "ENG"]

# GROUP_LEVEL <= 3 可顯示完整路徑供診斷；> 3 僅顯示簡短訊息。
ATTACH_FOLDER_VISIBLE_MAX_LEVEL = 3


def user_may_see_attach_folder(group_level: Optional[int]) -> bool:
    if group_level is None:
        return False
    return group_level <= ATTACH_FOLDER_VISIBLE_MAX_LEVEL


def format_attach_not_found_message(
    lang: LanguageCode,
    key_value: str,
    folder: str,
    group_level: Optional[int],
    *,
    folder_missing: bool = False,
) -> str:
    if user_may_see_attach_folder(group_level):
        if folder_missing:
            if lang == "CHN":
                return (
                    f"附件目錄不存在或無法存取（請確認路徑對應 attachment_path_map）：\n{folder}"
                )
            return (
                f"Attachment folder missing or inaccessible "
                f"(check attachment_path_map):\n{folder}"
            )
        if lang == "CHN":
            return (
                f"在以下目錄找不到符合「{key_value}」的附件：\n{folder}"
                if key_value
                else f"在以下目錄找不到附件：\n{folder}"
            )
        if key_value:
            return f'No attachment matching "{key_value}" in:\n{folder}'
        return f"No attachment found in:\n{folder}"
    if lang == "CHN":
        return "找不到附件。"
    return "Attachment not found."
