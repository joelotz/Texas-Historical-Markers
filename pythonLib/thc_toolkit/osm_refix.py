"""Batch-push ref:US-TX:thc corrections into JOSM via Remote Control.

Each fix becomes a ``/load_object?objects=n<id>&addtags=ref:US-TX:thc=<value>``
call so JOSM loads the existing OSM node and stages the tag change for human
review. The user reviews each batch in JOSM and clicks Upload to commit.

A sidecar state JSON tracks which OSM IDs have already been pushed so the
workflow is resumable across invocations.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests

DEFAULT_JOSM_ENDPOINT = "http://localhost:8111"
REQUIRED_PLAN_COLS = ("id", "correct_ref")


def load_plan(path: str | os.PathLike) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED_PLAN_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"plan missing required columns: {missing}")
    df["id"] = df["id"].astype("Int64")
    df["correct_ref"] = df["correct_ref"].astype("Int64")
    if df["id"].isna().any() or df["correct_ref"].isna().any():
        raise ValueError("plan has rows with NA in id or correct_ref")
    return df


def load_state(path: str | os.PathLike) -> dict:
    p = Path(path)
    if not p.exists():
        return {"pushed": {}}
    with open(p) as f:
        data = json.load(f)
    data.setdefault("pushed", {})
    return data


def save_state(path: str | os.PathLike, state: dict) -> None:
    with open(path, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


@dataclass
class PushResult:
    osm_id: int
    correct_ref: int
    ok: bool
    status: int | None
    body: str


def push_one(
    osm_id: int,
    correct_ref: int,
    endpoint: str = DEFAULT_JOSM_ENDPOINT,
    timeout: float = 10.0,
    session: requests.Session | None = None,
    dry_run: bool = False,
) -> PushResult:
    url = f"{endpoint.rstrip('/')}/load_object"
    params = {
        "objects": f"n{int(osm_id)}",
        "addtags": f"ref:US-TX:thc={int(correct_ref)}",
        "new_layer": "false",
        "relation_members": "false",
    }
    if dry_run:
        return PushResult(osm_id=int(osm_id), correct_ref=int(correct_ref),
                          ok=True, status=None, body="<dry-run>")
    http = session or requests
    r = http.get(url, params=params, timeout=timeout)
    return PushResult(
        osm_id=int(osm_id),
        correct_ref=int(correct_ref),
        ok=(r.status_code == 200),
        status=r.status_code,
        body=r.text[:300],
    )


def run_batch(
    plan: pd.DataFrame,
    state_path: str | os.PathLike,
    batch_size: int = 25,
    rate_limit_sec: float = 0.4,
    endpoint: str = DEFAULT_JOSM_ENDPOINT,
    dry_run: bool = False,
    log=print,
) -> dict:
    """Push the next ``batch_size`` unpushed rows from ``plan`` into JOSM.

    Returns a summary dict with counts and the IDs touched in this run.
    The state file at ``state_path`` is updated incrementally — rerun the
    same command to push the next batch.
    """
    state = load_state(state_path)
    pushed_ids = {int(k) for k in state["pushed"].keys()}

    pending = plan[~plan["id"].astype(int).isin(pushed_ids)]
    log(f"[INFO] plan total: {len(plan)}  pushed so far: {len(pushed_ids)}  "
        f"pending: {len(pending)}")
    if len(pending) == 0:
        log("[OK] nothing to do — all plan rows already pushed")
        return {"ok": 0, "fail": 0, "pushed_ids": [], "pending_remaining": 0}

    batch = pending.head(batch_size)
    log(f"[INFO] pushing batch of {len(batch)} "
        f"(dry_run={dry_run}, rate_limit={rate_limit_sec}s)")

    session = None if dry_run else requests.Session()
    ok_ids: list[int] = []
    fail_ids: list[int] = []
    for _, row in batch.iterrows():
        osm_id = int(row["id"])
        correct_ref = int(row["correct_ref"])
        res = push_one(
            osm_id, correct_ref,
            endpoint=endpoint, session=session, dry_run=dry_run,
        )
        if res.ok:
            ok_ids.append(osm_id)
            if not dry_run:
                state["pushed"][str(osm_id)] = {
                    "correct_ref": correct_ref,
                    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
            log(f"  [OK]   n{osm_id}  →  ref:US-TX:thc={correct_ref}")
        else:
            fail_ids.append(osm_id)
            log(f"  [FAIL] n{osm_id}  status={res.status}  {res.body[:120]}")
        if rate_limit_sec and not dry_run:
            time.sleep(rate_limit_sec)

    if not dry_run:
        save_state(state_path, state)
    pending_remaining = len(pending) - len(batch)
    log(f"[OK] batch result: {len(ok_ids)} ok, {len(fail_ids)} failed; "
        f"{pending_remaining} still pending")
    return {
        "ok": len(ok_ids),
        "fail": len(fail_ids),
        "pushed_ids": ok_ids,
        "failed_ids": fail_ids,
        "pending_remaining": pending_remaining,
    }


def reset_state(state_path: str | os.PathLike, ids: Iterable[int] | None = None) -> int:
    """Remove ``ids`` (or all entries) from the state file. Returns count removed."""
    state = load_state(state_path)
    if ids is None:
        n = len(state["pushed"])
        state["pushed"] = {}
    else:
        keys = {str(int(i)) for i in ids}
        n = sum(1 for k in keys if k in state["pushed"])
        state["pushed"] = {k: v for k, v in state["pushed"].items() if k not in keys}
    save_state(state_path, state)
    return n
