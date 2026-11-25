import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class WebsocketReconnectGenerationTest(unittest.TestCase):
    def test_stale_disconnect_cannot_close_replacement_channel(self):
        header = (ROOT / "main/protocols/websocket_protocol.h").read_text(encoding="utf-8")
        source = (ROOT / "main/protocols/websocket_protocol.cc").read_text(encoding="utf-8")

        self.assertIn("std::atomic<uint32_t> audio_channel_generation_{0};", header)
        self.assertIn("const auto generation = audio_channel_generation_.fetch_add(1) + 1;", source)
        self.assertIn("websocket_->OnDisconnected([this, generation]()", source)
        self.assertIn("if (generation != audio_channel_generation_.load())", source)

    def test_unexpected_disconnect_is_reported_during_remote_task(self):
        header = (ROOT / "main/protocols/websocket_protocol.h").read_text(encoding="utf-8")
        protocol = (ROOT / "main/protocols/websocket_protocol.cc").read_text(encoding="utf-8")
        application = (ROOT / "main/application.cc").read_text(encoding="utf-8")

        self.assertIn("expected_disconnect_generation_", header)
        self.assertIn("on_disconnected_();", protocol)
        self.assertIn("protocol_->OnDisconnected([this]()", application)
        self.assertIn("remote_task_active_", application)
        self.assertIn("Lang::Strings::SERVER_ERROR", application)


if __name__ == "__main__":
    unittest.main()
