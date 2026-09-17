#!/usr/bin/env python3
"""
keys.py - Manage optional API keys for talwar-seo-audit.

The audit works with no keys at all. Keys unlock extra data:

    PAGESPEED_API_KEY   Google PageSpeed Insights - real-user Core Web Vitals (LCP/INP/CLS)
                        and Lighthouse lab scores for the homepage. Free.

Usage:
    python keys.py status                  # which keys are set, and where from
    python keys.py set PAGESPEED_API_KEY   # prompts for the value (hidden), saves to the key file
    python keys.py unset PAGESPEED_API_KEY
    python keys.py verify PAGESPEED_API_KEY  # makes one real API call to confirm the key works
    python keys.py path                    # prints the key file location

Keys are read in this order: environment variable, then ~/.talwar-seo-audit/.env,
then ./.env in the current directory. The key file is created with owner-only
permissions. Never paste a key into a chat window - run `set` in your own terminal.
"""

import getpass
import json
import os
import stat
import sys

KEYS = {
    "PAGESPEED_API_KEY": {
        "purpose": "Google PageSpeed Insights: field Core Web Vitals + Lighthouse scores for the homepage",
        "get_it": "https://developers.google.com/speed/docs/insights/v5/get-started",
        "free": True,
        # (url, params_builder) used by `verify` - a cheap real call that fails fast on a bad key
        "verify": (
            "https://www.googleapis.com/pagespeedonline/v5/runPagespeed",
            lambda key: {"url": "https://example.com/", "strategy": "desktop", "category": "seo", "key": key},
        ),
    },
}

KEY_FILE = os.path.join(os.path.expanduser("~"), ".talwar-seo-audit", ".env")
LOCAL_ENV = os.path.join(os.getcwd(), ".env")


def _parse_env_file(path):
    out = {}
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load_keys(names=None):
    """Return {name: (value, source)} for each known key, resolving env → key file → ./.env.
    Importable by other scripts: `from keys import load_keys`."""
    names = names or list(KEYS)
    file_keys = _parse_env_file(KEY_FILE)
    local_keys = _parse_env_file(LOCAL_ENV)
    result = {}
    for n in names:
        if os.environ.get(n):
            result[n] = (os.environ[n], "environment")
        elif file_keys.get(n):
            result[n] = (file_keys[n], KEY_FILE)
        elif local_keys.get(n):
            result[n] = (local_keys[n], LOCAL_ENV)
        else:
            result[n] = (None, None)
    return result


def apply_to_environ():
    """Export any file-stored keys into os.environ so downstream code just reads the env."""
    for n, (v, src) in load_keys().items():
        if v and not os.environ.get(n):
            os.environ[n] = v


def cmd_status(as_json=False):
    rows = []
    for n, meta in KEYS.items():
        v, src = load_keys([n])[n]
        rows.append({
            "key": n, "set": bool(v), "source": src,
            "masked": (v[:4] + "…" + v[-4:]) if v and len(v) > 10 else ("set" if v else None),
            "purpose": meta["purpose"], "get_it": meta["get_it"], "free": meta["free"],
        })
    if as_json:
        print(json.dumps({"keys": rows, "key_file": KEY_FILE}, indent=2))
        return
    print(f"Key file: {KEY_FILE}{'' if os.path.isfile(KEY_FILE) else '  (not created yet)'}\n")
    for r in rows:
        mark = "SET    " if r["set"] else "MISSING"
        print(f"  [{mark}] {r['key']}" + (f"  ({r['source']})" if r["set"] else ""))
        print(f"            {r['purpose']}")
        if not r["set"]:
            print(f"            Get a{' free' if r['free'] else ''} key: {r['get_it']}")
            print(f"            Then run:  python {os.path.basename(__file__)} set {r['key']}")
        else:
            print(f"            Check it works:  python {os.path.basename(__file__)} verify {r['key']}")
        print()


def _looks_like_paste_failure(value):
    # Windows consoles: Ctrl+V into a hidden prompt yields chr(22) (or nothing) instead of the clipboard
    return len(value) < 20 or any(ord(c) < 32 for c in value)


