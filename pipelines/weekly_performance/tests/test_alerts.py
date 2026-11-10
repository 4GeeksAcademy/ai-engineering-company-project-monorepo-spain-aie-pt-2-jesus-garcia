from __future__ import annotations

from pipelines.weekly_performance.alerts import send_alert


def test_send_alert_without_webhook_logs(monkeypatch):
    monkeypatch.delenv("PIPELINE_ALERT_WEBHOOK", raising=False)
    assert send_alert("subject", "message") is False


def test_send_alert_posts_to_webhook(monkeypatch):
    captured = {}

    class _Response:
        def raise_for_status(self):
            return None

    def _post(url, json, timeout):
        captured.update({"url": url, "json": json, "timeout": timeout})
        return _Response()

    monkeypatch.setattr("pipelines.weekly_performance.alerts.httpx.post", _post)

    assert send_alert("subject", "message", level="warning", webhook="http://hook") is True
    assert captured["url"] == "http://hook"
    assert captured["json"] == {"text": "[WARNING] subject\nmessage"}


def test_send_alert_swallows_transport_errors(monkeypatch):
    def _post(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("pipelines.weekly_performance.alerts.httpx.post", _post)
    assert send_alert("subject", "message", webhook="http://hook") is False
