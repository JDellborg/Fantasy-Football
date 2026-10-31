"""Prints the shape of FPL-family API responses (used to add new game types).

    python scripts/explore.py URL [URL ...]
"""

import json
import sys
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (compatible; office-fpl-weekly/1.0)"


def shape(value, depth=0, max_depth=4):
    pad = "  " * depth
    if isinstance(value, dict):
        if depth >= max_depth:
            return f"{{…{len(value)} keys}}"
        lines = []
        for k, v in list(value.items())[:40]:
            lines.append(f"{pad}  {k}: {shape(v, depth + 1, max_depth)}")
        return "{\n" + "\n".join(lines) + f"\n{pad}}}"
    if isinstance(value, list):
        if not value:
            return "[]"
        return f"[{len(value)} items] first= " + shape(value[0], depth + 1, max_depth)
    text = json.dumps(value)
    return text if len(text) < 80 else text[:77] + "…"


for url in sys.argv[1:]:
    print("=" * 100)
    print(url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
        print("HTTP 200")
        try:
            print(shape(json.loads(body)))
        except json.JSONDecodeError:
            print("NOT JSON:", body[:300])
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read()[:200])
    except Exception as e:  # noqa: BLE001
        print("ERROR", e)
