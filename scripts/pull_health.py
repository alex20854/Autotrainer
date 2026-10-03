#!/usr/bin/env python3
"""Pull workouts + daily metrics straight from the Health Auto Export app.

Health Auto Export (Premium) can run an MCP server on the iPhone, reachable on
the local network while the app is open in the foreground (Server screen).
This script speaks to it directly — deterministic, no LLM in the loop, so HR
series never pass through Claude's context — and writes the response as an
ordinary Auto Export JSON file in data/raw/health/, where parse_auto_export.py
picks it up like any other export.

Privacy: GPS routes are never requested (includeRoutes is hardcoded false) and
any location-like keys are dropped before the file is written. The bearer
token lives in the workspace's gitignored config/health_server.local.yaml:

    endpoint: http://<phone-ip>:9000/mcp
    token: <from the app's Server screen>

Window: --since/--until (YYYY-MM-DD); default since = the day before the
newest Health workout already derived (overlap is harmless: upsert never
downgrades), else lookback_days.

Usage: python3 <engine>/scripts/pull_health.py [--since D] [--until D] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import records, workspace

REPO_ROOT = workspace.root()
CONFIG_PATH = REPO_ROOT / "config" / "health_server.local.yaml"
OUT_DIR = REPO_ROOT / "data" / "raw" / "health"

LOOKBACK_DAYS = 30
TIMEOUT_S = 600
# Daily metrics worth pulling (mirrors parse_auto_export.METRIC_WHITELIST).
METRICS = "resting_heart_rate,heart_rate_variability,vo2_max"
# Keys never written to disk, at any depth: routes and coordinates.
LOCATION_KEYS = {"route", "routes", "locations", "location_data", "latitude", "longitude",
                 "lat", "lon", "lng", "coordinates", "gps"}


class PullError(RuntimeError):
    pass


def load_server_config(path: Path = CONFIG_PATH) -> tuple[str, str]:
    if not path.exists():
        raise PullError(f"missing {path} — create it with `endpoint:` and `token:` "
                        "from Health Auto Export's Server screen")
    cfg = yaml.safe_load(path.read_text()) or {}
    endpoint, token = cfg.get("endpoint"), cfg.get("token")
    if not endpoint or not token or "PASTE" in str(token):
        raise PullError(f"fill in `endpoint` and `token` in {path}")
    return str(endpoint), str(token)


def scrub_location(obj):
    """Drop route/coordinate keys at any depth. Pure; unit-tested."""
    if isinstance(obj, dict):
        return {k: scrub_location(v) for k, v in obj.items() if k.lower() not in LOCATION_KEYS}
    if isinstance(obj, list):
        return [scrub_location(v) for v in obj]
    return obj


def parse_mcp_body(body: str, content_type: str) -> dict:
    """An MCP streamable-HTTP response is JSON or an SSE stream of JSON events."""
    if "text/event-stream" in content_type:
        events = [line[5:].strip() for line in body.splitlines() if line.startswith("data:")]
        messages = [json.loads(e) for e in events if e]
        replies = [m for m in messages if "result" in m or "error" in m]
        if not replies:
            raise PullError("server sent no result in its event stream")
        return replies[-1]
    return json.loads(body)


def tool_payload(reply: dict) -> dict:
    """Unwrap tools/call result -> the app's JSON (Auto Export shape)."""
    if "error" in reply:
        raise PullError(f"server error: {reply['error'].get('message', reply['error'])}")
    result = reply.get("result") or {}
    if result.get("isError"):
        raise PullError(f"tool error: {json.dumps(result.get('content'))[:300]}")
    texts = [c.get("text", "") for c in result.get("content") or [] if c.get("type") == "text"]
    if result.get("structuredContent"):
        return result["structuredContent"]
    try:
        return json.loads("".join(texts))
    except json.JSONDecodeError as e:
        raise PullError(f"tool returned non-JSON text: {''.join(texts)[:200]!r}") from e


