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
        lambda m: f"&lt;{'/' if m.group(0).startswith('</') else ''}"
        f"{m.group(1)}{m.group(2) or ''}&gt;",
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

    return {
        "raw_text": text,
        "tool": tool.strip(),
        "is_fuzzy": is_fuzzy,
        "code": extract_tag(text, "code", fuzzy),
        "path": extract_tag(text, "path", fuzzy),
        "url": extract_tag(text, "url", fuzzy),
        "query": extract_tag(text, "query", fuzzy),
        "old": extract_tag(text, "old", fuzzy),
        "new": extract_tag(text, "new", fuzzy),
        "question": extract_tag(text, "question", fuzzy),
        "pattern": extract_tag(text, "pattern", fuzzy),
        "glob": extract_tag(text, "glob", fuzzy),
        "output_mode": extract_tag(text, "output_mode", fuzzy),
        "context": extract_tag(text, "context", fuzzy),
        "head_limit": extract_tag(text, "head_limit", fuzzy),
        "start_line": extract_tag(text, "start_line", fuzzy),
        "end_line": extract_tag(text, "end_line", fuzzy),
        "tail": extract_tag(text, "tail", fuzzy),
        "instruction": extract_tag(text, "instruction", fuzzy),
        "system_prompt": extract_tag(text, "system_prompt", fuzzy),
        "model": extract_tag(text, "model", fuzzy),
        "background": extract_tag(text, "background", fuzzy),
        "id": extract_tag(text, "id", fuzzy),
        "input": extract_tag(text, "input", fuzzy),
        "name": extract_tag(text, "name", fuzzy),
        "description": extract_tag(text, "description", fuzzy),
        "prompt": extract_tag(text, "prompt", fuzzy),
        "skill": extract_tag(text, "skill", fuzzy),
        "members": extract_tag(text, "members", fuzzy),
        "server": extract_tag(text, "server", fuzzy),
        "args": extract_tag(text, "args", fuzzy),
        "text": extract_tag(text, "text", fuzzy),
        "action": extract_tag(text, "action", fuzzy),
        "section": extract_tag(text, "section", fuzzy),
        "old_text": extract_tag(text, "old_text", fuzzy),
        "new_text": extract_tag(text, "new_text", fuzzy),
        "selector": extract_tag(text, "selector", fuzzy),
        "patches": (
            parse_multi_patch(text)
            if tool.strip() == "multi_patch_file"
            else None
        ),
    }


_extract_tag = extract_tag
_has_tool_call = has_tool_call
_parse_multi_patch = parse_multi_patch
_parse_tool_call = parse_tool_call
_sanitize_tool_result = sanitize_tool_result
