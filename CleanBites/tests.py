from django.test import TestCase


class baseTest(TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_basic(self):
        self.assertEqual(1, 1)
