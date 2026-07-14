import json
from pathlib import Path

from classifiers.africa_access import AfricaAccessClassifier
from certification_gates import evaluate, build_certified_feed
from phase2_enrichment import Phase2Enricher
from pipeline.deduplicate import deduplicate_opportunities
from migrate_phase12 import migrate_data
from refresh_feed import FeedBuilder
from validate_feed import validate_feed

REPO = Path(__file__).resolve().parents[2]


def load(path):
    return json.loads((REPO / path).read_text(encoding='utf-8'))


def enricher():
    return Phase2Enricher(
        load('config/organisations.json'),
        load('config/african_locations.json'),
        load('config/role_taxonomy.json'),
        load('config/source_registry.json'),
        load('config/investment_taxonomy.json'),
        load('config/ngo_taxonomy.json'),
        load('config/global_country_codes.json'),
    )


def base(title='Programme Officer', location='Nairobi, KE', summary=''):
    return {
        'id': 'test-role', 'title': title, 'opportunity_type': 'job',
        'organisation': {'name': 'Test Employer', 'type': 'private', 'verified': True},
        'location': {'raw': location, 'country': None, 'region': None, 'is_remote_from_kenya': False, 'scope': None, 'relocation_country': None},
        'work_mode': None, 'seniority': None, 'categories': [], 'specialisations': [],
        'industry': None, 'skills_required': [], 'skills_preferred': [],
        'posted_at': None, 'deadline': None, 'deadline_confidence': 'unknown',
        'years_experience_min': None, 'years_experience_max': None,
        'education_required': None, 'education_field': [], 'languages_required': [],
        'contract_type': 'unknown',
        'source': {'name': 'Official employer', 'url': 'https://example.org/jobs', 'confidence': 'official', 'last_seen_at': '2026-07-14T00:00:00Z', 'kind': 'employer_official'},
        'apply_url': 'https://example.org/jobs/1', 'apply_is_official': True,
        'flags': [], 'eligibility_notes': None, 'summary': summary, 'raw_description_url': 'https://example.org/jobs/1',
    }


def test_known_non_african_iso_is_detected():
    row = enricher().enrich(base(location='Tashkent, UZ'))
    assert row['location']['country_code'] == 'UZ'
    assert row['location']['known_non_african'] is True
    assert row['africa_relevance']['status'] == 'non_african'


def test_african_duty_station_does_not_prove_access():
    row = enricher().enrich(base(location='Nairobi, KE'))
    assert row['africa_relevance']['status'] == 'africa_based_confirmed'
    assert row['african_applicant_access']['status'] == 'unknown'
    assert row['eligibility']['status'] == 'uncertain'


def test_structured_government_citizenship_overrides_text():
    row = base(title='Principal Analyst', location='Kenya')
    row['government_fields'] = {
        'citizenship_required': True,
        'eligible_nationalities': ['KE'],
        'advert_reference': 'PSC/1/2026',
    }
    row['organisation'] = {'name': 'Kenya Public Service Commission', 'type': 'government', 'verified': True}
    result = enricher().enrich(row)
    assert result['african_applicant_access']['status'] == 'confirmed_specific_african_nationality'
    assert result['african_applicant_access']['eligible_nationalities'] == ['KE']
    assert result['eligibility']['status'] == 'citizenship_restricted'


def test_explicit_international_recruitment_is_certified():
    row = enricher().enrich(base(summary='International applicants are welcome and relocation support is provided.'))
    assert row['african_applicant_access']['status'] == 'confirmed_international_recruitment'
    assert row['african_applicant_access']['evidence_strength'] == 'explicit'


def test_remote_global_without_africa_access_is_not_default_visible():
    row = base(location='Remote worldwide')
    row['work_mode'] = 'remote_global'
    result = enricher().enrich(row)
    assert result['africa_relevance']['status'] == 'global_access_unconfirmed'
    assert result['africa_relevance']['default_visible'] is False


def test_non_african_africa_remit_is_retained_conditionally():
    row = enricher().enrich(base(title='Africa Regional Director', location='Washington, US'))
    assert row['africa_relevance']['status'] == 'africa_remit_non_african_location'
    assert row['africa_relevance']['default_visible'] is True


def government_row(identifier, reference, title, url='https://psckjobs.go.ke'):
    row = base(title=title, location='Kenya')
    row['id'] = identifier
    row['apply_url'] = url
    row['raw_description_url'] = url
    row['source']['kind'] = 'government_official'
    row['government_profile'] = {
        'is_government_or_public_service': True,
        'institution_type': 'government',
        'registry_id': 'kenya-public-service-commission',
        'source_pack': 'phase9_government_wave1',
        'phase9_priority_portal': True,
        'phase10_kenya_public_institution': False,
        'public_institution_category': None,
        'advert_reference': reference,
        'public_service_grade': None,
        'salary_scale': None,
        'number_of_positions': 1,
        'citizenship_required': True,
        'eligible_nationalities': ['KE'],
        'application_method': 'PSCIMS',
        'application_form_url': url,
        'internal_only': False,
        'county_or_region_requirement': None,
        'source_document_url': None,
    }
    return row


def test_government_posts_sharing_portal_url_are_not_collapsed():
    first = government_row('gov-1', 'PSC/1/2026', 'Economist')
    second = government_row('gov-2', 'PSC/2/2026', 'Legal Officer')
    kept, report = deduplicate_opportunities([first, second])
    assert len(kept) == 2
    assert report['government_loss_percent'] == 0.0


