"""Smoke test (no keys, no mock mode): every public page loads, no console errors and the right meta."""
import pytest
from playwright.sync_api import Page, expect

PAGES = ["/", "/rules", "/verify", "/judge"]


@pytest.mark.parametrize("path", PAGES)
def test_page_loads_without_console_errors(page: Page, base_url, path):
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    resp = page.goto(base_url + path)
    assert resp and resp.status == 200
    expect(page.locator("main")).to_be_visible()
    own = [e for e in errors if "fonts.g" not in e and "ERR_" not in e]  # web fonts / blocked third parties only
    assert not own, own


def test_home_meta_and_title(page: Page, base_url):
    page.goto(base_url)
    expect(page).to_have_title("Cair — the payout route a chatbot can't get wrong")
    assert page.locator('meta[property="og:site_name"]').get_attribute("content") == "Cair"
    assert page.locator('meta[name="viewport"]').count() == 1


def test_rules_sheet_lists_sources(page: Page, base_url):
    page.goto(base_url + "/rules")
    expect(page.get_by_role("link", name="Rules sheet")).to_be_visible()
    assert page.locator("a[href^='https://']").count() > 10  # every fact links to its primary source
