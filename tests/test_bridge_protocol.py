import pytest

from plutus.bridge.bridge import PlutusBridge


@pytest.mark.asyncio
async def test_send_to_cloud_agent_message_uses_content_field():
    bridge = PlutusBridge("https://api.useplutus.ai", "pk_test", embedded=True)
    bridge._connected = True
    bridge._ws = object()
    sent_payloads = []

    async def capture_send(ws, payload):
        sent_payloads.append(payload)

    bridge._send = capture_send

    assert await bridge.send_to_cloud("hello cloud", sender="local_agent", reply_to="msg-123")

    assert sent_payloads == [
        {
            "type": "agent_message",
            "content": "hello cloud",
            "sender": "local_agent",
            "ts": sent_payloads[0]["ts"],
            "reply_to": "msg-123",
        }
    ]
    assert "data" not in sent_payloads[0]