def test_exact_government_duplicate_is_removed_by_reference_and_title():
    first = government_row('gov-1', 'PSC/1/2026', 'Economist')
    second = government_row('gov-2', 'PSC/1/2026', 'Economist')
    kept, report = deduplicate_opportunities([first, second])
    assert len(kept) == 1
    assert report['government_removed_count'] == 1


def test_feed_builder_rejects_known_non_african_without_remit():
    builder = FeedBuilder(load('taxonomy.json'), load('config/source_registry.json'), enricher=enricher())
    builder.add(base(location='Toronto, CA'))
    assert builder.opportunities == []
    assert builder.rejected_scope[0]['reason'] == 'known_non_african_without_africa_remit'


def test_certification_gate_rejects_weak_likely_open():
    row = enricher().enrich(base(summary='Applications from Africa are welcome.'))
    row['african_applicant_access']['status'] = 'likely_open'
    row['african_applicant_access']['evidence_strength'] = 'none'
    report = evaluate({'meta': {'feed_version': '3.9'}, 'opportunities': [row]}, {'government_loss_percent': 0})
    assert any('likely-open' in error for error in report['errors'])


def test_certified_feed_only_contains_supported_rows():
    certified = enricher().enrich(base(summary='International applicants are welcome.'))
    unknown = enricher().enrich(base(title='Operations Officer'))
    result = build_certified_feed({'meta': {'feed_version': '3.9'}, 'opportunities': [certified, unknown]})
    assert [row['id'] for row in result['opportunities']] == ['test-role']


def test_current_feed_can_be_migrated_to_phase12_and_validates_cleanly():
    # The repository-root feed is a mutable publication artifact. On a live
    # checkout it may still be the last successful pre-certification feed when
    # offline tests begin, so validate the Phase 12 migration in memory rather
    # than assuming a fixed packaged record count or metadata state.
    feed, _stats = migrate_data(REPO, load('feed.json'))
    assert feed['meta']['feed_version'] == '3.8'
    assert feed['meta']['africa_access_certification_version'] == '1.0'
    assert all('africa_relevance' in row and 'african_applicant_access' in row for row in feed['opportunities'])
    result = validate_feed(feed, load('taxonomy.json'), load('config/role_taxonomy.json'))
    assert result.errors == []
    assert result.warnings == []


def test_site_defaults_to_africa_relevant_scope():
    app = (REPO / 'scripts/site/app.js').read_text(encoding='utf-8')
    template = (REPO / 'scripts/site/template.html').read_text(encoding='utf-8')
    assert "certificationScope: new Set(['certified'])" in app
    assert 'africaRelevancePill' in template
    assert 'africanAccessPill' in template
    assert 'certificationScopePill' in template


def test_local_recruitment_is_not_mislabeled_as_citizenship():
    result = enricher().enrich(base(summary='This is a locally recruited position. Local candidates only.'))
    access = result['african_applicant_access']
    assert access['status'] == 'local_only'
    assert access['citizenship_required'] is None
    assert access['work_authorisation_required'] is True
    assert access['eligible_nationalities'] == []


def test_explicit_nationality_requirement_uses_african_country_code():
    result = enricher().enrich(base(summary='Applicants must be Kenyan citizens.'))
    access = result['african_applicant_access']
    assert access['status'] == 'confirmed_specific_african_nationality'
    assert access['citizenship_required'] is True
    assert access['eligible_nationalities'] == ['KE']


def test_government_safe_duplicate_consolidation_is_not_certification_loss():
    first = government_row('gov-1', 'PSC/1/2026', 'Economist')
    second = government_row('gov-2', 'PSC/1/2026', 'Economist')
    kept, dedup = deduplicate_opportunities([first, second])
    assert len(kept) == 1
    assert dedup['government_safe_duplicate_count'] == 1
    assert dedup['government_duplicate_consolidation_percent'] == 50.0
    assert dedup['government_destructive_loss_count'] == 0
    assert dedup['government_destructive_loss_percent'] == 0.0
    report = evaluate({'meta': {'feed_version': '3.8'}, 'opportunities': kept}, dedup)
    assert not any('government deduplication loss' in error for error in report['errors'])


def test_government_posts_with_same_semantics_but_different_references_survive():
    first = government_row('gov-1', 'PSC/1/2026', 'Economist')
    second = government_row('gov-2', 'PSC/2/2026', 'Economist')
    # Deliberately make every broad semantic/content signal identical.  The
    # explicit advert reference must still preserve both government posts.
    for row in (first, second):
        row['summary'] = 'Identical public service vacancy description ' * 10
        row['location']['city'] = 'Nairobi'
        row['deadline'] = '2026-08-01T23:59:59Z'
    kept, report = deduplicate_opportunities([first, second])
    assert len(kept) == 2
    assert report['government_removed_count'] == 0
    assert report['government_destructive_loss_percent'] == 0.0


def test_certification_gate_still_rejects_destructive_government_loss():
    report = evaluate(
        {'meta': {'feed_version': '3.8'}, 'opportunities': []},
        {'government_destructive_loss_percent': 5.1, 'government_duplicate_consolidation_percent': 49.9},
    )
    assert any('destructive government deduplication loss is 5.1%' in error for error in report['errors'])
