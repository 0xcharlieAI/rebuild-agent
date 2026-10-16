import unittest


class SmokeTest(unittest.TestCase):
    def test_package_imports(self) -> None:
        import rebuild_agent

        self.assertEqual(rebuild_agent.__version__, "0.1.0")


if __name__ == "__main__":
    unittest.main()
