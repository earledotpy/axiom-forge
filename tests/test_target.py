import unittest

from app.target import answer


class TestTarget(unittest.TestCase):
    def test_answer_is_nonempty_string(self):
        self.assertIsInstance(answer(), str)
        self.assertTrue(answer())


if __name__ == "__main__":
    unittest.main()
