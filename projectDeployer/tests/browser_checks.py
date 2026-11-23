"""Optional Chromium checks for the actual production output."""
import os
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

def check_page(case, directory, router, tailwind):
    from playwright.sync_api import sync_playwright

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, directory=str(directory / "dist")))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=os.getenv("CHROMIUM_PATH") or None)
            page = browser.new_page(viewport={"width": 375, "height": 780})
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            case.assertEqual(page.title(), "Мой React App")
            case.assertEqual(page.locator("html").get_attribute("lang"), "ru")
            page.get_by_role("button", name="Увеличить").click()
            case.assertTrue(page.get_by_text("Значение: 1").is_visible())
            page.get_by_role("button", name="Переключить").click()
            case.assertEqual(page.get_by_role("button", name="Переключить").get_attribute("aria-pressed"), "true")
            case.assertTrue(page.get_by_text("Включено", exact=True).is_visible())
            case.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"))
            if tailwind:
                card = page.locator("section.rounded-xl").first
                case.assertNotEqual(card.evaluate("e => getComputedStyle(e).borderTopLeftRadius"), "0px")
            if router:
                page.evaluate("window.navigationMarker = 42")
                page.get_by_role("link", name="О проекте").click()
                page.get_by_role("heading", name="О проекте").wait_for(state="visible")
                case.assertTrue(page.url.endswith("/about"))
                page.get_by_role("link", name="Главная").click()
                page.get_by_role("heading", name="Мой React App").wait_for(state="visible")
                case.assertEqual(page.evaluate("window.navigationMarker"), 42)
            case.assertFalse(errors, errors)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
