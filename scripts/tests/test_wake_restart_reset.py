import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class WakeRestartResetTest(unittest.TestCase):
    def test_multinet_is_cleaned_at_each_detection_session_boundary(self):
        source = (ROOT / "main/audio/wake_words/custom_wake_word.cc").read_text(
            encoding="utf-8"
        )
        start = source[source.index("void CustomWakeWord::Start()") : source.index("void CustomWakeWord::Stop()")]
        stop = source[source.index("void CustomWakeWord::Stop()") : source.index("void CustomWakeWord::Feed(")]

        for method in (start, stop):
            self.assertIn("std::lock_guard<std::mutex> lock(input_buffer_mutex_)", method)
            self.assertIn("input_buffer_.clear()", method)
            self.assertIn("multinet_->clean(multinet_model_data_)", method)

    def test_continuous_wake_uses_a_window_longer_than_the_phrase(self):
        source = (ROOT / "main/audio/wake_words/custom_wake_word.cc").read_text(
            encoding="utf-8"
        )
        self.assertIn("kContinuousWakeRecognitionWindowMs", source)
        self.assertIn(
            "duration_ = std::max(duration_, kContinuousWakeRecognitionWindowMs)",
            source,
        )

    def test_timeout_replays_recent_audio_into_the_clean_model(self):
        source = (ROOT / "main/audio/wake_words/custom_wake_word.cc").read_text(
            encoding="utf-8"
        )
        header = (ROOT / "main/audio/wake_words/custom_wake_word.h").read_text(
            encoding="utf-8"
        )
        timeout_branch = source[
            source.index("else if (mn_state == ESP_MN_STATE_TIMEOUT)") :
            source.index("if (!running_)", source.index("else if (mn_state == ESP_MN_STATE_TIMEOUT)"))
        ]

        self.assertIn("kTimeoutOverlapMs = 2000", source)
        self.assertIn("timeout_overlap_buffer_", header)
        self.assertIn("multinet_->clean(multinet_model_data_)", timeout_branch)
        self.assertIn("ReplayTimeoutOverlap()", timeout_branch)


if __name__ == "__main__":
    unittest.main()
