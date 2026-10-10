"""The core journey in a real browser: fill the form, get the card, confirm a line."""
from playwright.sync_api import Page, expect


def test_hero_plan_refuses_wise_recommends_payoneer_and_confirms_line10(page: Page, base_url):
    page.goto(base_url)
    page.select_option("#payer", "devpost")
    page.fill("#amount", "7000")
    page.select_option("#country", "ID")
    page.get_by_role("button", name="Plan my payout").click()
    card = page.locator("#result")
    expect(card.get_by_text("REFUSED").first).to_be_visible(timeout=30_000)
    expect(card.get_by_text("Leave blank").first).to_be_visible()
    expect(card.get_by_text("no longer hold money").first).to_be_visible()  # Wise's own sentence
    expect(card.locator(".is-rec")).to_have_count(1)
    expect(card.locator(".is-rec")).to_contain_text("Payoneer")
    page.get_by_role("button", name="Confirm").first.click()
    expect(page.get_by_role("button", name="Confirmed").first).to_be_visible(timeout=15_000)


def test_unlisted_country_is_unclear_and_picks_no_route(page: Page, base_url):
    page.goto(base_url)
    page.select_option("#country", "OTHER")
    page.get_by_role("button", name="Plan my payout").click()
    card = page.locator("#result")
    expect(card.get_by_text("UNCLEAR").first).to_be_visible(timeout=30_000)
    assert page.locator("#result .is-rec").count() == 0  # no rail is marked as the recommended one


def test_bad_amount_shows_a_message_not_a_crash(page: Page, base_url):
    page.goto(base_url)
    page.fill("#amount", "abc")
    page.get_by_role("button", name="Plan my payout").click()
    expect(page.locator("#status")).to_contain_text("amount", timeout=10_000)
