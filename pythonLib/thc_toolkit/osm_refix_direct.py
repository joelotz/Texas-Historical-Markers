"""Push ref:US-TX:thc corrections directly to OSM (no JOSM review step).

Uses the OAuth2 access token JOSM already stored after the user signed in.
Each batch opens its own changeset, bulk-fetches current node state,
modifies only the ``ref:US-TX:thc`` tag, uploads as an osmChange diff,
and closes the changeset. State is tracked in the same JSON file as the
JOSM-staging workflow so the two modes share a single source of truth on
"which refs have been handled."
"""

from __future__ import annotations

import html
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd
import requests

from .osm_refix import load_state, save_state

DEFAULT_API_ENDPOINT = "https://api.openstreetmap.org/api/0.6"
DEFAULT_JOSM_PREFS = "~/.config/JOSM/preferences.xml"
DEFAULT_USER_AGENT = "thc-toolkit/0.1 (joelotz@gmail.com)"
JOSM_OAUTH_KEY = "oauth.access-token.object.OAuth20.api.openstreetmap.org"

CHANGESET_TAGS = {
    "created_by": "thc-toolkit/0.1",
    "comment": (
        "Fix incorrect ref:US-TX:thc tag values to match official THC Atlas "
        "marker IDs (atlas.thc.texas.gov); cross-verified with HMDB.org."
    ),
    "source": "atlas.thc.texas.gov; hmdb.org",
    "bot": "yes",
}


def read_josm_oauth_token(prefs_path: str | os.PathLike | None = None) -> str:
    p = Path(prefs_path or DEFAULT_JOSM_PREFS).expanduser()
    root = ET.parse(p).getroot()
    for el in root.iter():
        local = el.tag.rsplit("}", 1)[-1]
        if local != "tag":
            continue
        if el.get("key") == JOSM_OAUTH_KEY:
            data = json.loads(el.get("value", "{}"))
            token = data.get("access_token")
            if not token:
                raise ValueError(f"OAuth entry in {p} has no access_token")
            return token
    raise ValueError(f"No JOSM OAuth2 access token found in {p}")


def make_session(token: str, user_agent: str = DEFAULT_USER_AGENT) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {token}",
        "User-Agent": user_agent,
    })
    return s


def _xe(s: str) -> str:
    return html.escape(s, quote=True)


def fetch_nodes_bulk(
    node_ids: list[int],
    session: requests.Session,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout: float = 30.0,
) -> dict[int, dict]:
    """GET /nodes?nodes=… returns {id: {version, lat, lon, tags}}."""
    if not node_ids:
        return {}
    ids_param = ",".join(str(i) for i in node_ids)
    r = session.get(f"{endpoint}/nodes", params={"nodes": ids_param}, timeout=timeout)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out: dict[int, dict] = {}
    for node in root.findall("node"):
        nid = int(node.get("id"))
        out[nid] = {
            "version": int(node.get("version")),
            "lat": node.get("lat"),
            "lon": node.get("lon"),
            "tags": {t.get("k"): t.get("v") for t in node.findall("tag")},
        }
    return out


def open_changeset(
    session: requests.Session,
    endpoint: str = DEFAULT_API_ENDPOINT,
    tags: dict | None = None,
    timeout: float = 30.0,
) -> int:
    tags = tags or CHANGESET_TAGS
    body = (
        "<osm><changeset>"
        + "".join(f'<tag k="{_xe(k)}" v="{_xe(v)}"/>' for k, v in tags.items())
        + "</changeset></osm>"
    )
    r = session.put(
        f"{endpoint}/changeset/create",
        data=body.encode(),
        headers={"Content-Type": "text/xml"},
        timeout=timeout,
    )
    r.raise_for_status()
    return int(r.text.strip())


def close_changeset(
    session: requests.Session,
    changeset_id: int,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout: float = 30.0,
) -> None:
    r = session.put(f"{endpoint}/changeset/{changeset_id}/close", timeout=timeout)
    r.raise_for_status()


def build_osmchange(updates: list[dict], changeset_id: int) -> bytes:
    parts = ['<osmChange version="0.6" generator="thc-toolkit"><modify>']
    for u in updates:
        attrs = (
            f'id="{u["node_id"]}" version="{u["version"]}" '
            f'changeset="{changeset_id}" lat="{u["lat"]}" lon="{u["lon"]}"'
        )
        parts.append(f"<node {attrs}>")
        for k, v in u["tags"].items():
            parts.append(f'<tag k="{_xe(k)}" v="{_xe(v)}"/>')
        parts.append("</node>")
    parts.append("</modify></osmChange>")
    return "".join(parts).encode()


