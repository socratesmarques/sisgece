"""Proteção contra scripts administrativos na página pública e cache obsoleto."""
import re
import unittest
from backend.app import app, ROOT, STATIC_ASSET_VERSIONS

IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "public, max-age=0, must-revalidate"


class StaticAssetsTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_page_specific_scripts_and_versioned_css(self):
        for route, expected, excluded in (("/", "public.js", "staff.js"), ("/equipe", "staff.js", "public.js")):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                html = response.get_data(as_text=True)
                for name in ("main.css", "shared.js", expected):
                    self.assertIn(f"/static/{name}?v={STATIC_ASSET_VERSIONS[name]}", html)
                self.assertNotIn(f"/static/{excluded}", html)
                self.assertNotIn("/static/main.js", html)
                for name in ("mascote.css", "mascote.js"):
                    url = f"/static/{name}?v={STATIC_ASSET_VERSIONS[name]}"
                    if route == "/":
                        self.assertIn(url, html)
                    else:
                        self.assertNotIn(f"/static/{name}", html)
                self.assertEqual(len(re.findall(r'<script defer src=', html)), 3 if route == "/" else 2)

    def test_only_matching_fingerprints_have_immutable_cache(self):
        for name, version in STATIC_ASSET_VERSIONS.items():
            with self.subTest(name=name):
                url = f"/static/{name}?v={version}"
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["Cache-Control"], IMMUTABLE)
                etag = response.headers.get("ETag")
                self.assertTrue(etag)
                cached = self.client.get(url, headers={"If-None-Match": etag})
                self.assertEqual(cached.status_code, 304)
                self.assertEqual(cached.headers["Cache-Control"], IMMUTABLE)
                for bad_url in (f"/static/{name}", f"/static/{name}?v=incorreta",
                                f"/static/{name}?v={version}&extra=1"):
                    self.assertEqual(self.client.get(bad_url).headers["Cache-Control"], REVALIDATE)

    def test_public_bundle_has_no_admin_code_and_is_smaller(self):
        static = ROOT / "frontend/static"
        shared = (static / "shared.js").read_bytes()
        public = (static / "public.js").read_bytes()
        staff = (static / "staff.js").read_bytes()
        self.assertLess(len(shared) + len(public), 7000)
        self.assertLess(len(shared) + len(public), (len(shared) + len(staff)) * 0.4)
        self.assertIn(b"solicitar", public)
        self.assertNotIn(b"loadMessageModels", public)
        self.assertNotIn(b"loadMessageModels", shared)
        self.assertIn(b"loadMessageModels", staff)

    def test_api_remains_uncached(self):
        self.assertEqual(self.client.get("/api/me").headers["Cache-Control"], "no-store")
