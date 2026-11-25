import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class RemoteTaskTimeoutGateTest(unittest.TestCase):
    def test_remote_work_states_gate_local_listening_timeout(self):
        header = (ROOT / "main/application.h").read_text(encoding="utf-8")
        source = (ROOT / "main/application.cc").read_text(encoding="utf-8")

        self.assertIn("bool remote_task_active_ = false;", header)
        self.assertIn(
            "GetDeviceState() == kDeviceStateListening && !remote_task_active_ &&",
            source,
        )
        self.assertIn(
            'state_name == "thinking" || state_name == "executing" ||\n'
            '                                      state_name == "processing" || state_name == "queued"',
            source,
        )
        self.assertIn("remote_task_active_ = remote_task_active;", source)


if __name__ == "__main__":
    unittest.main()
