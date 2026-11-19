"""Valida a identidade e os créditos públicos do rodapé LSD sem banco de dados."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FooterCredits(unittest.TestCase):
    def test_developers_and_lsd_link(self):
        html = (ROOT / 'frontend/templates/home.html').read_text(encoding='utf-8')
        footer = html.split('<footer class="site-footer">', 1)[1].split('</footer>', 1)[0]

        self.assertIn('© 2026 LSD - Laboratório de Sistemas e Dados', footer)
        self.assertIn('Desenvolvido por ', footer)
        for name in ('Bryan William', 'Mario Gabriel', 'Sócrates Costa', 'Wendel Peterson'):
            self.assertIn(name, footer)

        self.assertIn('https://lsd.maranguape.ifce.edu.br/', footer)
        self.assertIn('rel="noopener noreferrer"', footer)
        self.assertIn("filename='img/lsd-logo.svg'", footer)
        self.assertIn('alt="Logotipo do Laboratório de Sistemas e Dados"', footer)
        self.assertNotIn('<nav', footer)
        self.assertNotIn('Contato', footer)

        logo = (ROOT / 'frontend/static/img/lsd-logo.svg').read_text(encoding='utf-8')
        self.assertIn('<svg', logo)
        self.assertIn('</svg>', logo)

    def test_responsive_styles(self):
        css = (ROOT / 'frontend/static/main.css').read_text(encoding='utf-8')
        self.assertIn('.site-footer {', css)
        self.assertIn('background: var(--ink);', css)
        self.assertIn('.site-footer__content {', css)
        self.assertIn('.site-footer__brand img {', css)
        self.assertIn('.site-footer__bottom {', css)
        self.assertIn('.site-footer__bottom p {', css)
        self.assertIn('@media (max-width: 520px)', css)


if __name__ == '__main__':
    unittest.main()
