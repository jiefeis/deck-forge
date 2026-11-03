"""Real-browser regressions for visible HTML chrome and keyboard ownership."""
from pathlib import Path
import re
import sys
import tempfile
import unittest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ('consulting-visuals', 'consulting-diagrams')
NAVIGATION_SOURCES = (*EXAMPLES, 'template')
NAVIGATION_KEYS = ('ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End')
sys.path.insert(0, str(ROOT / 'scripts'))
from export_pdf import EXPORT_CSS, _start_server, launch_chromium, resolve_browser_executable


class ConsultingHtmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = sync_playwright().start()
        cls.browser = launch_chromium(cls.runtime, resolve_browser_executable(None))
        cls.example_server, cls.example_port = _start_server(ROOT)
        cls.template_dir = tempfile.TemporaryDirectory()
        # Run the template's actual controller; expose only its instance to wire
        # optional previous/next buttons in this representative four-slide page.
        template = (ROOT / 'html-template.md').read_text(encoding='utf-8')
        script = re.search(r'<script>(.*?)</script>', template, re.S).group(1)
        script = script.replace('new SlidePresentation();', 'window.testDeck = new SlidePresentation();')
        fixture = '<!doctype html><html><body><main id="deckStage">'
        fixture += '<section class="slide">Slide</section>' * 4
        fixture += """</main><nav class="deck-controls">
            <button id="prev">Previous</button><button id="next">Next</button>
            </nav><script>""" + script + """
            document.getElementById('prev').onclick = () => testDeck.showSlide(testDeck.currentSlide - 1);
            document.getElementById('next').onclick = () => testDeck.showSlide(testDeck.currentSlide + 1);
            </script></body></html>"""
        (Path(cls.template_dir.name) / 'index.html').write_text(fixture, encoding='utf-8')
        cls.template_server, cls.template_port = _start_server(Path(cls.template_dir.name))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.runtime.stop()
        for server in (cls.example_server, cls.template_server):
            server.shutdown()
            server.server_close()
        cls.template_dir.cleanup()

    def open_example(self, name, size=(1280, 720)):
        page = self.browser.new_page(viewport={'width': size[0], 'height': size[1]})
        url = (f'http://127.0.0.1:{self.template_port}/index.html' if name == 'template'
               else f'http://127.0.0.1:{self.example_port}/examples/{name}/index.html')
        page.goto(url)
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

    def slide_index(self, page):
        return page.locator('.slide').evaluate_all("slides => slides.findIndex(s => s.classList.contains('active'))")

    def test_navigation_shortcuts_after_button_click(self):
        for name in NAVIGATION_SOURCES:
            page = self.open_example(name)
            try:
                last = page.locator('.slide').count() - 1
                for button in ('next', 'prev'):
                    for key in NAVIGATION_KEYS:
                        with self.subTest(example=name, button=button, key=key):
                            page.locator('body').click(position={'x': 2, 'y': 2})
                            page.keyboard.press('Home' if button == 'next' else 'End')
                            page.locator('#' + button).click()
                            self.assertEqual(page.evaluate('document.activeElement.id'), button)
                            start = 1 if button == 'next' else last - 1
                            self.assertEqual(self.slide_index(page), start)
                            page.keyboard.press(key)
                            expected = (0 if key == 'Home' else last if key == 'End' else
                                        start + (1 if key in ('ArrowRight', 'ArrowDown', 'PageDown') else -1))
                            self.assertEqual(self.slide_index(page), expected)
            finally:
                page.close()

    def test_navigation_buttons_activate_once_for_enter_and_space(self):
        for name in NAVIGATION_SOURCES:
            page = self.open_example(name)
            try:
                page.evaluate("""() => {
                    window.navClicks = 0;
                    window.slideCalls = 0;
                    document.querySelectorAll('.deck-controls button').forEach(button =>
                        button.addEventListener('click', () => window.navClicks++));
                    const showSlide = SlidePresentation.prototype.showSlide;
                    SlidePresentation.prototype.showSlide = function(index) {
                        window.slideCalls++;
                        return showSlide.call(this, index);
                    };
                }""")
                last = page.locator('.slide').count() - 1
                for button in ('next', 'prev'):
                    for key in ('Enter', 'Space'):
                        with self.subTest(example=name, button=button, key=key):
                            page.locator('body').click(position={'x': 2, 'y': 2})
                            page.keyboard.press('Home' if button == 'next' else 'End')
                            page.locator('#' + button).click()
                            page.evaluate('window.navClicks = window.slideCalls = 0')
                            page.keyboard.press(key)
                            self.assertEqual(self.slide_index(page), 2 if button == 'next' else last - 2)
                            self.assertEqual(page.evaluate('[window.navClicks, window.slideCalls]'), [1, 1])
            finally:
                page.close()

    def test_other_interactive_controls_keep_keyboard_ownership(self):
        for name in NAVIGATION_SOURCES:
            page = self.open_example(name)
            try:
                page.keyboard.press('ArrowRight')
                page.evaluate("""() => {
                    const controls = document.createElement('div');
                    controls.innerHTML = `<button>Action</button><a href="#">Link</a>
                        <input><textarea></textarea><select><option>First</option><option>Second</option></select>
                        <div contenteditable="true">Editable</div>
                        <div role="button" tabindex="0">Action</div>
                        <div role="textbox" tabindex="0">Text</div>
                        <div role="slider" tabindex="0">Range</div>
                        <nav class="deck-controls"><button>Other deck control</button></nav>`;
                    document.body.append(controls);
                    controls.querySelectorAll('button,a,input,textarea,select,[contenteditable],[role]').forEach(
                        (control, index) => control.id = 'test-control-' + index);
                }""")
                for index in range(10):
                    control = page.locator('#test-control-' + str(index))
                    for key in (*NAVIGATION_KEYS, 'Enter', 'Space'):
                        with self.subTest(example=name, control=index, key=key):
                            control.focus()
                            page.keyboard.press(key)
                            self.assertEqual(self.slide_index(page), 1)
            finally:
                page.close()

    def test_composition_modifiers_and_prevented_events_keep_keyboard_ownership(self):
        for name in NAVIGATION_SOURCES:
            page = self.open_example(name)
            try:
                page.locator('#next').click()
                for target in ('body', '#prev', '#next'):
                    for flag in ('isComposing', 'altKey', 'ctrlKey', 'metaKey', 'defaultPrevented'):
                        with self.subTest(example=name, target=target, flag=flag):
                            page.locator(target).evaluate("""(target, flag) => {
                                const event = new KeyboardEvent('keydown', {
                                    key: 'ArrowRight', bubbles: true, cancelable: true, [flag]: true
                                });
                                if (flag === 'defaultPrevented') event.preventDefault();
                                target.dispatchEvent(event);
                            }""", flag)
                            self.assertEqual(self.slide_index(page), 1)
            finally:
                page.close()

    def test_navigation_shortcuts_clamp_at_boundaries(self):
        for name in NAVIGATION_SOURCES:
            page = self.open_example(name)
            try:
                last = page.locator('.slide').count() - 1
                for button, boundary, keys in (
                    ('next', 'Home', ('ArrowLeft', 'ArrowUp', 'PageUp', 'Home')),
                    ('prev', 'End', ('ArrowRight', 'ArrowDown', 'PageDown', 'End')),
                ):
                    page.locator('body').click(position={'x': 2, 'y': 2})
                    page.keyboard.press(boundary)
                    page.locator('#' + button).focus()
                    for key in keys:
                        with self.subTest(example=name, boundary=boundary, key=key):
                            page.keyboard.press(key)
                            self.assertEqual(self.slide_index(page), 0 if boundary == 'Home' else last)
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
