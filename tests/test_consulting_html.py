"""Real-browser regressions for visible HTML chrome and keyboard ownership."""
from pathlib import Path
import sys
import unittest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ('consulting-visuals', 'consulting-diagrams')
sys.path.insert(0, str(ROOT / 'scripts'))
from export_pdf import EXPORT_CSS, launch_chromium, resolve_browser_executable


class ConsultingHtmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = sync_playwright().start()
        cls.browser = launch_chromium(cls.runtime, resolve_browser_executable(None))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.runtime.stop()

    def open_example(self, name, size=(1280, 720)):
        page = self.browser.new_page(viewport={'width': size[0], 'height': size[1]})
        page.goto((ROOT / 'examples' / name / 'index.html').as_uri())
        page.evaluate('document.fonts.ready')
        return page

    def test_controls_never_cover_authored_page(self):
        for name in EXAMPLES:
            for size in ((1280, 720), (960, 540)):
                with self.subTest(example=name, viewport=size):
                    page = self.open_example(name, size)
                    try:
                        for _ in range(3):
                            slide = page.locator('.slide.active').bounding_box()
                            controls = page.locator('.deck-controls').bounding_box()
                            self.assertLessEqual(slide['y'] + slide['height'], controls['y'])
                            self.assertLessEqual(slide['x'] + slide['width'], size[0] + 0.01)
                            page.locator('body').click(position={'x': 2, 'y': 2})
                            page.keyboard.press('ArrowRight')
                    finally:
                        page.close()

    def test_native_button_space_and_background_shortcuts(self):
        for name in EXAMPLES:
            with self.subTest(example=name):
                page = self.open_example(name)
                try:
                    self.assertTrue(page.locator('#prev').is_disabled())
                    page.keyboard.press('End')
                    self.assertEqual(page.locator('#position').inner_text(), '3 / 3')
                    self.assertTrue(page.locator('#next').is_disabled())
                    page.locator('#prev').click()
                    page.keyboard.press('Space')
                    self.assertEqual(page.locator('#position').inner_text(), '1 / 3')
                    page.locator('body').click(position={'x': 2, 'y': 2})
                    page.keyboard.press('Space')
                    self.assertEqual(page.locator('#position').inner_text(), '2 / 3')
                    page.keyboard.press('Home')
                    self.assertEqual(page.locator('#position').inner_text(), '1 / 3')
                    self.assertEqual(page.locator('#position').get_attribute('aria-live'), 'polite')
                    page.evaluate("const t=document.createElement('textarea');t.id='test-editor';t.style='position:fixed;z-index:9999;top:0;left:0';document.body.append(t);t.focus()")
                    page.keyboard.press('Space')
                    page.keyboard.press('ArrowRight')
                    self.assertEqual(page.locator('#position').inner_text(), '1 / 3')
                finally:
                    page.close()

    def test_bundled_font_faces_load_without_local_font_sources(self):
        for name in EXAMPLES:
            with self.subTest(example=name):
                page = self.open_example(name)
                try:
                    self.assertNotIn("src:local(", page.locator('style').inner_text())
                    faces = page.evaluate("[...document.fonts].filter(f=>f.family.includes('Deck CJK')).map(f=>f.status)")
                    self.assertEqual(faces, ['loaded', 'loaded'])
                finally:
                    page.close()

    def test_export_and_print_keep_full_slide_geometry(self):
        for name in EXAMPLES:
            with self.subTest(example=name):
                page = self.open_example(name)
                try:
                    page.add_style_tag(content=EXPORT_CSS)
                    stage = page.locator('.deck-stage').bounding_box()
                    self.assertEqual((stage['x'], stage['y'], stage['width'], stage['height']), (0, 0, 1920, 1080))
                    self.assertFalse(page.locator('.deck-controls').is_visible())
                    page.emulate_media(media='print')
                    for slide in page.locator('.slide').all():
                        self.assertTrue(slide.is_visible())
                        box = slide.bounding_box()
                        self.assertEqual((box['width'], box['height']), (1920, 1080))
                finally:
                    page.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
