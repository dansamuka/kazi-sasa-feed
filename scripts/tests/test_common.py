"""Unit tests for scripts/collectors/_common.py's v3 extraction functions.

Run with: python3 -m pytest tests/ -v
(or, without pytest installed: python3 tests/test_common.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from collectors._common import (  # noqa: E402
    classify_industry, extract_contract_type, extract_education_requirement,
    extract_languages_required, extract_years_experience, has_sponsorship_signal,
    infer_seniority, infer_work_mode, is_relevant_to_african_applicant,
    normalise_salary, parse_location,
)


def test_years_experience_range():
    assert extract_years_experience("5-8 years of experience required") == (5, 8)


def test_years_experience_minimum():
    assert extract_years_experience("Minimum 5 years of experience") == (5, None)


def test_years_experience_plus():
    assert extract_years_experience("10+ years in leadership") == (10, None)


def test_years_experience_bare():
    assert extract_years_experience("3 years experience needed") == (3, None)


def test_years_experience_none_found():
    assert extract_years_experience("No experience requirement stated") == (None, None)


def test_years_experience_empty_input():
    assert extract_years_experience(None) == (None, None)
    assert extract_years_experience("") == (None, None)


def test_years_experience_rejects_absurd_values():
    # 99 years is not a real job requirement - sanity bound should reject it
    result = extract_years_experience("99 years of experience required")
    assert result == (None, None), f"expected sanity rejection, got {result}"


def test_education_bachelor_and_masters():
    level, fields = extract_education_requirement("Bachelor's degree in Engineering is required; Master's preferred.")
    assert level == "masters"  # ceiling, not floor
    assert "engineering" in fields


def test_education_phd():
    level, fields = extract_education_requirement("PhD in Economics or related field required.")
    assert level == "phd"
    assert "economics" in fields


def test_education_none_found():
    level, fields = extract_education_requirement("No formal education requirement.")
    assert level is None
    assert fields == []


def test_languages_context_sensitive():
    result = extract_languages_required("Must be fluent in French and have working knowledge of Arabic.")
    assert set(result) == {"french", "arabic"}


def test_languages_no_false_positive_from_unrelated_mention():
    result = extract_languages_required("This role is funded by the French government but no language required.")
    assert result == [], f"expected no false positive, got {result}"


def test_contract_type_consultant():
    assert extract_contract_type("Consultant - Climate Finance", "6-month consultancy") == "consultant"


def test_contract_type_permanent_default():
    assert extract_contract_type("Software Engineer", "full-time permanent role") == "permanent"


def test_contract_type_unknown_when_no_signal():
    assert extract_contract_type("Generic Title", "no signal here") == "unknown"


def test_classify_industry_technology():
    assert classify_industry("Senior Backend Engineer", "Python and AWS experience") == "technology"


def test_classify_industry_financial_services():
    assert classify_industry("Credit Risk Analyst", "credit analysis and underwriting") == "financial_services"


def test_classify_industry_no_match_returns_none():
    assert classify_industry("Totally ambiguous title", "") is None


def test_infer_seniority_leadership():
    assert infer_seniority("Country Director - Kenya") == "leadership"


def test_infer_seniority_entry():
    assert infer_seniority("Software Engineering Intern") == "entry"


def test_infer_seniority_senior():
    assert infer_seniority("Senior Backend Engineer") == "senior"


def test_infer_seniority_none_when_ambiguous():
    assert infer_seniority("Backend Engineer") is None


def test_normalise_salary_monthly_kes_to_annual_usd():
    rates = {"KES": 0.0067, "USD": 1.0}
    result = normalise_salary(100000, 150000, "KES", "month", rates)
    assert result == (8040.0, 12060.0)


def test_normalise_salary_unknown_currency_returns_none():
    rates = {"USD": 1.0}
    assert normalise_salary(100, 200, "XYZ", "year", rates) == (None, None)


def test_normalise_salary_unknown_period_returns_none():
    rates = {"USD": 1.0}
    assert normalise_salary(100, 200, "USD", "fortnight", rates) == (None, None)


def test_parse_location_kenya_national():
    loc = parse_location("Nairobi, Kenya")
    assert loc["country"] == "Kenya"
    assert loc["scope"] == "national"
    assert loc["is_remote_from_kenya"] is False


def test_parse_location_remote_kenya():
    loc = parse_location("Remote - Kenya")
    assert loc["country"] == "Kenya"
    assert loc["is_remote_from_kenya"] is True


def test_parse_location_bare_remote_no_longer_defaults_relevant():
    """Tightened 2026-07-11 after real data showed this default drowned out
    genuinely-relevant postings with a flood of ambiguous "Remote" US-tech
    listings. Bare "Remote" with no country and no positive region signal
    should now be left ambiguous, not assumed relevant."""
    loc = parse_location("Remote")
    assert loc["is_remote_from_kenya"] is False
    assert loc["scope"] is None


def test_parse_location_remote_africa_is_relevant():
    loc = parse_location("Remote - Africa")
    assert loc["is_remote_from_kenya"] is True
    assert loc["scope"] == "international"


def test_parse_location_remote_global_is_relevant():
    loc = parse_location("Remote (Global)")
    assert loc["is_remote_from_kenya"] is True


def test_parse_location_remote_emea_is_relevant():
    loc = parse_location("Remote - EMEA")
    assert loc["is_remote_from_kenya"] is True


def test_parse_location_remote_us_only_not_relevant():
    """No African/global signal and no country match (Non-African hint
    catches this one via 'united states') - should not be marked relevant."""
    loc = parse_location("Remote - United States")
    assert loc["is_remote_from_kenya"] is False


def test_parse_location_empty_input():
    loc = parse_location(None)
    assert loc["country"] is None
    assert loc["scope"] is None


def test_is_relevant_to_african_applicant_kenya():
    assert is_relevant_to_african_applicant({"country": "Kenya", "is_remote_from_kenya": False}) is True


def test_is_relevant_to_african_applicant_us_rejected():
    assert is_relevant_to_african_applicant({"country": "United States", "is_remote_from_kenya": False}) is False


def test_is_relevant_to_african_applicant_remote_from_kenya():
    assert is_relevant_to_african_applicant({"country": None, "is_remote_from_kenya": True}) is True


def test_infer_work_mode_structured_hint_wins():
    assert infer_work_mode("Some office in Lagos", structured_hint="remote") == "remote_global"


def test_infer_work_mode_from_text_hybrid():
    assert infer_work_mode("Hybrid - Nairobi office") is None or infer_work_mode("Hybrid - Nairobi office") == "hybrid"


def test_parse_location_remote_us_abbreviation_now_detected():
    """Regression test for the real leaked-roles bug: 'Remote (US)' and
    'Remote-US' previously went undetected by naive substring matching
    (neither 'usa' nor 'united states' is a substring of 'us'), and got
    incorrectly marked relevant by a since-removed override in ashby.py."""
    loc = parse_location("Remote (US)")
    assert loc["country"] == "United States"
    assert loc["is_remote_from_kenya"] is False


def test_parse_location_remote_us_hyphenated_form():
    loc = parse_location("Remote-US")
    assert loc["country"] == "United States"
    assert loc["is_remote_from_kenya"] is False


def test_parse_location_uk_abbreviation_detected():
    loc = parse_location("Remote (UK)")
    assert loc["country"] == "United Kingdom"


def test_parse_location_us_substring_does_not_false_positive_on_unrelated_words():
    """'us' as a bare 2-letter code must not match inside words like
    'campus', 'focus', 'business' - word-boundary matching, not substring."""
    loc = parse_location("Business Development Manager - Lagos, Nigeria")
    assert loc["country"] == "Nigeria"


def test_has_sponsorship_signal_affirmative():
    assert has_sponsorship_signal("We offer visa sponsorship for this role.") is True
    assert has_sponsorship_signal("Relocation assistance provided for the right candidate.") is True


def test_has_sponsorship_signal_negation_correctly_excluded():
    """The much more common real-world phrasing - must not be treated as an offer."""
    assert has_sponsorship_signal("No visa sponsorship available for this position.") is False
    assert has_sponsorship_signal("We are unable to sponsor work visas at this time.") is False


def test_has_sponsorship_signal_no_mention_at_all():
    assert has_sponsorship_signal("A great opportunity to join our team in Austin.") is False
    assert has_sponsorship_signal(None) is False


def test_has_sponsorship_signal_bare_visa_mention_without_offer_is_not_a_signal():
    """A bare mention of 'visa' with no sponsorship claim shouldn't trigger -
    only the more specific phrases in _SPONSORSHIP_SIGNAL should."""
    assert has_sponsorship_signal("Candidates must already hold a valid US work visa.") is False


def test_parse_location_bare_worldwide_recognized_without_the_word_remote():
    """Regression test: remote-only job boards (Himalayas, RemoteOK,
    Remotive, Arbeitnow) very often just say "Worldwide" without ever using
    the literal word "remote", since the whole board is inherently remote.
    Found via testing this exact gap against real Remotive/RemoteOK mock
    data - "Worldwide" alone was previously falling through undetected."""
    loc = parse_location("Worldwide")
    assert loc["is_remote_from_kenya"] is True
    assert loc["scope"] == "international"


def test_parse_location_bare_anywhere_also_recognized():
    loc = parse_location("Anywhere")
    assert loc["is_remote_from_kenya"] is True


ALL_TESTS = [obj for name, obj in list(globals().items()) if name.startswith("test_")]


def run_all():
    passed, failed = 0, 0
    for test_fn in ALL_TESTS:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {test_fn.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"ERROR: {test_fn.__name__}: {e}")
    print(f"\n{passed} passed, {failed} failed out of {passed + failed}")
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
