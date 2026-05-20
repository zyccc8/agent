import unittest

from competitor_agents.config import get_config_value


class ConfigTest(unittest.TestCase):
    def test_missing_config_returns_default(self):
        self.assertEqual(get_config_value("__MISSING_TEST_KEY__", "fallback"), "fallback")


if __name__ == "__main__":
    unittest.main()
