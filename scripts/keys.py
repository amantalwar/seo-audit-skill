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
        print()


def cmd_set(name):
    if name not in KEYS:
        sys.exit(f"Unknown key {name}. Known keys: {', '.join(KEYS)}")
    if not sys.stdin.isatty():
        sys.exit("Run this in an interactive terminal so the key can be entered without echo. "
                 "Do not pass keys through chat or command-line arguments.")
    print(f"{name}: {KEYS[name]['purpose']}")
    print(f"Get one at {KEYS[name]['get_it']}")
    value = getpass.getpass("Paste the key (input hidden): ").strip()
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
    elif cmd == "path":
        print(KEY_FILE)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
