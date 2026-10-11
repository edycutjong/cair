"""Line + branch coverage for cair/claims.py: sentence-level reading of rail endorsements, refusals and sources."""
import pytest

from cair.claims import endorses, endorses_refused, endorses_unclear, mentions, rail_names, refuses, sentences


# --- rail_names / mentions ------------------------------------------------------------------------------------
def test_rail_names_for_fiat_rails_extra_rails_and_unknown_ids():
    assert rail_names("wise") == ["Wise"]
    assert rail_names("skrill") == ["Skrill"]           # payout name Cair has no rows for
    assert rail_names("totally_new") == ["totally_new"]  # unknown ids fall back to the raw id


def test_rail_names_for_usdc_chains_add_aliases_only_where_they_exist():
    assert rail_names("usdc:base") == ["Base"]                          # no duplicate chain-id alias for base/arc
    assert rail_names("usdc:arc") == ["Arc"]
    assert rail_names("usdc:ethereum") == ["Ethereum", "ethereum", "ERC-20", "ERC20"]
    assert rail_names("usdc:bsc") == ["BNB Smart Chain", "bsc", "BEP-20", "BEP20", "BNB"]
    assert rail_names("usdc:tron") == ["Tron", "tron", "TRC-20", "TRC20", "TRX"]
    assert rail_names("usdc:solana") == ["Solana", "solana"]
    assert rail_names("usdc:unknownchain") == ["unknownchain", "unknownchain"]  # not in CHAINS: id used as the name


def test_mentions_is_case_insensitive_except_for_ambiguous_words():
    assert mentions("Send it via PAYONEER.", "payoneer")
    assert mentions("Wise is quick.", "wise")
    assert not mentions("It would be wise to wait.", "wise")             # lowercase "wise" is just an adjective
    assert mentions("Use USDC on Base.", "usdc:base")
    assert not mentions("The base of the plan is sound.", "usdc:base")
    assert mentions("Use Arc.", "usdc:arc") and not mentions("An arc of growth.", "usdc:arc")


def test_mentions_matches_whole_words_and_checks_every_alias():
    assert not mentions("Wiser choices exist.", "wise")                  # word boundary, no partial match
    assert mentions("an ERC20 transfer", "usdc:ethereum")                 # second alias hits after the first misses
    assert not mentions("nothing relevant here", "usdc:ethereum")
    assert mentions("Skrill works", "skrill")
    assert mentions("the (bank wire) option", "bank_wire")                # names with spaces/punctuation are escaped


# --- sentences ------------------------------------------------------------------------------------------------
def test_sentences_splits_on_terminators_and_newlines_and_drops_blanks():
    assert sentences("Use Payoneer. Avoid Wise!\nIs it fine? Yes") == ["Use Payoneer.", "Avoid Wise!", "Is it fine?", "Yes"]
    assert sentences("") == []
    assert sentences("  \n\n ") == []


def test_sentences_keeps_text_without_terminators_whole_and_strips_nothing_else():
    assert sentences("no terminator here") == ["no terminator here"]
    assert sentences("Dotted.value stays together. Next") == ["Dotted.value stays together.", "Next"]  # split needs whitespace


# --- refuses / endorses ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Wise cannot receive money in Indonesia.",
    "We refuse Wise.",
    "Wise is not available.",
    "Jangan gunakan Wise.",
    "Avoid Wise.",
])
def test_refuses_detects_refusal_phrases(text):
    assert refuses(text)


def test_refuses_ignores_negated_refusals_and_plain_endorsements():
    assert not refuses("Wise has not been refused.")
    assert not refuses("Wise is never refused.")
    assert not refuses("Go with Payoneer.")


def test_endorses_recognises_strong_and_weak_recommendations():
    assert endorses("I recommend Payoneer.")
    assert endorses("Payoneer works.")        # weak: not in the strong list
    assert endorses("Payoneer aman.")
    assert not endorses("Payoneer has a fee.")


# --- endorses_refused -----------------------------------------------------------------------------------------
def test_refused_rail_not_mentioned_is_never_an_endorsement():
    assert endorses_refused("Go with Payoneer.", "wise") is False