def upload_diff(
    session: requests.Session,
    changeset_id: int,
    osmchange: bytes,
    endpoint: str = DEFAULT_API_ENDPOINT,
    timeout: float = 60.0,
) -> str:
    r = session.post(
        f"{endpoint}/changeset/{changeset_id}/upload",
        data=osmchange,
        headers={"Content-Type": "text/xml"},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.text


def run_batch_direct(
    plan: pd.DataFrame,
    state_path: str | os.PathLike,
    batch_size: int = 10,
    rate_limit_sec: float = 1.0,
    endpoint: str = DEFAULT_API_ENDPOINT,
    prefs_path: str | os.PathLike | None = None,
    changeset_tags: dict | None = None,
    dry_run: bool = False,
    log=print,
) -> dict:
    state = load_state(state_path)
    pushed_ids = {int(k) for k in state["pushed"].keys()}
    pending = plan[~plan["id"].astype(int).isin(pushed_ids)]
    log(f"[INFO] plan total: {len(plan)}  done so far: {len(pushed_ids)}  "
        f"pending: {len(pending)}")
    if len(pending) == 0:
        log("[OK] nothing to do — all plan rows already done")
        return {"ok": 0, "fail": 0, "pushed_ids": [], "pending_remaining": 0}

    batch = pending.head(batch_size)
    log(f"[INFO] direct-push batch of {len(batch)} "
        f"(dry_run={dry_run}, rate_limit={rate_limit_sec}s)")

    if dry_run:
        for _, row in batch.iterrows():
            log(f"  [DRY] would set n{int(row['id'])} ref:US-TX:thc="
                f"{int(row['correct_ref'])}")
        return {
            "ok": len(batch),
            "fail": 0,
            "pushed_ids": [int(r) for r in batch["id"]],
            "pending_remaining": len(pending) - len(batch),
        }

    token = read_josm_oauth_token(prefs_path)
    session = make_session(token)
    cs_tags = changeset_tags or CHANGESET_TAGS

    node_ids = [int(r) for r in batch["id"]]
    fetched = fetch_nodes_bulk(node_ids, session, endpoint=endpoint)
    missing = [i for i in node_ids if i not in fetched]
    for i in missing:
        log(f"  [SKIP] n{i}: not present in OSM (deleted or wrong id)")

    updates: list[dict] = []
    for _, row in batch.iterrows():
        nid = int(row["id"])
        if nid not in fetched:
            continue
        node = fetched[nid]
        new_tags = dict(node["tags"])
        new_tags["ref:US-TX:thc"] = str(int(row["correct_ref"]))
        updates.append({
            "node_id": nid,
            "version": node["version"],
            "lat": node["lat"],
            "lon": node["lon"],
            "tags": new_tags,
            "correct_ref": int(row["correct_ref"]),
        })

    if not updates:
        log("[WARN] no upload-able nodes in this batch; advancing state for missing")
        for i in missing:
            state["pushed"][str(i)] = {
                "skipped": True,
                "reason": "not_found_in_osm",
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        save_state(state_path, state)
        return {
            "ok": 0, "fail": len(missing), "pushed_ids": [],
            "failed_ids": missing, "pending_remaining": len(pending) - len(batch),
        }

    cs_id = open_changeset(session, endpoint=endpoint, tags=cs_tags)
    log(f"[INFO] changeset opened: {cs_id} "
        f"(https://www.openstreetmap.org/changeset/{cs_id})")
    try:
        osc = build_osmchange(updates, cs_id)
        upload_diff(session, cs_id, osc, endpoint=endpoint)
        log(f"[OK] uploaded {len(updates)} node modifications "
            f"to changeset {cs_id}")
    finally:
        close_changeset(session, cs_id, endpoint=endpoint)
        log(f"[OK] changeset {cs_id} closed")

    ok_ids = [u["node_id"] for u in updates]
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for u in updates:
        state["pushed"][str(u["node_id"])] = {
            "correct_ref": u["correct_ref"],
            "changeset": cs_id,
            "mode": "direct",
            "ts": ts,
        }
    for i in missing:
        state["pushed"][str(i)] = {
            "skipped": True, "reason": "not_found_in_osm", "ts": ts,
        }
    save_state(state_path, state)

    if rate_limit_sec:
        time.sleep(rate_limit_sec)

    pending_remaining = len(pending) - len(batch)
    log(f"[OK] batch done: {len(ok_ids)} ok, {len(missing)} skipped; "
        f"{pending_remaining} still pending")
    return {
        "ok": len(ok_ids),
        "fail": len(missing),
        "pushed_ids": ok_ids,
        "failed_ids": missing,
        "changeset_id": cs_id,
        "pending_remaining": pending_remaining,
    }
