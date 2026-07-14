const DATA = JSON.parse(document.getElementById('feedData').textContent);
const META = DATA.__meta__;
const ITEMS = DATA.items;
const PAGE_SIZE = 30;

const EXPERIENCE_LABELS = {
  entry: 'Entry level', mid: 'Associate', senior: 'Mid-Senior level', leadership: 'Director+',
};
const JOB_TYPE_LABELS = {
  full_time: 'Full-time', part_time: 'Part-time', contract: 'Contract',
  temporary: 'Temporary', volunteer: 'Volunteer', internship: 'Internship',
  fellowship: 'Fellowship', grant: 'Grant', programme: 'Programme',
};
const CONTRACT_TO_JOB_TYPE = {
  permanent: 'full_time', contract: 'contract', part_time: 'part_time',
  fixed_term: 'temporary', consultant: 'contract', volunteer: 'volunteer',
};
const REMOTE_LABELS = { onsite: 'On-site', hybrid: 'Hybrid', remote: 'Remote' };
const DATE_LABELS = { '24h': 'Past 24 hours', week: 'Past week', month: 'Past month' };
const DFI_RELEVANCE_LABELS = {
  direct_investment: 'Direct DFI investment',
  institutional_role: 'DFI institutional role',
  adjacent_experience: 'DFI-adjacent experience',
  none: 'No DFI relevance',
};
const DFI_INSTITUTION_LABELS = { true: 'DFI / multilateral only', false: 'Other organisations' };
const NGO_CLASS_LABELS = {
  humanitarian: 'Humanitarian programme', development: 'Development programme',
  technical_programme: 'Technical programme', institutional_support: 'Institutional support',
  not_ngo_un: 'Other organisations',
};
const NGO_INSTITUTION_LABELS = { true: 'NGO / UN / development only', false: 'Other organisations' };
const INVESTMENT_CLASS_LABELS = {
  core_investment: 'Core investment',
  investment_adjacent: 'Investment adjacent',
  institutional_support: 'Investment/DFI institution',
  not_investment: 'Not investment',
};
const ELIGIBILITY_LABELS = {
  eligible: 'Eligible',
  likely_eligible: 'Likely eligible',
  uncertain: 'Eligibility uncertain',
  local_only: 'Local applicants only',
  citizenship_restricted: 'Citizenship restricted',
  internal_only: 'Internal applicants only',
  ineligible: 'Not eligible',
};
const AFRICA_RELEVANCE_LABELS = {
  africa_based_confirmed: 'Confirmed Africa-based',
  africa_regional: 'Africa regional / remit',
  remote_confirmed_open_to_africa: 'Remote confirmed open to Africa',
  africa_remit_non_african_location: 'Africa remit, non-African base',
  official_location_pending: 'Official role, location pending',
  global_access_unconfirmed: 'Global access unconfirmed',
  non_african: 'Non-African',
  unresolved: 'Location unresolved',
};
const AFRICAN_ACCESS_LABELS = {
  confirmed_any_african_national: 'Open to any African nationality',
  confirmed_specific_african_nationality: 'Specific African nationality required',
  confirmed_international_recruitment: 'International recruitment confirmed',
  likely_open: 'Likely open to African applicants',
  work_authorisation_required: 'Local work authorisation required',
  local_only: 'Local recruitment only',
  internal_only: 'Internal applicants only',
  unknown: 'African applicant access unverified',
  not_open: 'Not open to African applicants',
};
const CERTIFICATION_SCOPE_LABELS = {
  certified: 'Certified / conditional access',
  africa_unverified: 'Africa-relevant, access unverified',
  broader_index: 'Broader index / location pending',
};

function newFilterState(sortBy = 'relevance', expanded = new Set()) {
  return {
    keyword: '', location: '', datePosted: '',
    experience: new Set(), jobType: new Set(), remote: new Set(),
    company: new Set(), industry: new Set(), country: new Set(), city: new Set(),
    roleFamily: new Set(), investmentClass: new Set(), investmentTrack: new Set(), dfiInstitution: new Set(), dfiRelevance: new Set(), ngoInstitution: new Set(), ngoTrack: new Set(), government: new Set(), governmentGrade: new Set(), publicInstitution: new Set(), publicInstitutionCategory: new Set(), multinational: new Set(), multinationalSector: new Set(), orgType: new Set(), eligibility: new Set(), africaRelevance: new Set(), africanAccess: new Set(), certificationScope: new Set(['certified']),
    sortBy, page: 1, expanded,
  };
}

