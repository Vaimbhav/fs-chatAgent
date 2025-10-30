from fastapi.testclient import TestClient


def test_web_search_exa_used(client: TestClient, monkeypatch):
    async def fake_exa(q, top_n, include_text):
        return [
            {"title": "A", "url": "https://a", "snippet": "exa", "source": "exa", "text": "body"}  # list[dict]
        ]
    async def fake_serper(q, top_n):
        raise RuntimeError("should not call serper when exa succeeds")

    import agent_app.main as m
    monkeypatch.setattr(m, "_exa_search", fake_exa, raising=True)
    monkeypatch.setattr(m, "_serper_search", fake_serper, raising=True)
    monkeypatch.setattr(m, "_maybe_scrape", lambda results, top_n: (results, []), raising=True)

    r = client.get("/api/v1/web/search?engine=exa&q=test&data=true&top_n=2&user_id=demo")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["engine"] == "exa"
    assert j["results"][0]["source"] == "exa"


def test_web_search_fallback_to_serper(client: TestClient, monkeypatch):
    async def fail_exa(q, top_n, include_text):
        raise RuntimeError("exa down")
    async def ok_serper(q, top_n):
        return [
            {"title": "S", "url": "https://s", "snippet": "serper", "source": "serper"}
        ]

    import agent_app.main as m
    monkeypatch.setattr(m, "_exa_search", fail_exa, raising=True)
    monkeypatch.setattr(m, "_serper_search", ok_serper, raising=True)
    monkeypatch.setattr(m, "_maybe_scrape", lambda results, top_n: (results, []), raising=True)

    r = client.get("/api/v1/web/search?engine=exa|serper&query=test&user_id=demo")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["engine"] == "serper"
    assert j["attempt_errors"] and j["attempt_errors"][0]["engine"] == "exa"
