import json
import pytest
from gwt.engines.deepl_engine import DeepLEngine


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append({"url": url, **kw})
        n = len(kw["json"]["text"])
        return FakeResponse({"translations": [{"text": f"EN{i}"} for i in range(n)]})

    monkeypatch.setattr("gwt.engines.deepl_engine.requests.post", fake_post)
    return calls


def test_sends_xml_tag_handling_and_ignore_tags(captured):
    DeepLEngine(api_key="k").translate(["创建用户"])
    body = captured[0]["json"]
    assert body["tag_handling"] == "xml"
    assert body["ignore_tags"] == ["x"]
    assert body["source_lang"] == "ZH"
    assert body["target_lang"] == "EN-US"


def test_masks_identifiers_before_sending(captured):
    DeepLEngine(api_key="k").translate(["调用 getUserList 方法"])
    sent = captured[0]["json"]["text"][0]
    assert "<x>getUserList</x>" in sent


def test_unmasks_response(captured, monkeypatch):
    def fake_post(url, **kw):
        return FakeResponse({"translations": [{"text": "Call <x>getUserList</x> method"}]})
    monkeypatch.setattr("gwt.engines.deepl_engine.requests.post", fake_post)
    assert DeepLEngine(api_key="k").translate(["调用 getUserList 方法"]) == [
        "Call getUserList method"]


def test_batches_at_fifty(captured):
    DeepLEngine(api_key="k", batch=50).translate([f"文本{i}" for i in range(120)])
    assert len(captured) == 3
    assert [len(c["json"]["text"]) for c in captured] == [50, 50, 20]


def test_uses_free_endpoint_for_free_key(captured):
    DeepLEngine(api_key="abc:fx").translate(["甲"])
    assert "api-free.deepl.com" in captured[0]["url"]


def test_uses_pro_endpoint_for_pro_key(captured):
    DeepLEngine(api_key="abc").translate(["甲"])
    assert captured[0]["url"].startswith("https://api.deepl.com")


def test_output_length_matches_input(captured):
    out = DeepLEngine(api_key="k").translate(["甲", "乙", "丙"])
    assert len(out) == 3


def test_missing_key_raises():
    with pytest.raises(RuntimeError, match="DEEPL_API_KEY"):
        DeepLEngine(api_key=None)
