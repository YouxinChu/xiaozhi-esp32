from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class OrakiProvisioningIdentityTest(unittest.TestCase):
    def test_oraki_provisioning_prefix_is_configurable_and_used_for_hostname(self):
        kconfig = (ROOT / "main/Kconfig.projbuild").read_text(encoding="utf-8")
        wifi_board = (ROOT / "main/boards/common/wifi_board.cc").read_text(encoding="utf-8")

        self.assertIn("config WIFI_AP_SSID_PREFIX", kconfig)
        self.assertIn('default "Oraki"', kconfig)
        self.assertIn("CONFIG_WIFI_AP_SSID_PREFIX", wifi_board)
        self.assertNotIn('config.ssid_prefix = "Xiaozhi"', wifi_board)


if __name__ == "__main__":
    unittest.main()
