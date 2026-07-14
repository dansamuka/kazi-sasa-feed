# Phase 12 run #41 hotfix

This release fixes the live-refresh validation failure caused by an NGO profile
confidence above the schema maximum. Multiple evidence signals could previously
produce a score above 1.0. Confidence is now clamped defensively in both the
classifier and its serialized profile.

It also reduces operational log noise by emitting each unmapped taxonomy warning
once per source term, deriving ATS industries from canonical specialisations
instead of raw employer department labels, and suppressing the known BeautifulSoup
XML-as-HTML diagnostic where tolerant official-site parsing is intentional.
