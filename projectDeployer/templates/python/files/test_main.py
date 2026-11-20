import unittest

from main import greeting


class GreetingTest(unittest.TestCase):
    def test_greeting(self) -> None:
        self.assertEqual(greeting(), "Привет! Проект готов.")
