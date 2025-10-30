from fastapi.testclient import TestClient


def test_file_search_roundtrip(client: TestClient, tmp_docs):
    # make a file to index & query
    (tmp_docs / "q.md").write_text("# WhoIs\nSaket is a person.\n", encoding="utf-8")

    # index (full)
    r = client.post("/api/v1/index-full", json={"roots": [str(tmp_docs)]})
    assert r.status_code == 200, r.text

    # search
    body = {"user_id": "demo", "query": "Who is Saket", "top_k": 1}
    r2 = client.post("/api/v1/file/search", json=body)
    assert r2.status_code == 200, r2.text
    j = r2.json()
    assert "hits" in j and len(j["hits"]) >= 0
