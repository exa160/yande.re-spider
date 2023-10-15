import unittest
import sys
from urllib.parse import unquote

sys.path.insert(0, '..')

from utils.downloader import MultiDown


class MyTestCase(unittest.TestCase):
    def test_downloader(self):
        url = 'https://files.yande.re/image/ea78fcc7336b9f0eccabc95f83f31003/yande.re%201048888%20ass%20euryale%20fate_grand_order%20fate_stay_night%20jack_the_ripper%20loli%20medusa_%28lancer%29%20miyu_edelfelt%20naked%20nipples%20pussy%20rogia%20stheno%20tattoo%20uncensored.png'
        path = f'./{unquote("yande.re%201048888%20ass%20euryale%20fate_grand_order%20fate_stay_night%20jack_the_ripper%20loli%20medusa_%28lancer%29%20miyu_edelfelt%20naked%20nipples%20pussy%20rogia%20stheno%20tattoo%20uncensored.png")}'
        f = MultiDown(url, path, md5='ea78fcc7336b9f0eccabc95f83f31003')
        # self.assertEqual(True, False)  # add assertion here


if __name__ == '__main__':
    unittest.main()
