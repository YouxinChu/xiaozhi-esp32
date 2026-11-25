import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class IdleWakeAecTest(unittest.TestCase):
    def test_idle_multinet_does_not_enable_playback_aec(self):
        source = (ROOT / "main/audio/engines/afe_audio_engine.cc").read_text(encoding="utf-8")
        start = source.index("void AfeAudioEngine::ApplyAfeControls()")
        end = source.index("void AfeAudioEngine::ApplyPendingReset()", start)
        controls = source[start:end]

        self.assertNotIn("(bits & kWakeWordEnabled) ||", controls)
        self.assertIn(
            "device_aec_enabled_.load() && (bits & kVoiceProcessingEnabled)", controls
        )

    def test_vad_does_not_abort_speaking_without_semantic_confirmation(self):
        source = (ROOT / "main/application.cc").read_text(encoding="utf-8")
        start = source.index("callbacks.on_vad_change")
        end = source.index("callbacks.on_playback_drained", start)
        vad_callback = source[start:end]

        self.assertNotIn("AbortSpeaking(", vad_callback)
        self.assertNotIn("SetListeningMode(", vad_callback)


if __name__ == "__main__":
    unittest.main()