let state = newFilterState();

function humanize(value) {
  if (!value) return null;
  return String(value).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#039;');
}

function escapeAttr(value) {
  return escapeHtml(value).replace(/`/g, '&#096;');
}

function fmtDate(iso) {
  if (!iso) return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date.toISOString().slice(0, 10);
}

function timeAgo(iso) {
  if (!iso) return null;
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;
  const hours = (Date.now() - then.getTime()) / 36e5;
  if (hours < 0) return null;
  if (hours < 1) return 'Just posted';
  if (hours < 24) return `${Math.floor(hours)}h ago`;
  const days = Math.floor(hours / 24);
  return days < 30 ? `${days}d ago` : fmtDate(iso);
}

function jobTypeValue(item) {
  if (item.type && item.type !== 'job') return item.type;
  return CONTRACT_TO_JOB_TYPE[item.contract] || null;
}

function remoteValue(item) {
  if (!item.work_mode) return null;
  if (item.work_mode === 'onsite') return 'onsite';
  if (item.work_mode === 'hybrid') return 'hybrid';
  return 'remote';
}

function withinDatePosted(item, filterValue) {
  if (!filterValue) return true;
  if (!item.posted) return false;
  const posted = new Date(item.posted);
  if (Number.isNaN(posted.getTime())) return false;
  const hours = (Date.now() - posted.getTime()) / 36e5;
  if (filterValue === '24h') return hours <= 24;
  if (filterValue === 'week') return hours <= 24 * 7;
  if (filterValue === 'month') return hours <= 24 * 30;
  return true;
}

function positionDawnMarker() {
  const generated = new Date(META.generated_at);
  const next = new Date(META.next_expected_update);
  const total = next - generated;
  const elapsed = new Date() - generated;
  let percent = total > 0 ? (elapsed / total) * 100 : 50;
  percent = Math.max(2, Math.min(98, percent));
  document.getElementById('dawnMarker').style.left = `${percent}%`;
}

function renderHeroStats() {
  const sources = new Set(ITEMS.map(item => item.source).filter(Boolean));
  const roleFamilies = new Set(ITEMS.map(item => item.role_family).filter(Boolean));
  const countries = new Set(ITEMS.map(item => item.country).filter(Boolean));
  const cities = new Set(ITEMS.map(item => item.city).filter(Boolean));
  const stats = [
    { num: ITEMS.length, label: META.bootstrap_schema_migration ? 'Available roles' : 'Live roles' },
    { num: sources.size, label: 'Sources' },
    { num: roleFamilies.size, label: 'Role families' },
    { num: `${countries.size}/${cities.size}`, label: 'Countries / cities' },
  ];
  document.getElementById('heroStats').innerHTML = stats.map(stat =>
    `<div class="hero-stat"><div class="num"><span>${escapeHtml(stat.num)}</span></div><div class="lbl">${escapeHtml(stat.label)}</div></div>`
  ).join('');
}

function renderSourceStrip() {
  const sources = [...new Set(ITEMS.map(item => item.source).filter(Boolean))].sort();
  document.getElementById('sourceStrip').innerHTML =
    '<span class="tag">Sources</span> ' + sources.map(escapeHtml).join(' &middot; ');
}

function renderFreshnessStatus() {
  const banner = document.getElementById('freshnessBanner');
  if (!banner) return;
  if (META.bootstrap_schema_migration && !META.live_refresh_completed) {
    banner.innerHTML = '<span class="live-dot"></span> LAST-KNOWN-GOOD DATA &mdash; Africa/access certification schema is live; source refresh retry pending';
  }
}

function renderFooterMeta() {
  const sourceTime = META.source_data_generated_at || META.generated_at;
  const generated = new Date(sourceTime);
  const timeText = Number.isNaN(generated.getTime()) ? sourceTime : generated.toISOString().slice(0, 16).replace('T', ' ');
  const suffix = META.bootstrap_schema_migration && !META.live_refresh_completed ? ' · schema migrated without claiming a fresh source pull' : '';
  document.getElementById('footerMeta').textContent = `Source data as of ${timeText} UTC · schema v${META.feed_version}${suffix}`;
}

function selected(set, value) {
  return set.size === 0 || set.has(value);
}

function getFiltered() {
  const keyword = state.keyword.trim().toLowerCase();
  const location = state.location.trim().toLowerCase();

  const filtered = ITEMS.filter(item => {
    if (keyword) {
      const haystack = [
        item.title, item.org, item.summary, item.industry, item.role_family,
        item.role_subfamily, item.org_type, item.eligibility, item.investment_track,
        item.investment_classification, item.dfi_relevance, item.institution_type,
        item.ngo_classification, item.ngo_track, item.ngo_organisation_group,
        item.africa_relevance, item.african_applicant_access,
        ...(item.thematic_sectors || []),
      ].filter(Boolean).join(' ').toLowerCase();
      if (!haystack.includes(keyword)) return false;
    }
    if (location) {
      const haystack = [item.loc_raw, item.city, item.country, item.country_code]
        .filter(Boolean).join(' ').toLowerCase();
      if (!haystack.includes(location)) return false;
    }
    if (!withinDatePosted(item, state.datePosted)) return false;
    if (!selected(state.experience, item.seniority)) return false;
    if (!selected(state.jobType, jobTypeValue(item))) return false;
    if (!selected(state.remote, remoteValue(item))) return false;
    if (!selected(state.company, item.org)) return false;
    if (!selected(state.industry, item.industry)) return false;
    if (!selected(state.country, item.country)) return false;
    if (!selected(state.city, item.city)) return false;
    if (!selected(state.roleFamily, item.role_family)) return false;
    if (!selected(state.investmentClass, item.investment_classification)) return false;
    if (!selected(state.investmentTrack, item.investment_track)) return false;
    if (!selected(state.dfiInstitution, String(Boolean(item.is_dfi_or_multilateral)))) return false;
    if (!selected(state.dfiRelevance, item.dfi_relevance)) return false;
    if (!selected(state.ngoInstitution, String(Boolean(item.is_ngo_or_un)))) return false;
    if (!selected(state.ngoTrack, item.ngo_track)) return false;
    if (!selected(state.government, String(Boolean(item.is_government_or_public_service)))) return false;
    if (!selected(state.governmentGrade, item.public_service_grade)) return false;
    if (!selected(state.publicInstitution, String(Boolean(item.is_kenya_public_institution)))) return false;
    if (!selected(state.publicInstitutionCategory, item.public_institution_category)) return false;
    if (!selected(state.multinational, String(Boolean(item.is_multinational)))) return false;
    if (!selected(state.multinationalSector, item.multinational_sector)) return false;
    if (!selected(state.africaRelevance, item.africa_relevance)) return false;
    if (!selected(state.africanAccess, item.african_applicant_access)) return false;
    const certificationScope = item.certified_default_view ? 'certified' : item.africa_default_visible ? 'africa_unverified' : 'broader_index';
    if (!selected(state.certificationScope, certificationScope)) return false;
    if (!selected(state.orgType, item.org_type)) return false;
    if (!selected(state.eligibility, item.eligibility)) return false;
    return true;
  });

  if (state.sortBy === 'recent') {
    return [...filtered].sort((a, b) => {
      const first = a.posted ? new Date(a.posted).getTime() : -Infinity;
      const second = b.posted ? new Date(b.posted).getTime() : -Infinity;
      return second - first;
    });
  }
  return filtered;
}

const PILL_CONFIGS = [
  { key: 'datePosted', pillId: 'datePill', dropdownId: 'dateDropdown', label: 'Date posted', kind: 'single' },
  { key: 'country', pillId: 'countryPill', dropdownId: 'countryDropdown', label: 'Country', kind: 'multi' },
  { key: 'city', pillId: 'cityPill', dropdownId: 'cityDropdown', label: 'City', kind: 'multi' },
  { key: 'roleFamily', pillId: 'roleFamilyPill', dropdownId: 'roleFamilyDropdown', label: 'Role family', kind: 'multi' },
  { key: 'investmentClass', pillId: 'investmentClassPill', dropdownId: 'investmentClassDropdown', label: 'Investment relevance', kind: 'multi' },
  { key: 'investmentTrack', pillId: 'investmentTrackPill', dropdownId: 'investmentTrackDropdown', label: 'Investment track', kind: 'multi' },
  { key: 'dfiInstitution', pillId: 'dfiInstitutionPill', dropdownId: 'dfiInstitutionDropdown', label: 'DFI / multilateral', kind: 'multi' },
  { key: 'dfiRelevance', pillId: 'dfiRelevancePill', dropdownId: 'dfiRelevanceDropdown', label: 'DFI relevance', kind: 'multi' },
  { key: 'ngoInstitution', pillId: 'ngoInstitutionPill', dropdownId: 'ngoInstitutionDropdown', label: 'NGO / UN', kind: 'multi' },
  { key: 'ngoTrack', pillId: 'ngoTrackPill', dropdownId: 'ngoTrackDropdown', label: 'NGO / development track', kind: 'multi' },
  { key: 'government', pillId: 'governmentPill', dropdownId: 'governmentDropdown', label: 'Government / public service', kind: 'multi' },
  { key: 'governmentGrade', pillId: 'governmentGradePill', dropdownId: 'governmentGradeDropdown', label: 'Public-service grade', kind: 'multi' },
  { key: 'publicInstitution', pillId: 'publicInstitutionPill', dropdownId: 'publicInstitutionDropdown', label: 'Kenya public institutions', kind: 'multi' },
  { key: 'publicInstitutionCategory', pillId: 'publicInstitutionCategoryPill', dropdownId: 'publicInstitutionCategoryDropdown', label: 'Public institution category', kind: 'multi' },
  { key: 'multinational', pillId: 'multinationalPill', dropdownId: 'multinationalDropdown', label: 'Multinationals', kind: 'multi' },
  { key: 'multinationalSector', pillId: 'multinationalSectorPill', dropdownId: 'multinationalSectorDropdown', label: 'Multinational sector', kind: 'multi' },
  { key: 'certificationScope', pillId: 'certificationScopePill', dropdownId: 'certificationScopeDropdown', label: 'Certification scope', kind: 'multi' },
  { key: 'africaRelevance', pillId: 'africaRelevancePill', dropdownId: 'africaRelevanceDropdown', label: 'Africa relevance', kind: 'multi' },
  { key: 'africanAccess', pillId: 'africanAccessPill', dropdownId: 'africanAccessDropdown', label: 'African applicant access', kind: 'multi' },
  { key: 'orgType', pillId: 'orgTypePill', dropdownId: 'orgTypeDropdown', label: 'Organisation type', kind: 'multi' },
  { key: 'eligibility', pillId: 'eligibilityPill', dropdownId: 'eligibilityDropdown', label: 'Eligibility', kind: 'multi' },
  { key: 'experience', pillId: 'expPill', dropdownId: 'expDropdown', label: 'Experience level', kind: 'multi' },
  { key: 'jobType', pillId: 'jobTypePill', dropdownId: 'jobTypeDropdown', label: 'Job type', kind: 'multi' },
  { key: 'remote', pillId: 'remotePill', dropdownId: 'remoteDropdown', label: 'On-site/remote', kind: 'multi' },
  { key: 'company', pillId: 'companyPill', dropdownId: 'companyDropdown', label: 'Company', kind: 'multi' },
  { key: 'industry', pillId: 'industryPill', dropdownId: 'industryDropdown', label: 'Industry', kind: 'multi' },
];

function valueFor(item, key) {
  const map = {
    experience: item.seniority,
    jobType: jobTypeValue(item),
    remote: remoteValue(item),
    company: item.org,
    industry: item.industry,
    country: item.country,
    city: item.city,
    roleFamily: item.role_family,
    investmentClass: item.investment_classification,
    investmentTrack: item.investment_track,
    dfiInstitution: String(Boolean(item.is_dfi_or_multilateral)),
    dfiRelevance: item.dfi_relevance,
    ngoInstitution: String(Boolean(item.is_ngo_or_un)),
    ngoTrack: item.ngo_track,
    government: String(Boolean(item.is_government_or_public_service)),
    governmentGrade: item.public_service_grade,
    publicInstitution: String(Boolean(item.is_kenya_public_institution)),
    publicInstitutionCategory: item.public_institution_category,
    multinational: String(Boolean(item.is_multinational)),
    multinationalSector: item.multinational_sector,
    africaRelevance: item.africa_relevance,
    africanAccess: item.african_applicant_access,
    certificationScope: item.certified_default_view ? 'certified' : item.africa_default_visible ? 'africa_unverified' : 'broader_index',
    orgType: item.org_type,
    eligibility: item.eligibility,
  };
  return map[key] || null;
}

function labelFor(key, value) {
  if (key === 'experience') return EXPERIENCE_LABELS[value] || humanize(value);
  if (key === 'jobType') return JOB_TYPE_LABELS[value] || humanize(value);
  if (key === 'remote') return REMOTE_LABELS[value] || humanize(value);
  if (key === 'eligibility') return ELIGIBILITY_LABELS[value] || humanize(value);
  if (key === 'africaRelevance') return AFRICA_RELEVANCE_LABELS[value] || humanize(value);
  if (key === 'africanAccess') return AFRICAN_ACCESS_LABELS[value] || humanize(value);
  if (key === 'certificationScope') return CERTIFICATION_SCOPE_LABELS[value] || humanize(value);
  if (key === 'investmentClass') return INVESTMENT_CLASS_LABELS[value] || humanize(value);
  if (key === 'dfiInstitution') return DFI_INSTITUTION_LABELS[value] || humanize(value);
  if (key === 'dfiRelevance') return DFI_RELEVANCE_LABELS[value] || humanize(value);
  if (key === 'ngoInstitution') return NGO_INSTITUTION_LABELS[value] || humanize(value);
  if (key === 'government') return value === 'true' ? 'Government/public service' : 'Other employers';
  if (key === 'publicInstitution') return value === 'true' ? 'Kenya public institution' : 'Other organisations';
  if (key === 'multinational') return value === 'true' ? 'Multinational employer' : 'Other organisations';
  if (key === 'ngoTrack') return humanize(value);
  if (['industry', 'roleFamily', 'investmentTrack', 'ngoTrack', 'governmentGrade', 'publicInstitutionCategory', 'multinationalSector', 'orgType'].includes(key)) return humanize(value);
  return value;
}

function optionsFor(key) {
  const counts = {};
  ITEMS.forEach(item => {
    const value = valueFor(item, key);
    if (value) counts[value] = (counts[value] || 0) + 1;
  });
  const alphabetical = ['company', 'industry', 'country', 'city', 'roleFamily', 'investmentTrack', 'ngoTrack', 'governmentGrade', 'publicInstitutionCategory', 'multinationalSector', 'orgType'];
  const limit = key === 'company' ? 80 : key === 'city' ? 100 : 60;
  return Object.keys(counts)
    .map(value => ({ value, label: labelFor(key, value), count: counts[value] }))
    .sort((a, b) => alphabetical.includes(key) ? a.label.localeCompare(b.label) : b.count - a.count)
    .slice(0, limit);
}

function closeAllDropdowns() {
  document.querySelectorAll('.li-dropdown.open').forEach(element => element.classList.remove('open'));
  PILL_CONFIGS.forEach(config => {
    const pill = document.getElementById(config.pillId);
    const hasSelection = config.kind === 'single' ? Boolean(state.datePosted) : state[config.key].size > 0;
    pill.classList.toggle('active', hasSelection);
  });
}

function renderDropdown(config) {
  const element = document.getElementById(config.dropdownId);
  if (config.kind === 'single') {
    const options = [['', 'Any time'], ['24h', DATE_LABELS['24h']], ['week', DATE_LABELS.week], ['month', DATE_LABELS.month]];
    element.innerHTML = options.map(([value, label]) => `
      <label class="li-dropdown-item">
        <input type="radio" name="datePosted" value="${escapeAttr(value)}" ${state.datePosted === value ? 'checked' : ''}>
        ${escapeHtml(label)}
      </label>`).join('');
    element.querySelectorAll('input[type="radio"]').forEach(input => {
      input.addEventListener('change', () => {
        state.datePosted = input.value;
        state.page = 1;
        updatePillLabels();
        render();
      });
    });
    return;
  }

  const options = optionsFor(config.key);
  if (options.length === 0) {
    element.innerHTML = '<div class="li-dropdown-empty">No data for this filter yet</div>';
    return;
  }
  element.innerHTML = options.map(option => `
    <label class="li-dropdown-item">
      <input type="checkbox" data-key="${escapeAttr(config.key)}" value="${escapeAttr(option.value)}" ${state[config.key].has(option.value) ? 'checked' : ''}>
      <span>${escapeHtml(option.label)}</span>
      <span class="filter-count">${option.count}</span>
    </label>`).join('');
  element.querySelectorAll('input[type="checkbox"]').forEach(input => {
    input.addEventListener('change', () => {
      const values = state[config.key];
      if (input.checked) values.add(input.value); else values.delete(input.value);
      state.page = 1;
      updatePillLabels();
      render();
    });
  });
}

function updatePillLabels() {
  PILL_CONFIGS.forEach(config => {
    const pill = document.getElementById(config.pillId);
    if (config.kind === 'single') {
      pill.textContent = state.datePosted ? DATE_LABELS[state.datePosted] : config.label;
      pill.classList.toggle('active', Boolean(state.datePosted));
    } else {
      const count = state[config.key].size;
      pill.textContent = count ? `${config.label} (${count})` : config.label;
      pill.classList.toggle('active', count > 0);
    }
  });
}

function setupPills() {
  PILL_CONFIGS.forEach(config => {
    const pill = document.getElementById(config.pillId);
    const dropdown = document.getElementById(config.dropdownId);
    pill.addEventListener('click', event => {
      event.stopPropagation();
      const wasOpen = dropdown.classList.contains('open');
      closeAllDropdowns();
      if (!wasOpen) {
        renderDropdown(config);
        dropdown.classList.add('open');
        pill.classList.add('active');
      }
    });
    dropdown.addEventListener('click', event => event.stopPropagation());
  });
  document.addEventListener('click', closeAllDropdowns);
}

function confClass(confidence) {
  return `conf-${confidence || 'unverified'}`;
}

function eligibilityClass(status) {
  if (status === 'eligible' || status === 'likely_eligible') return 'eligibility-positive';
  if (status === 'local_only' || status === 'citizenship_restricted' || status === 'internal_only' || status === 'ineligible') return 'eligibility-restricted';
  return 'eligibility-uncertain';
}

function displayLocation(item) {
  if (item.city && item.country) return `${item.city}, ${item.country}`;
  return item.loc_raw || item.country || item.city || 'Location not specified';
}

function renderCard(item) {
  const expanded = state.expanded.has(item.id);
  const posted = timeAgo(item.posted);
  const chips = [];
  if (item.role_family) chips.push(`<span class="chip role-family">${escapeHtml(humanize(item.role_family))}</span>`);
  if (item.investment_track) chips.push(`<span class="chip industry">${escapeHtml(humanize(item.investment_track))}</span>`);
  if (item.is_dfi_or_multilateral) chips.push(`<span class="chip role-family">DFI / multilateral</span>`);
  if (item.is_ngo_or_un) chips.push(`<span class="chip role-family">NGO / UN</span>`);
  if (item.ngo_track) chips.push(`<span class="chip industry">${escapeHtml(humanize(item.ngo_track))}</span>`);
  if (item.is_kenya_public_institution) chips.push(`<span class="chip role-family">Kenya public institution</span>`);
  if (item.public_institution_category) chips.push(`<span class="chip industry">${escapeHtml(humanize(item.public_institution_category))}</span>`);
  if (item.is_multinational) chips.push(`<span class="chip role-family">Multinational</span>`);
  if (item.multinational_sector) chips.push(`<span class="chip industry">${escapeHtml(humanize(item.multinational_sector))}</span>`);
  if (item.org_type) chips.push(`<span class="chip">${escapeHtml(humanize(item.org_type))}</span>`);
  if (item.africa_relevance) chips.push(`<span class="chip role-family">${escapeHtml(AFRICA_RELEVANCE_LABELS[item.africa_relevance] || humanize(item.africa_relevance))}</span>`);
  if (item.african_applicant_access) chips.push(`<span class="chip ${item.certified_default_view ? 'eligibility-positive' : 'eligibility-uncertain'}">${escapeHtml(AFRICAN_ACCESS_LABELS[item.african_applicant_access] || humanize(item.african_applicant_access))}</span>`);
  if (item.eligibility) chips.push(`<span class="chip ${eligibilityClass(item.eligibility)}">${escapeHtml(ELIGIBILITY_LABELS[item.eligibility] || humanize(item.eligibility))}</span>`);
  if (item.industry) chips.push(`<span class="chip industry">${escapeHtml(humanize(item.industry))}</span>`);
  if (item.work_mode) chips.push(`<span class="chip">${escapeHtml(REMOTE_LABELS[remoteValue(item)] || humanize(item.work_mode))}</span>`);
  if (item.seniority) chips.push(`<span class="chip">${escapeHtml(EXPERIENCE_LABELS[item.seniority] || humanize(item.seniority))}</span>`);
  if (item.years_min !== null && item.years_min !== undefined) {
    const years = item.years_max ? `${item.years_min}–${item.years_max} yrs` : `${item.years_min}+ yrs`;
    chips.push(`<span class="chip">${escapeHtml(years)}</span>`);
  }

  let detailHtml = '';
  if (expanded) {
    const eligibilityConfidence = item.eligibility_confidence !== null && item.eligibility_confidence !== undefined
      ? `${Math.round(item.eligibility_confidence * 100)}% confidence` : null;
    const details = [
      ['Organisation', item.org],
      ['Organisation type', humanize(item.org_type)],
      ['Role family', humanize(item.role_family)],
      ['Investment classification', INVESTMENT_CLASS_LABELS[item.investment_classification] || humanize(item.investment_classification)],
      ['Investment track', humanize(item.investment_track)],
      ['DFI relevance', DFI_RELEVANCE_LABELS[item.dfi_relevance] || humanize(item.dfi_relevance)],
      ['Institution type', humanize(item.institution_type)],
      ['Phase 7 priority institution', item.phase7_priority_institution ? 'Yes' : null],
      ['NGO / UN classification', NGO_CLASS_LABELS[item.ngo_classification] || humanize(item.ngo_classification)],
      ['NGO / development track', humanize(item.ngo_track)],
      ['Phase 8 priority organisation', item.phase8_priority_organisation ? 'Yes' : null],
      ['Kenya public institution', item.is_kenya_public_institution ? 'Yes' : null],
      ['Public institution category', humanize(item.public_institution_category)],
      ['Multinational employer', item.is_multinational ? 'Yes' : null],
      ['Multinational sector', humanize(item.multinational_sector)],
      ['Phase 11 priority employer', item.phase11_priority_employer ? 'Yes' : null],
      ['Investment confidence', item.investment_confidence !== null && item.investment_confidence !== undefined ? `${Math.round(item.investment_confidence * 100)}%` : null],
      ['City', item.city],
      ['Country', item.country],
      ['Africa relevance', AFRICA_RELEVANCE_LABELS[item.africa_relevance] || humanize(item.africa_relevance)],
      ['African applicant access', AFRICAN_ACCESS_LABELS[item.african_applicant_access] || humanize(item.african_applicant_access)],
      ['Access evidence strength', humanize(item.african_access_evidence_strength)],
      ['Eligible nationalities', (item.african_access_nationalities || []).join(', ') || null],
      ['Eligibility', item.eligibility ? `${ELIGIBILITY_LABELS[item.eligibility] || humanize(item.eligibility)}${eligibilityConfidence ? ` · ${eligibilityConfidence}` : ''}` : null],
      ['Posted', fmtDate(item.posted)],
      ['Deadline', fmtDate(item.deadline) || 'Not specified'],
      ['Education', humanize(item.education)],
      ['Contract', item.contract !== 'unknown' ? humanize(item.contract) : null],
    ].filter(([, value]) => value);
    detailHtml = `
      <div class="card-detail">
        <div class="detail-grid">
          ${details.map(([key, value]) => `<div class="detail-item"><div class="label">${escapeHtml(key)}</div><div class="value">${escapeHtml(value)}</div></div>`).join('')}
        </div>
        ${item.apply_url ? `<a class="apply-link" href="${escapeAttr(item.apply_url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">View &amp; apply &rarr;</a>` : ''}
      </div>`;
  }

  const postedClass = posted && (posted.includes('h ago') || posted === 'Just posted') ? ' recent' : '';
  return `
    <div class="card ${expanded ? 'expanded' : ''}" data-id="${escapeAttr(item.id)}">
      <div class="card-top">
        <div>
          <div class="card-title">${escapeHtml(item.title)}</div>
          <div class="card-org">${escapeHtml(item.org || 'Unknown organisation')} ${item.org_verified ? '<span class="verified-badge">&#10003;</span>' : ''} &middot; ${escapeHtml(displayLocation(item))}${posted ? ` &middot; <span class="posted-time${postedClass}">${escapeHtml(posted)}</span>` : ''}</div>
        </div>
        <span class="confidence-badge ${confClass(item.confidence)}">${escapeHtml(item.confidence || 'unverified')}</span>
      </div>
      <div class="card-meta">${chips.join('')}</div>
      ${item.summary ? `<div class="card-summary">${escapeHtml(item.summary)}</div>` : ''}
      ${detailHtml}
    </div>`;
}

function render() {
  const filtered = getFiltered();
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  state.page = Math.min(state.page, totalPages);
  const start = (state.page - 1) * PAGE_SIZE;
  const pageItems = filtered.slice(start, start + PAGE_SIZE);
  document.getElementById('resultsHeaderCount').innerHTML = `<b>${filtered.length}</b> ${filtered.length === 1 ? 'result' : 'results'}`;

  const list = document.getElementById('cardList');
  list.innerHTML = pageItems.length
    ? pageItems.map(renderCard).join('')
    : '<div class="empty-state"><div class="big">No matches</div>Try a broader search or clear a filter.</div>';

  const pager = document.getElementById('pager');
  if (totalPages > 1) {
    pager.innerHTML = `
      <button id="prevBtn" ${state.page <= 1 ? 'disabled' : ''}>&larr; Prev</button>
      <span>Page ${state.page} of ${totalPages}</span>
      <button id="nextBtn" ${state.page >= totalPages ? 'disabled' : ''}>Next &rarr;</button>`;
    document.getElementById('prevBtn').onclick = () => { state.page -= 1; render(); window.scrollTo({ top: 0, behavior: 'smooth' }); };
    document.getElementById('nextBtn').onclick = () => { state.page += 1; render(); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  } else {
    pager.innerHTML = '';
  }

  list.querySelectorAll('.card').forEach(card => {
    card.addEventListener('click', () => {
      const id = card.dataset.id;
      if (state.expanded.has(id)) state.expanded.delete(id); else state.expanded.add(id);
      render();
    });
  });
}

document.getElementById('keywordInput').addEventListener('input', event => { state.keyword = event.target.value; state.page = 1; render(); });
document.getElementById('locationInput').addEventListener('input', event => { state.location = event.target.value; state.page = 1; render(); });
document.getElementById('searchBtn').addEventListener('click', () => { state.page = 1; render(); });
document.getElementById('keywordInput').addEventListener('keydown', event => { if (event.key === 'Enter') { state.page = 1; render(); } });
document.getElementById('locationInput').addEventListener('keydown', event => { if (event.key === 'Enter') { state.page = 1; render(); } });
document.getElementById('sortSelect').addEventListener('change', event => { state.sortBy = event.target.value; state.page = 1; render(); });
document.getElementById('clearAllBtn').addEventListener('click', () => {
  state = newFilterState(state.sortBy, state.expanded);
  document.getElementById('keywordInput').value = '';
  document.getElementById('locationInput').value = '';
  updatePillLabels();
  render();
});

positionDawnMarker();
renderHeroStats();
renderSourceStrip();
renderFreshnessStatus();
renderFooterMeta();
setupPills();
updatePillLabels();
render();
