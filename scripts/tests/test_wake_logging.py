import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class WakeLoggingTest(unittest.TestCase):
    def test_production_build_has_no_periodic_pcm_diagnostic_logging(self):
        source = (ROOT / "main/audio/wake_words/custom_wake_word.cc").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("Wake diagnostic", source)
        self.assertNotIn("diagnostic_feed_chunks_", source)


if __name__ == "__main__":
    unittest.main()
