import json

import pytest

import pull_health as ph


def test_scrub_location_drops_routes_and_coordinates_at_any_depth():
    doc = {"data": {"workouts": [{"name": "Outdoor Walk", "route": [{"lat": 1, "lon": 2}],
                                  "heartRateData": [{"qty": 120}],
                                  "meta": {"latitude": 1.0, "Longitude": 2.0, "kcal": 5}}]}}
    clean = ph.scrub_location(doc)
    w = clean["data"]["workouts"][0]
    assert "route" not in w and w["meta"] == {"kcal": 5}
    assert w["heartRateData"] == [{"qty": 120}]
    assert "lat" not in json.dumps(clean) and "latitude" not in json.dumps(clean).lower()


def test_parse_mcp_body_json_and_sse():
    reply = {"jsonrpc": "2.0", "id": 1, "result": {"content": []}}
    assert ph.parse_mcp_body(json.dumps(reply), "application/json") == reply
    sse = "event: message\ndata: " + json.dumps(reply) + "\n\n"
    assert ph.parse_mcp_body(sse, "text/event-stream") == reply
    with pytest.raises(ph.PullError):
        ph.parse_mcp_body("event: ping\n\n", "text/event-stream")


def test_tool_payload_unwraps_text_and_raises_on_errors():
    payload = {"data": {"workouts": [{"name": "Cycling"}]}}
    ok = {"result": {"content": [{"type": "text", "text": json.dumps(payload)}]}}
    assert ph.tool_payload(ok) == payload
    with pytest.raises(ph.PullError, match="tool error"):
        ph.tool_payload({"result": {"isError": True, "content": [{"type": "text", "text": "x"}]}})
    with pytest.raises(ph.PullError, match="server error"):
        ph.tool_payload({"error": {"code": -1, "message": "boom"}})


def test_merge_payloads_accepts_wrapped_or_bare_sections():
    merged = ph.merge_payloads({"data": {"workouts": [1, 2]}}, {"metrics": [3]})
    assert merged == {"data": {"workouts": [1, 2], "metrics": [3]}}


def test_config_refuses_placeholder_token(tmp_path):
    cfg = tmp_path / "health_server.local.yaml"
    cfg.write_text("endpoint: http://10.0.0.2:9000/mcp\ntoken: PASTE_TOKEN_FROM_APP_HERE\n")
    with pytest.raises(ph.PullError, match="fill in"):
        ph.load_server_config(cfg)
    with pytest.raises(ph.PullError, match="missing"):
        ph.load_server_config(tmp_path / "nope.yaml")


def test_routes_are_never_requested():
    import ast
    from pathlib import Path
    src = Path(ph.__file__).read_text()
    calls = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Dict)]
    for d in calls:
        for k, v in zip(d.keys, d.values):
            if isinstance(k, ast.Constant) and k.value == "includeRoutes":
                assert isinstance(v, ast.Constant) and v.value is False
