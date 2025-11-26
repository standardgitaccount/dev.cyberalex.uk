#!/usr/bin/env python3
import json
import os
import pathlib
import re
import subprocess
import sys

URLS_PATH = pathlib.Path("urls.json")

BANNED_SUBSTRINGS = [
    # Adult
    "porn", "xxx", "sex", "xvideos", "xnxx", "redtube", "pornhub",
    "onlyfans", "camgirl", "cam4", 
    # Gambling
    "casino", "bet365", "betfair", "poker", "slots", "bookmaker", "1xbet",
    # Basic spammy stuff (tweak as you like)
    "free-money", "giveaway", "crypto-scam",
]

MAX_CODE_LENGTH = 64


def load_json_text(path: pathlib.Path) -> tuple[str, dict]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Top-level JSON must be an object (code → URL).")
    return raw, data


def load_base_urls() -> dict | None:
    """
    Load urls.json from the base branch (e.g. origin/main) so we can
    detect attempts to modify or remove existing codes.
    """
    base_ref = os.environ.get("GITHUB_BASE_REF")
    if not base_ref:
        # Not a pull_request context, or no base ref – skip this check.
        return None

    ref = f"origin/{base_ref}:urls.json"
    try:
        result = subprocess.run(
            ["git", "show", ref],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError:
        # urls.json might not exist yet on base; nothing to compare.
        return None

    try:
        data = json.loads(result.stdout)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    return data


def main() -> int:
    try:
        raw, data = load_json_text(URLS_PATH)
    except FileNotFoundError:
        print("❌ urls.json not found in repo root.")
        return 1
    except Exception as e:
        print("❌ Failed to parse urls.json:", e)
        return 1

    errors: list[str] = []

    # ---- Canonical formatting check ----
    formatted = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)
    if not formatted.endswith("\n"):
        formatted += "\n"

    if raw != formatted:
        errors.append(
            "urls.json is not in canonical format "
            "(sorted keys, 2-space indent, trailing newline)."
        )
        print("ℹ️ Suggested canonical formatting for urls.json:")
        print()
        print(formatted)

    # ---- Validate individual entries ----
    for code, url in data.items():
        # Code validation
        if not isinstance(code, str):
            errors.append(f"Key {code!r} is not a string.")
            continue

        if code != code.lower():
            errors.append(f"Code {code!r} must be lowercase only.")

        if not re.fullmatch(r"[0-9a-z]+", code):
            errors.append(
                f"Code {code!r} must contain only 0–9 and a–z with no spaces."
            )

        if len(code) == 0:
            errors.append("Found an empty code (zero-length key).")

        if len(code) > MAX_CODE_LENGTH:
            errors.append(
                f"Code {code!r} is too long (>{MAX_CODE_LENGTH} characters)."
            )

        # URL validation
        if not isinstance(url, str):
            errors.append(f"Value for code {code!r} is not a string.")
            continue

        if not (url.startswith("http://") or url.startswith("https://")):
            errors.append(
                f"URL for code {code!r} must start with http:// or https:// "
                f"(got {url!r})."
            )

        lower_url = url.lower()
        for banned in BANNED_SUBSTRINGS:
            if banned in lower_url:
                errors.append(
                    f"URL for code {code!r} appears disallowed because it "
                    f"contains '{banned}'."
                )
                break

    # ---- Block modifying/removing existing codes ----
    base_data = load_base_urls()
    if base_data is not None:
        for code, base_url in base_data.items():
            if code not in data:
                errors.append(
                    f"Code {code!r} exists on the base branch but is missing "
