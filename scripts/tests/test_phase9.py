from __future__ import annotations
import json, sys
from pathlib import Path

SCRIPTS=Path(__file__).resolve().parents[1]; REPO=SCRIPTS.parent
sys.path.insert(0,str(SCRIPTS))
from collectors.government_html import parse_government_table
from collectors.government_pdf import parse_tanzania_advert_text, parse_dpsa_text
from collectors.registry import collector_manifest
from phase2_enrichment import Phase2Enricher
from refresh_feed import FeedBuilder, FEED_VERSION
from reporting import build_government_coverage_report
from verify_published_output import verify_feed, verify_site


def load(path): return json.loads(Path(path).read_text(encoding='utf-8'))

def builder(enriched=True):
    sources=load(REPO/'config/source_registry.json')
    enricher=Phase2Enricher(load(REPO/'config/organisations.json'),load(REPO/'config/african_locations.json'),load(REPO/'config/role_taxonomy.json'),sources,load(REPO/'config/investment_taxonomy.json'),load(REPO/'config/ngo_taxonomy.json')) if enriched else None
    return FeedBuilder(load(REPO/'taxonomy.json'),sources,enricher=enricher)

def portal(code): return next(x for x in load(REPO/'config/public_portals.json')['portals'] if x['country_code']==code)

def test_phase9_registry_has_five_portals_and_three_enabled():
    rows=load(REPO/'config/public_portals.json')['portals']
    assert len(rows)==5
    assert {x['country_code'] for x in rows if x['enabled']}=={'KE','TZ','ZA'}
    assert all(x.get('disabled_reason') for x in rows if not x['enabled'])

def test_government_collectors_registered():
    keys={x['key'] for x in collector_manifest()}
    assert {'government_html','government_pdf','government_circular'} <= keys

def test_kenya_psc_table_parses_individual_vacancies():
    html='''<table><tr><th>Advert Number</th><th>Position</th><th>Job Scale</th><th>Ministry</th><th>Number of Vacancies</th><th>Years of Experience Required</th><th>Advert Date</th><th>Advert Close Date</th></tr><tr><td>D85/2026</td><td>Cook III</td><td>E</td><td>Correctional Services</td><td>18</td><td>0</td><td>17-06-2026</td><td>03-08-2026</td></tr></table>'''
    b=builder(); assert parse_government_table(b,portal('KE'),html)==1
    row=b.opportunities[0]; gp=row['government_profile']
    assert row['title']=='Cook III' and gp['advert_reference']=='D85/2026'
    assert gp['number_of_positions']==18 and gp['public_service_grade']=='E'
    assert row['deadline']=='2026-08-03T23:59:59Z'

def test_tanzania_pdf_text_splits_positions_and_captures_salary():
    text='''TANGAZO LA NAFASI ZA KAZI\n1.0 MWANDISHI MWENDESHA OFISI DARAJA LA II - Nafasi 5\n1.1 MAJUKUMU YA KAZI\nKuchapa barua.\n1.2 SIFA ZA MWOMBAJI\nStashahada.\n1.3 NGAZI YA MSHAHARA\nTGS C\n2.0 DEREVA DARAJA II - Nafasi 4\n2.1 MAJUKUMU YA KAZI\nKuendesha gari.\n2.3 NGAZI YA MSHAHARA\nTGS B\nWaombaji wote lazima wawe raia wa Jamhuri ya Muungano wa Tanzania.\nMwisho wa kutuma maombi ya kazi ni tarehe 23 Julai, 2026.'''
    b=builder(); assert parse_tanzania_advert_text(b,portal('TZ'),text,'https://ajira.go.tz/a.pdf')==2
    assert {r['government_profile']['number_of_positions'] for r in b.opportunities}=={4,5}
    assert all(r['government_profile']['citizenship_required'] for r in b.opportunities)

def test_dpsa_text_splits_posts_and_fields():
    text='''POST 24/01 : DEPUTY DIRECTOR: FINANCE\nSALARY : R849 702 per annum\nCENTRE : Pretoria\nREQUIREMENTS : Degree and five years experience.\nCLOSING DATE : 31 July 2026\nPOST 24/02 : LEGAL ADMINISTRATION OFFICER\nSALARY : R444 036 per annum\nCENTRE : Cape Town\nREQUIREMENTS : LLB degree.\nCLOSING DATE : 31 July 2026'''
    b=builder(); assert parse_dpsa_text(b,portal('ZA'),text,'https://dpsa.gov.za/c24.pdf')==2
    assert b.opportunities[0]['government_profile']['advert_reference']=='24/01'
    assert b.opportunities[0]['location']['city']=='Pretoria'

def test_packaged_feed_phase9_profile_and_reports():
    feed=load(REPO/'feed.json')
    assert FEED_VERSION==feed['meta']['feed_version']=='3.8'
    assert all('government_profile' in row for row in feed['opportunities'])
    report=build_government_coverage_report(feed)
    assert report['report_version']=='1.0'

def test_phase9_publication_and_site_guards():
    feed=load(REPO/'feed.json')
    assert verify_feed(feed,'3.8',True,None,require_phase4=True,require_phase5=True,require_phase6=True,require_phase7=True,require_phase8=True,require_phase9=True)==[]
    html=(REPO/'docs/index.html').read_text(encoding='utf-8')
    # Site is rebuilt during release; this assertion protects required markers.
    assert verify_site(html,feed,require_phase3=True,require_phase6=True,require_phase7=True,require_phase8=True,require_phase9=True)==[]
