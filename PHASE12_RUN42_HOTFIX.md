# Phase 12 run #42 hotfix

Run #42 collected 640 government-circular rows and correctly consolidated many
repeated posts that appeared in both a complete circular and department-specific
PDFs. The certification gate incorrectly treated every safe consolidation as
lost data and reported 49.9% government loss.

This hotfix:

- excludes government records from broad semantic/description deduplication;
- deduplicates government posts only by stable ID or explicit government
  identity (country, institution, advert reference and title);
- separates safe duplicate consolidation from destructive/unexplained loss;
- gates only destructive loss at the 5% threshold;
- retains total removal and consolidation rates as transparent audit metrics.
