import json
from pathlib import Path

from fastapi.testclient import TestClient
from agent_app.config import SETTINGS


def _make_basic_files(d: Path):
    # Text-ish
    (d / "a.txt").write_text("alpha bravo", encoding="utf-8")
    (d / "b.md").write_text("# head\ncharlie delta", encoding="utf-8")
    (d / "c.json").write_text(json.dumps({"k": "echo foxtrot"}), encoding="utf-8")
    (d / "d.csv").write_text("col\nHelloIndex\n", encoding="utf-8")


def test_index_full_and_incremental(client: TestClient, tmp_docs, stub_embed_and_vs):
    _make_basic_files(tmp_docs)

    # Full reindex with explicit roots
    resp = client.post(
        "/api/v1/index-full",
        json={"roots": [str(tmp_docs)]}
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert "stats" in payload
    assert "scanned_files" in payload
    assert len(payload["scanned_files"]) >= 4
    assert payload["stats"]["upserted"] >= 1

    # Run incremental immediately; should have unchanged_files >= previous count
    resp2 = client.post(
        "/api/v1/index",
        json={"roots": [str(tmp_docs)]}
    )
    assert resp2.status_code == 200, resp2.text
    payload2 = resp2.json()
    assert "unchanged_files" in payload2
    assert len(payload2["unchanged_files"]) >= 4
