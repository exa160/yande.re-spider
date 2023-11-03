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

    def test_spider_update(self):
        y = YandeSpider()
        b_path = r'E:\小工具\python_tool\yande.re_spider\pic'
        y.update_tags(b_path, [['iijima_masashi', 1127736, False]])


if __name__ == '__main__':
    unittest.main()