class McpClient:
    """Minimal MCP streamable-HTTP client: initialize, then tools/call."""

    def __init__(self, endpoint: str, token: str):
        self.endpoint, self.token, self.session, self._id = endpoint, token, None, 0

    def _post(self, message: dict, *, expect_reply: bool = True) -> dict | None:
        headers = {"Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "Authorization": f"Bearer {self.token}"}
        if self.session:
            headers["Mcp-Session-Id"] = self.session
        req = urllib.request.Request(self.endpoint, data=json.dumps(message).encode(),
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                self.session = resp.headers.get("Mcp-Session-Id") or self.session
                body = resp.read().decode("utf-8")
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            hint = {401: " (token rejected — re-copy it from the Server screen)"}.get(e.code, "")
            raise PullError(f"HTTP {e.code} from the app{hint}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            reason = str(getattr(e, "reason", e))
            if "No route to host" in reason or "Host is down" in reason:
                hint = ("the phone is not on the network at this address: screen locked "
                        "(Wi-Fi sleeps) or its address changed — wake it, check the Server "
                        "screen's endpoint")
            elif "Connection refused" in reason:
                hint = ("nothing is serving on the phone — open Health Auto Export in the "
                        "foreground on its Server screen (the server stops when backgrounded)")
            else:
                hint = ("is Health Auto Export open in the foreground on the Server screen, "
                        "on the same Wi-Fi as this Mac?")
            raise PullError(f"can't reach {self.endpoint}: {reason} — {hint}") from None
        if not expect_reply or not body.strip():
            return None
        return parse_mcp_body(body, ctype)

    def _request(self, method: str, params: dict) -> dict:
        self._id += 1
        return self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params})

    def initialize(self) -> None:
        reply = self._request("initialize", {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "autotrainer-pull-health", "version": "1"}})
        if "error" in reply:
            raise PullError(f"initialize failed: {reply['error']}")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, expect_reply=False)

    def call(self, tool: str, arguments: dict) -> dict:
        return tool_payload(self._request("tools/call", {"name": tool, "arguments": arguments}))


def default_since() -> datetime:
    health = [r for r in records.load_records() if r.get("source_kind") == "health"]
    if health:
        newest = max(records.parse_dt(r["end"]) for r in health)
        return (newest - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return datetime.now().astimezone() - timedelta(days=LOOKBACK_DAYS)


def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S %z")


def merge_payloads(workouts: dict, metrics: dict) -> dict:
    """Combine the two tool results into one Auto Export-shaped document."""
    def section(doc: dict, key: str) -> list:
        data = doc.get("data", doc)
        return data.get(key) or []
    return {"data": {"workouts": section(workouts, "workouts"),
                     "metrics": section(metrics, "metrics")}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", help="YYYY-MM-DD (default: day before newest Health workout)")
    ap.add_argument("--until", help="YYYY-MM-DD inclusive (default: now)")
    ap.add_argument("--dry-run", action="store_true", help="pull and summarize; write nothing")
    args = ap.parse_args()
    workspace.require(REPO_ROOT)
    now = datetime.now().astimezone()
    since = datetime.fromisoformat(args.since).astimezone() if args.since else default_since()
    until = (datetime.fromisoformat(args.until).astimezone() + timedelta(days=1, seconds=-1)) \
        if args.until else now
    try:
        endpoint, token = load_server_config()
        client = McpClient(endpoint, token)
        client.initialize()
        print(f"pull-health: {since:%Y-%m-%d} -> {until:%Y-%m-%d %H:%M} from the app...", flush=True)
        workouts = client.call("get_workouts", {
            "start": fmt(since), "end": fmt(until), "includeMetadata": True,
            "includeRoutes": False,             # never: location must not leave the phone
            "metadataAggregation": "seconds"})
        metrics = client.call("get_health_metrics", {
            "start": fmt(since), "end": fmt(until), "metrics": METRICS,
            "interval": "days", "aggregate": True})
    except PullError as e:
        print(f"pull-health: {e}", file=sys.stderr)
        return 1

    doc = scrub_location(merge_payloads(workouts, metrics))
    n_w, n_m = len(doc["data"]["workouts"]), len(doc["data"]["metrics"])
    with_hr = sum(bool(w.get("heartRateData")) for w in doc["data"]["workouts"])
    print(f"pull-health: {n_w} workouts ({with_hr} with HR series), {n_m} metric series")
    if args.dry_run:
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"mcp-pull-{since:%Y%m%d}-{until:%Y%m%d}-{now:%Y%m%dT%H%M%S}.json"
    out.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    print(f"pull-health: wrote {out.relative_to(REPO_ROOT)} — run ingest to parse it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
