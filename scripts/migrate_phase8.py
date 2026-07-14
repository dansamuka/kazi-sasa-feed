#!/usr/bin/env python3
"""Add Phase 8 NGO/UN profiles to packaged feed artifacts without changing legacy DTO fields."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from phase2_enrichment import Phase2Enricher, legacy_projection
from validate_feed import validate_feed

def load(p: Path): return json.loads(p.read_text(encoding='utf-8'))
def digest(rows):
    payload=json.dumps([legacy_projection(r) for r in rows],sort_keys=True,separators=(',',':'),ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()

def migrate(root: Path, path: Path):
    feed=load(path); rows=feed.get('opportunities',[])
    ids=[r.get('id') for r in rows]; before=digest(rows)
    enricher=Phase2Enricher(load(root/'config/organisations.json'),load(root/'config/african_locations.json'),load(root/'config/role_taxonomy.json'),load(root/'config/source_registry.json'),load(root/'config/investment_taxonomy.json'),load(root/'config/ngo_taxonomy.json'))
    feed['opportunities']=[enricher.enrich(r) for r in rows]
    meta=feed.setdefault('meta',{})
    meta.update({'feed_version':'3.6','opportunity_count':len(rows),'enterprise_adapter_version':'1.1','ngo_source_pack_version':'1.0','ngo_taxonomy_version':'1.0','ngo_classifier_version':'1.0'})
    if ids != [r.get('id') for r in feed['opportunities']]: raise RuntimeError('IDs or ordering changed')
    if before != digest(feed['opportunities']): raise RuntimeError('legacy projection changed')
    result=validate_feed(feed,load(root/'taxonomy.json'),load(root/'config/role_taxonomy.json'))
    if result.errors or result.warnings: raise RuntimeError(f'not clean: {result.errors} {result.warnings}')
    path.write_text(json.dumps(feed,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    return {'path':str(path),'opportunities':len(rows),'ngo_or_un':sum(bool((r.get('ngo_profile') or {}).get('is_ngo_or_un')) for r in feed['opportunities']),'programme_roles':sum(bool((r.get('ngo_profile') or {}).get('is_programme_role')) for r in feed['opportunities'])}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('paths',nargs='+'); ap.add_argument('--root',default=None); a=ap.parse_args()
    root=Path(a.root).resolve() if a.root else Path(__file__).resolve().parent.parent
    for raw in a.paths:
        p=Path(raw); p=p if p.is_absolute() else root/p
        print(json.dumps(migrate(root,p.resolve())))
if __name__=='__main__': main()
