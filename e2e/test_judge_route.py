"""/judge must work for a stranger: no credentials, no session, no redirect."""
import urllib.request


def test_judge_route_is_200_with_no_credentials_and_states_the_claim(base_url):
    req = urllib.request.Request(base_url + "/judge", headers={})  # no cookie, no auth header
    with urllib.request.urlopen(req, timeout=10) as r:
        body = r.read().decode()
        assert r.status == 200 and r.geturl().endswith("/judge")
        assert r.headers.get("Set-Cookie") is None
    assert "The payout route a chatbot can" in body
    assert "30-second path" in body and "Honest limitations" in body
