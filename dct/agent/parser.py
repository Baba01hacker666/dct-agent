"""
dct.agent.parser
XML-like tool call parsing and tool-result sanitization helpers.
"""

from __future__ import annotations

import re
from typing import Optional

from dct.core.config import Config

KNOWN_FUZZY_TOOLS = [
    "run_bash",
    "run_shell",
    "run_python",
    "read_file",
    "write_file",
    "patch_file",
]


def sanitize_tool_result(result: str) -> str:
    """Escape XML-like content in tool results to prevent prompt injection."""
    return re.sub(
        r"</?(\w+)(\s[^>]*)?>",
        lambda m: (
            f"&lt;{'/' if m.group(0).startswith('</') else ''}"
            f"{m.group(1)}{m.group(2) or ''}&gt;"
        ),
        result,
    )


def extract_tag(text: str, tag: str, fuzzy: bool = False) -> Optional[str]:
    m = re.search(
        rf"<{tag}(?:\s+[^>]*)?>(.*?)</{tag}>",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    if fuzzy:
        if tag == "code":
            m_md = re.search(r"```[a-zA-Z]*\n(.*?)```", text, re.DOTALL)
            if m_md:
                return m_md.group(1).strip()
        m_fuz = re.search(
            rf"<{tag}(?:\s+[^>]*)?>(.*?)(?:<\w+>|$)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if m_fuz:
            return m_fuz.group(1).strip()

    return None


def has_tool_call(text: str) -> bool:
    if re.search(
        r"<tool(?:\s+[^>]*)?>(.+?)</tool>",
        text,
        re.DOTALL | re.IGNORECASE,
    ):
        return True

    if Config().get("enable_approx_parser", False):
        if re.search(
            r"<(?:tool|action)(?:\s+name=[\"']([^\"']+)[\"'])?",
            text,
            re.IGNORECASE,
        ):
            return True
        if "[TOOL]" in text or "```xml" in text:
            return True
    return False


def parse_multi_patch(text: str) -> list[dict[str, str]]:
    """Parse multiple <patch> blocks containing <old> and <new>."""
    patches = []
    for patch_match in re.finditer(
        r"<patch>(.*?)</patch>", text, re.DOTALL | re.IGNORECASE
    ):
        patch_content = patch_match.group(1)
        old = extract_tag(patch_content, "old")
        new = extract_tag(patch_content, "new")
        if old is not None and new is not None:
            patches.append({"old": old, "new": new})
    return patches


def parse_tool_call(text: str) -> Optional[dict]:
    """Extract the first tool call from model output."""
    fuzzy = Config().get("enable_approx_parser", False)

    tool = extract_tag(text, "tool", fuzzy=False)
    is_fuzzy = False

    if not tool and fuzzy:
        m1 = re.search(
            r"<(?:tool|action)(?:\s+name=[\"']([^\"']+)[\"'])?",
            text,
            re.IGNORECASE,
        )
        if m1 and m1.group(1):
            tool = m1.group(1)
            is_fuzzy = True
        else:
            m2 = re.search(r"\[TOOL\]\s*([a-zA-Z0-9_]+)", text)
            if m2:
                tool = m2.group(1)
                is_fuzzy = True
            else:
                for known_tool in KNOWN_FUZZY_TOOLS:
                    if f"<{known_tool}" in text:
                        tool = known_tool
                        is_fuzzy = True
                        break

    if not tool:
        return None

    result = {
        "raw_text": text,
        "tool": tool.strip(),
        "is_fuzzy": is_fuzzy,
    }

    # Pre-fill all expected keys with None
    keys = [
        "code",
        "path",
        "url",
        "query",
        "old",
        "new",
        "question",
        "pattern",
        "glob",
        "output_mode",
        "context",
        "head_limit",
        "start_line",
        "end_line",
        "tail",
        "instruction",
        "system_prompt",
        "model",
        "background",
        "id",
        "input",
        "name",
        "description",
        "prompt",
        "skill",
        "members",
        "server",
        "args",
        "text",
        "action",
        "section",
        "old_text",
        "new_text",
        "selector",
    ]
    for k in keys:
        result[k] = None

    # Single pass for well-formed tags
    for match in re.finditer(
        r"<([a-zA-Z0-9_]+)(?:\s+[^>]*)?>(.*?)</\1>", text, re.DOTALL | re.IGNORECASE
    ):
        tag_name = match.group(1).lower()
        if tag_name in result:
            result[tag_name] = match.group(2).strip()

    # Fallback for fuzzy matching
    if fuzzy:
        if result["code"] is None:
            m_md = re.search(r"```[a-zA-Z]*\n(.*?)```", text, re.DOTALL)
            if m_md:
                result["code"] = m_md.group(1).strip()

        for k in keys:
            if result[k] is None:
                m_fuz = re.search(
                    rf"<{k}(?:\s+[^>]*)?>(.*?)(?:<\w+>|$)",
                    text,
                    re.DOTALL | re.IGNORECASE,
                )
                if m_fuz:
                    result[k] = m_fuz.group(1).strip()

    result["patches"] = (
        parse_multi_patch(text) if tool.strip() == "multi_patch_file" else None
    )
    return result


_extract_tag = extract_tag
_has_tool_call = has_tool_call
_parse_multi_patch = parse_multi_patch
_parse_tool_call = parse_tool_call
_sanitize_tool_result = sanitize_tool_result
