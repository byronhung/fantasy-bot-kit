"""Push notifications via ntfy.sh (free, no account).

You install the ntfy app and subscribe to NTFY_TOPIC. The topic name is the
only 'password', so it's long and random and kept in .env / GitHub secrets.

Dedupe without a database: every alert carries a key as an ntfy tag, and before
sending we ask ntfy for the topic's last day of messages. Same key -> skip.
"""
from __future__ import annotations

import hashlib
import json
import os
import urllib.request


def _topic() -> str:
    return os.environ["NTFY_TOPIC"]


def push(message: str, title: str = "Fantasy bot", priority: str = "default", tags: str = "basketball",
         click: str | None = None) -> None:
    """click: URL opened when the notification is tapped, also shown as an 'Open report' button."""
    click = click or os.environ.get("REPORT_URL") or None
    headers = {"Title": title.encode("utf-8").decode("latin-1"), "Priority": priority, "Tags": tags}
    if click:
        headers["Click"] = click
        headers["Actions"] = f"view, Open report, {click}"
    req = urllib.request.Request(
        f"https://ntfy.sh/{_topic()}",
        data=message.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    urllib.request.urlopen(req, timeout=20).read()


def recent_keys(since: str = "24h") -> set[str]:
    req = urllib.request.Request(f"https://ntfy.sh/{_topic()}/json?poll=1&since={since}")
    keys = set()
    try:
        body = urllib.request.urlopen(req, timeout=20).read().decode("utf-8")
    except Exception:
        return keys
    for line in body.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        for t in ev.get("tags") or []:
            if t.startswith("k-"):
                keys.add(t)
    return keys


def alert_key(text: str) -> str:
    return "k-" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def push_once(alerts: list[str], title: str, priority: str = "high") -> list[str]:
    """Send each alert line not already sent in the last 24 h, batched into one push."""
    seen = recent_keys()
    fresh = [(a, alert_key(a)) for a in alerts if alert_key(a) not in seen]
    if not fresh:
        return []
    tags = ",".join(["rotating_light"] + [k for _, k in fresh])
    push("\n\n".join(a for a, _ in fresh), title=title, priority=priority, tags=tags)
    return [a for a, _ in fresh]