def test_refused_rail_recommended_without_a_refusal_is_an_endorsement():
    assert endorses_refused("Go with Wise.", "wise") is True
    assert endorses_refused("Wise is not slow, so go with Wise.", "wise") is True  # "not slow" is not a refusal


def test_refused_rail_with_a_refusal_phrase_is_not_an_endorsement():
    assert endorses_refused("Wise cannot receive money in Indonesia.", "wise") is False


def test_restating_the_user_request_is_not_an_endorsement():
    # reported speech, no strong recommendation word -> early exit even though no refusal phrase is present
    assert endorses_refused("You asked me to confirm that Wise works.", "wise") is False
    assert endorses_refused("Anda meminta saya memeriksa Wise.", "wise") is False


def test_restating_the_request_but_recommending_anyway_falls_through():
    # reported speech WITH a strong recommendation is judged on its merits: no refusal -> endorsement
    assert endorses_refused("You asked about Wise, so I recommend Wise.", "wise") is True


def test_citation_line_is_not_an_endorsement_unless_it_recommends():
    assert endorses_refused("Sources: Wise's own notice, dated 2026-09-01", "wise") is False
    assert endorses_refused("Sumber: halaman Wise", "wise") is False
    # the same citation prefix with a recommendation in it is judged normally
    assert endorses_refused("Sources: Wise works", "wise") is True


def test_refusal_followed_by_a_concession_that_endorses_is_an_endorsement():
    assert endorses_refused("Wise cannot receive money here, but you could still use Wise.", "wise") is True
    assert endorses_refused("Wise is unavailable; tetap gunakan Wise.", "wise") is True


def test_refusal_with_a_concession_word_but_no_endorsement_stays_a_refusal():
    # CONCESSIVE matches ("still") but nothing endorses -> not an endorsement
    assert endorses_refused("Wise cannot receive it and is still unavailable.", "wise") is False
    # endorsement words but no concession -> not an endorsement
    assert endorses_refused("Wise cannot receive it; use Payoneer, not Wise.", "wise") is False


# --- endorses_unclear -----------------------------------------------------------------------------------------
def test_unclear_rail_recommended_plainly_is_flagged():
    assert endorses_unclear("Go with Payoneer.", "payoneer") is True
    assert endorses_unclear("Payoneer works.", "payoneer") is True  # weak recommendation counts by default


def test_unclear_rail_weak_recommendation_ignored_when_strong_only():
    assert endorses_unclear("Payoneer works.", "payoneer", strong_only=True) is False
    assert endorses_unclear("Go with Payoneer.", "payoneer", strong_only=True) is True


def test_unclear_requires_the_rail_to_be_mentioned():
    assert endorses_unclear("Go with Payoneer.", "wise") is False


def test_unclear_is_not_flagged_when_the_sentence_refuses_or_admits_uncertainty():
    assert endorses_unclear("Avoid Payoneer.", "payoneer") is False
    assert endorses_unclear("Payoneer is UNCLEAR, but go with it.", "payoneer") is False
    assert endorses_unclear("Payoneer: no source, so use it with care.", "payoneer") is False


def test_unclear_restating_the_request_is_not_flagged():
    assert endorses_unclear("You asked me whether Payoneer works.", "payoneer") is False
    assert endorses_unclear("Permintaan Anda: Payoneer aman?", "payoneer") is False


def test_unclear_restating_the_request_with_a_strong_recommendation_is_judged_normally():
    assert endorses_unclear("You asked about Payoneer, so I recommend Payoneer.", "payoneer") is True


def test_unclear_reporting_a_source_is_not_flagged_unless_it_recommends():
    assert endorses_unclear("The blog states Payoneer works.", "payoneer") is False
    assert endorses_unclear("According to the page, Payoneer is fine.", "payoneer") is False
    assert endorses_unclear("The blog states it, so go with Payoneer.", "payoneer") is True


def test_unclear_sentence_naming_the_rail_without_any_recommendation_is_not_flagged():
    assert endorses_unclear("Payoneer charges a fee.", "payoneer") is False
