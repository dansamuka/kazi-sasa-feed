# Africa and Eligibility Certification Hardening

This release hardens Kazi Sasa's two most important trust questions:

1. Is the vacancy genuinely Africa-relevant?
2. What evidence shows that an African applicant may apply?

## Implemented controls

- Global country-code and country-name registry covering 249 territories.
- Detection of non-African ISO locations such as `Tashkent, UZ`.
- Removal of known non-African vacancies without an explicit Africa remit.
- Independent `africa_relevance` and `african_applicant_access` profiles.
- Structured government citizenship requirements override generic text. Explicit nationality wording is resolved through controlled African nationality terms; local recruitment alone is not mislabeled as citizenship.
- African duty station is no longer treated as proof of applicant eligibility.
- `likely_open` requires explicit or strong evidence.
- `certified_feed.json` provides a strict subset separate from the broad index.
- The site defaults to certified or conditional African-applicant access only; unverified Africa-relevant roles require an explicit filter choice.
- Government deduplication now uses country, institution, advert reference and
  title instead of shared portal or circular URLs.
- Certification CI gates block non-African leakage, weak eligibility claims,
  missing government nationality codes and excessive government dedup loss.

## Government deduplication

Government vacancies often share an application portal or one circular PDF.
Those shared URLs are no longer duplicate keys. Distinct posts survive when
advert references or titles differ.

## Publication artifacts

- `feed.json`: broad audited Africa-oriented index.
- `certified_feed.json`: strict access-certified subset.
- `reports/africa_eligibility_certification_report.json`
- `reports/rejected_records.json`
- `reports/deduplication_report.json`

## Honest interpretation

`africa_based_confirmed` proves location, not eligibility. `unknown` applicant
access is displayed as unverified. A citizenship-restricted Kenyan role is
certified for Kenyan citizens specifically, not for African citizens generally.
