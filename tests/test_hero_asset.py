"""Regressão: marca IFCE local, prioritária e com cache seguro."""
import unittest

from backend.app import app


IMAGE_URL = "/static/img/ifce-logo.374f13b.png"


class HeroAssetTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_public_home_uses_prioritized_local_logo(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        html = response.get_data(as_text=True)
        self.assertIn(f'src="{IMAGE_URL}"', html)
        self.assertIn(f'rel="preload" as="image" href="{IMAGE_URL}"', html)
        self.assertIn('fetchpriority="high"', html)
        self.assertIn('loading="eager"', html)
        self.assertIn('width="768" height="765"', html)
        self.assertNotIn("acervo.ifce.edu.br", html)
        self.assertNotIn("acervo.ifce.edu.br", response.headers["Content-Security-Policy"])

    def test_logo_is_a_small_png_with_immutable_cache(self):
        response = self.client.get(IMAGE_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertTrue(response.data.startswith(b"\\x89PNG\\r\\n\\x1a\\n"))
        self.assertLess(len(response.data), 40_000)
        self.assertEqual(
            response.headers["Cache-Control"], "public, max-age=31536000, immutable"
        )
        etag = response.headers.get("ETag")
        self.assertTrue(etag)
        again = self.client.get(IMAGE_URL, headers={"If-None-Match": etag})
        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.headers["Cache-Control"],
                         "public, max-age=31536000, immutable")

    def test_other_static_resources_revalidate_and_private_pages_do_not_cache(self):
        css = self.client.get("/static/main.css")
        self.assertEqual(css.status_code, 200)
        self.assertEqual(css.headers["Cache-Control"],
                         "public, max-age=0, must-revalidate")
        self.assertTrue(css.headers.get("ETag"))

        staff = self.client.get("/equipe")
        self.assertEqual(staff.status_code, 200)
        self.assertEqual(staff.headers["Cache-Control"], "no-store")
        self.assertNotIn('rel="preload" as="image"', staff.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