def _read_secret():
    """Prompt for a key. Hidden input first; if the paste clearly failed (a Windows
    getpass quirk with Ctrl+V), explain and fall back to a visible prompt."""
    if os.name == "nt":
        print("Tip: in a Windows console, paste into the hidden prompt with RIGHT-CLICK (Ctrl+V won't work).")
    value = getpass.getpass("Paste the key (input hidden): ").strip()
    if value and not _looks_like_paste_failure(value):
        return value
    print(f"That came through as {len(value)} character(s), so the paste did not work.")
    print("Falling back to a VISIBLE prompt - the key will show on screen. Clear your terminal afterwards.")
    try:
        value = input("Paste the key (visible): ").strip()
    except EOFError:
        return ""
    value = "".join(c for c in value if ord(c) >= 32)
    if _looks_like_paste_failure(value):
        sys.exit(f"Still only {len(value)} character(s) - not saving. API keys are typically 30-50 characters.")
    return value


def cmd_set(name):
    if name not in KEYS:
        sys.exit(f"Unknown key {name}. Known keys: {', '.join(KEYS)}")
    if not sys.stdin.isatty():
        sys.exit("Run this in an interactive terminal so the key can be entered without echo. "
                 "Do not pass keys through chat or command-line arguments.")
    print(f"{name}: {KEYS[name]['purpose']}")
    print(f"Get one at {KEYS[name]['get_it']}")
    value = _read_secret()
    if not value:
        sys.exit("Nothing entered; aborting.")
    os.makedirs(os.path.dirname(KEY_FILE), exist_ok=True)
    existing = _parse_env_file(KEY_FILE)
    existing[name] = value
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write("# talwar-seo-audit optional API keys. Keep private.\n")
        for k, v in existing.items():
            f.write(f"{k}={v}\n")
    try:
        os.chmod(KEY_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # Windows ignores POSIX bits; the file is under the user profile regardless
    print(f"Saved {name} to {KEY_FILE}")
    print("Verifying...")
    if not cmd_verify(name):
        print(f"The key is saved but did not work. Fix it and run `set` again, or `unset {name}`.")


def cmd_verify(name, quiet=False):
    """Return True if the key works. Makes one real API request."""
    if name not in KEYS:
        sys.exit(f"Unknown key {name}. Known keys: {', '.join(KEYS)}")
    value, src = load_keys([name])[name]
    if not value:
        print(f"{name} is not set. Run: python {os.path.basename(__file__)} set {name}")
        return False
    url, build = KEYS[name]["verify"]
    try:
        import requests  # only needed here; keeps `status` dependency-free
        r = requests.get(url, params=build(value), timeout=60)
        body = r.json() if r.headers.get("Content-Type", "").startswith("application/json") else {}
    except Exception as e:  # noqa: BLE001
        print(f"Could not reach the API to verify {name}: {e}")
        return False
    if r.status_code == 200 and "error" not in body:
        if not quiet:
            print(f"OK - {name} works (source: {src})")
        return True
    msg = (body.get("error") or {}).get("message") or f"HTTP {r.status_code}"
    print(f"FAILED - {name} was rejected: {msg}")
    hint = KEYS[name]["get_it"]
    if "not valid" in msg.lower():
        print("  The key itself is wrong (typo / truncated paste). Copy it again from the Google Cloud console.")
    elif "has not been used" in msg.lower() or "disabled" in msg.lower():
        print("  The key exists but the PageSpeed Insights API is not enabled on its project - enable it:")
        print("  https://console.cloud.google.com/apis/library/pagespeedonline.googleapis.com")
    elif "referer" in msg.lower() or "restricted" in msg.lower():
        print("  The key has application restrictions (HTTP referrer / IP). Remove them or create an unrestricted key.")
    print(f"  Docs: {hint}")
    return False


def cmd_unset(name):
    existing = _parse_env_file(KEY_FILE)
    if name not in existing:
        print(f"{name} was not in {KEY_FILE}")
        return
    del existing[name]
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write("# talwar-seo-audit optional API keys. Keep private.\n")
        for k, v in existing.items():
            f.write(f"{k}={v}\n")
    print(f"Removed {name} from {KEY_FILE}")


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd = args[0]
    if cmd == "status":
        cmd_status(as_json="--json" in args)
    elif cmd == "set" and len(args) > 1:
        cmd_set(args[1])
    elif cmd == "unset" and len(args) > 1:
        cmd_unset(args[1])
    elif cmd == "verify" and len(args) > 1:
        sys.exit(0 if cmd_verify(args[1]) else 1)
    elif cmd == "path":
        print(KEY_FILE)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
