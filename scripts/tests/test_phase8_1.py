from __future__ import annotations
import json, sys
from pathlib import Path

SCRIPTS=Path(__file__).resolve().parents[1]; REPO=SCRIPTS.parent
sys.path.insert(0,str(SCRIPTS))
from collectors.official_common import choose_job_title, has_vacancy_evidence, is_official_opportunity_in_scope, is_valid_job_title, opportunity_from_page
from classifiers.ngo import NGOClassifier
from refresh_feed import FeedBuilder


def load(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def builder(): return FeedBuilder(load(REPO/'taxonomy.json'), load(REPO/'config/source_registry.json'))

def target():
    return {'organisation_id':'unicef','name':'UNICEF','type':'multilateral','listing_url':'https://jobs.unicef.org/', 'default_specialisations':['programme_management']}

def test_invalid_detail_title_never_overrides_valid_listing_title():
    assert choose_job_title('Junior Evaluator, Nairobi', 'JavaScript is disabled', 'UNICEF') == 'Junior Evaluator, Nairobi'
    assert not is_valid_job_title('JavaScript is disabled')

def test_generic_policy_and_landing_titles_are_rejected():
    for title in ('Careers','Military veterans','Equal employment opportunity - FHI 360','Population Services International'):
        assert not is_valid_job_title(title, 'Population Services International' if title.startswith('Population') else None)

def test_page_requires_vacancy_specific_evidence_and_preserves_listing_title():
    html='<html><head><title>JavaScript is disabled</title></head><body><p>Requirements: degree.</p><p>Closing date: 31 July 2026.</p></body></html>'
    row=opportunity_from_page(builder(),target(),title='Junior Evaluator',url='https://jobs.unicef.org/job/123456/junior-evaluator',page_html=html,context_text='Junior Evaluator Requirements Closing date: 31 July 2026',source_name='PageUp-hosted institutional board',prefix='pageup')
    assert row and row['title']=='Junior Evaluator'
    assert row['specialisations'] == []
    assert row['source_context_specialisations'] == ['programme_management']

def test_generic_careers_link_is_not_published_as_job():
    html='<html><head><title>Careers</title></head><body>Explore our culture and military veterans policy.</body></html>'
    assert opportunity_from_page(builder(),target(),title='Careers',url='https://example.org/careers',page_html=html,context_text='Careers',source_name='Official',prefix='official') is None

def test_multilateral_bank_is_not_ngo_un_by_type_alone():
    classifier=NGOClassifier(load(REPO/'config/ngo_taxonomy.json'))
    result=classifier.classify({'title':'Legal Analyst','organisation':{'type_detail':'multilateral'},'specialisations':['legal_services']})
    assert result.is_ngo_or_un is False
    assert result.classification == 'not_ngo_un'

def test_un_agency_support_role_remains_institutional_support():
    classifier=NGOClassifier(load(REPO/'config/ngo_taxonomy.json'))
    result=classifier.classify({'title':'Software Engineer','organisation':{'type_detail':'un_agency'},'specialisations':['software_engineering']})
    assert result.is_ngo_or_un is True
    assert result.is_programme_role is False


def test_vacancy_evidence_recognises_real_job_sections():
    html='<h1>Programme Officer</h1><p>Job reference: PO-123</p><h2>Responsibilities</h2><p>Lead delivery.</p>'
    assert has_vacancy_evidence(html,'https://example.org/jobs/po-123','Programme Officer')

def test_known_non_african_official_role_requires_africa_remit():
    location={'country':'United States','is_african':False,'is_remote_from_kenya':False}
    assert not is_official_opportunity_in_scope(location,'Legal Analyst','Based in Washington DC')
    assert is_official_opportunity_in_scope(location,'Africa Region Legal Analyst','Based in Washington DC')

def test_missing_location_official_role_remains_pending_not_dropped():
    location={'country':None,'is_african':False,'is_remote_from_kenya':False}
    assert is_official_opportunity_in_scope(location,'Programme Officer','')
