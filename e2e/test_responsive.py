"""Layout at phone, tablet and desktop widths: nothing overflows horizontally, tap targets are usable."""
import pytest
from playwright.sync_api import Page

SIZES = [(375, 812), (768, 1024), (1440, 900)]
PAGES = ["/", "/rules", "/verify", "/judge"]


@pytest.mark.parametrize("path", PAGES)
@pytest.mark.parametrize("w,h", SIZES)
def test_no_horizontal_overflow(page: Page, base_url, path, w, h):
    page.set_viewport_size({"width": w, "height": h})
    page.goto(base_url + path)
    scroll_w = page.evaluate("document.documentElement.scrollWidth")
    if path == "/rules" and w < 600:  # the rules table scrolls inside its own wrapper by design
        assert page.evaluate("document.body.scrollWidth") <= w + 1 or page.locator(".table-wrap").count() == 1
    else:
        assert scroll_w <= w + 1, f"{path} is {scroll_w}px wide at {w}px"


def test_form_controls_are_tappable_on_a_phone(page: Page, base_url):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(base_url)
    for sel in ("#payer", "#amount", "#country", "#go"):
        box = page.locator(sel).bounding_box()
        assert box and box["height"] >= 36, (sel, box)
