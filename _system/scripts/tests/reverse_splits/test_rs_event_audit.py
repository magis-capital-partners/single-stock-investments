"""Conservative filing-clause repair never promotes a historical reference to a new announcement."""
import pytest

from reverse_splits.event_audit import audit_clause, ratio


def test_past_split_is_not_a_new_announcement_even_with_prior_authorization():
    text='On September 11, 2023, Company effected a reverse stock split at a ratio of one-for-two hundred. The reverse stock split became effective as of 5:00 p.m. Eastern Time on September 11, 2023. Previously stockholders approved a reverse split between one-for-80 and one-for-200.'
    a=audit_clause(text,'2023-09-15')
    assert a['category']=='historical_reference' and not a['eligible']
    assert a['dated_actions'][0]['ratio']==pytest.approx(.005)


def test_clock_and_timezone_do_not_hide_future_date_or_decimal_ratio():
    text='The proposed reverse stock split will become effective at 12:01 a.m., Eastern Time, on September 23, 2026. Every 12.62 shares will be automatically combined and converted into one share.'
    a=audit_clause(text,'2026-09-15')
    assert a['announced_ex_date']=='2026-09-23' and a['exact_ratio']==pytest.approx(1/12.62)


def test_authorization_has_no_final_ratio_or_execution_date():
    a=audit_clause('Stockholders approved a proposal to authorize a reverse stock split at a ratio ranging from 1-for-5 to 1-for-25 at Board discretion.','2025-09-25')
    assert a['category']=='authorization_or_proposal' and a['eligible']
    assert a['announced_ex_date'] is None and a['exact_ratio'] is None


def test_trading_date_takes_precedence_over_friday_legal_effective_time():
    text='The reverse stock split will become effective at 5 p.m. on Friday, April 5, 2024. Common stock will begin trading on a post Reverse Stock Split basis on Monday, April 8, 2024.'
    a=audit_clause(text,'2024-04-05')
    assert a['announced_ex_date']=='2024-04-08'


def test_retroactive_earnings_reference_and_unknown_clause_do_not_qualify():
    assert not audit_clause('EPS amounts retroactively adjusted for the cumulative 1-for-25 reverse stock split.','2026-09-16')['eligible']
    assert not audit_clause('The reverse stock split is mentioned here.','2026-09-16')['eligible']


def test_full_word_and_decimal_ratios_are_not_truncated():
    assert ratio('one-for-two hundred')==.005
    assert ratio('one-for-one hundred twenty-five')==.008
    assert ratio('1-for-12.62')==pytest.approx(1/12.62)


def test_missing_cached_text_is_ineligible_and_dates_without_comma_still_parse():
    assert audit_clause('', '2026-01-01')['category'] == 'missing_cached_text'
    a = audit_clause('The reverse stock split will become effective on January 5 2027.', '2026-12-20')
    assert a['announced_ex_date'] == '2027-01-05'
