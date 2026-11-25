import unittest
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class RuntimeWakeThresholdTest(unittest.TestCase):
    def test_oraki_box3_product_default_is_ten_percent(self):
        sdkconfig = (ROOT / "sdkconfig.oraki-box3.defaults").read_text(
            encoding="utf-8"
        )
        self.assertIn("CONFIG_CUSTOM_WAKE_WORD_THRESHOLD=10", sdkconfig)

    def test_multinet_threshold_can_be_changed_safely_at_runtime(self):
        header = (ROOT / "main/audio/wake_words/custom_wake_word.h").read_text(
            encoding="utf-8"
        )
        source = (ROOT / "main/audio/wake_words/custom_wake_word.cc").read_text(
            encoding="utf-8"
        )
        self.assertIn("bool SetDetectionThreshold(float threshold)", header)
        self.assertIn("kMinDetectionThreshold", source)
        self.assertIn("kMaxDetectionThreshold", source)
        self.assertIn("set_det_threshold(multinet_model_data_, threshold_)", source)

    def test_persisted_threshold_overrides_assets_default(self):
        source = (ROOT / "main/audio/wake_words/custom_wake_word.cc").read_text(
            encoding="utf-8"
        )
        self.assertIn('Settings settings("wake_word", false)', source)
        self.assertIn('GetInt("threshold_pct"', source)

    def test_ota_refresh_is_applied_without_reinitializing_audio(self):
        ota = (ROOT / "main/ota.cc").read_text(encoding="utf-8")
        application = (ROOT / "main/application.cc").read_text(encoding="utf-8")
        self.assertIn('cJSON_GetObjectItem(root, "wake_word")', ota)
        self.assertIn('SetInt("threshold_pct"', ota)
        self.assertIn("ApplyWakeWordThreshold", application)

    def test_websocket_config_updates_current_multinet_without_reboot(self):
        protocol = (ROOT / "main/protocols/websocket_protocol.cc").read_text(
            encoding="utf-8"
        )
        application_h = (ROOT / "main/application.h").read_text(encoding="utf-8")
        application_cc = (ROOT / "main/application.cc").read_text(encoding="utf-8")

        self.assertIn('strcmp(type->valuestring, "config") == 0', protocol)
        self.assertIn("ParseWakeWordConfig(root)", protocol)
        self.assertIn("UpdateWakeWordThreshold(int threshold_percent)", application_h)
        self.assertIn("SetWakeWordDetectionThreshold", application_cc)
        self.assertIn('Settings settings("wake_word", true)', application_cc)

    def test_wake_threshold_nvs_key_fits_esp_idf_limit(self):
        sources = [
            (ROOT / "main/ota.cc").read_text(encoding="utf-8"),
            (ROOT / "main/application.cc").read_text(encoding="utf-8"),
            (ROOT / "main/audio/wake_words/custom_wake_word.cc").read_text(
                encoding="utf-8"
            ),
        ]
        keys = []
        for source in sources:
            keys.extend(re.findall(r'(?:GetInt|SetInt)\("([^"]*threshold[^"]*)"', source))

        self.assertTrue(keys)
        self.assertTrue(all(len(key) <= 15 for key in keys), keys)


if __name__ == "__main__":
    unittest.main()
