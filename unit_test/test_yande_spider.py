import unittest
import sys
from urllib.parse import unquote

sys.path.insert(0, '..')

from spider.yande_api import YandeSpider


class MyTestCase(unittest.TestCase):
    def test_spider(self):
        y = YandeSpider()
        y.get_post_list()
        # self.assertEqual(True, False)  # add assertion here


if __name__ == '__main__':
    unittest.main()
