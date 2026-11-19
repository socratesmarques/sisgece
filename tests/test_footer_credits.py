"""Valida créditos públicos do rodapé sem necessidade de banco de dados."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FooterCredits(unittest.TestCase):
    def test_developers_and_lsd_link(self):
        html = (ROOT / 'frontend/templates/home.html').read_text(encoding='utf-8')
        for name in ('Bryan William', 'Mario Gabriel', 'Socrates Costa', 'Wendel Peterson'):
            self.assertIn(name, html)
        self.assertIn('Site desenvolvido por', html)
        self.assertIn('https://lsd.maranguape.ifce.edu.br/', html)
        self.assertIn('rel="noopener noreferrer"', html)

    def test_responsive_styles(self):
        css = (ROOT / 'frontend/static/main.css').read_text(encoding='utf-8')
        self.assertIn('.site-footer', css)
        self.assertIn('.footer-credits a', css)


if __name__ == '__main__':
    unittest.main()
