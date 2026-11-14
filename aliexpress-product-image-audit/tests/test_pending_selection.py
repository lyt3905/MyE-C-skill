import unittest
from workflow_runner import select_pending_products


class Reader:
    def __init__(self, shops=('7', '7'), status='PENDING'):
        self.shops = iter(shops)
        self.status = status
        self.calls = []

    def current_shop(self):
        self.calls.append('shop')
        return next(self.shops)

    def call(self, path):
        self.calls.append(path)
        return {'data': {'items': [{'id': 5017, 'status': self.status}]}}


class PendingSelectionTests(unittest.TestCase):
    def test_pending_first_page_and_shop_bracketing(self):
        reader = Reader()
        self.assertEqual(select_pending_products(reader, 7, 3), [5017])
        self.assertEqual(reader.calls, ['shop', '/api/admin/products?status=PENDING&size=3&page=1', 'shop'])

    def test_shop_mismatch_before_or_after_read_rejected(self):
        for shops in (('8',), ('7', '8')):
            with self.subTest(shops=shops), self.assertRaisesRegex(ValueError, 'SHOP_MISMATCH'):
                select_pending_products(Reader(shops), 7, 3)

    def test_wrong_or_missing_status_rejected(self):
        for status in ('READY_TO_PUBLISH', None):
            with self.subTest(status=status), self.assertRaises(ValueError):
                select_pending_products(Reader(status=status), 7, 3)

    def test_invalid_count_does_not_read(self):
        reader = Reader()
        with self.assertRaises(ValueError):
            select_pending_products(reader, 7, 0)
        self.assertEqual(reader.calls, [])
