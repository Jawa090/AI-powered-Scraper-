from scrappers.controller import list_scrapers, check_ready, validate_params, get_meta
from scrappers.base import InvalidScrapeParams
from Database.search import SearchCriteria


def get_candidate_scrapers(slots, attempted_scrapers=None, limit=1, current_source=None):
    """
    Find candidate scrapers matching record_kind and geographic coverage,
    verified ready, strictly excluding any scrapers in attempted_scrapers.
    """
    attempted = {s.lower() for s in (attempted_scrapers or []) if s}
    if current_source:
        attempted.add(current_source.lower())
    criteria = SearchCriteria.from_slots(slots)
    target_kind = criteria.record_kind or (getattr(get_meta(current_source), 'record_kind', None) if current_source else None) or 'company'

    candidates = []
    user_kw = (slots or {}).get("user_keyword") or (criteria.category.split(",")[0].strip() if criteria.category else None)
    scraper_kw = user_kw or criteria.category

    for meta in list_scrapers():
        if meta.id.lower() in attempted:
            continue
        ready, _ = check_ready(meta.id)
        if not ready:
            continue
        if meta.record_kind != target_kind:
            continue
        try:
            validate_params(meta.id, {
                'limit': max(1, limit or 1),
                'keyword': scraper_kw,
                'us_state': criteria.us_state,
                'city': criteria.city,
            })
        except InvalidScrapeParams:
            continue
        coverage = meta.coverage or {}
        state = coverage.get('state')
        if state and criteria.us_state and state.casefold() != criteria.us_state.casefold():
            continue
        # Bug 4 fix: exclude state-specific scrapers from nationwide searches
        if state and not criteria.us_state:
            continue
        city = coverage.get('city')
        if city and criteria.city and city.casefold() != criteria.city.casefold():
            continue
        candidates.append({
            'id': meta.id,
            'name': meta.name,
            'description': meta.description,
            'coverage': coverage,
            'recordKind': meta.record_kind,
            'compatible': True,
            'ready': True,
        })
    candidates.sort(key=lambda row: (-int(bool((row.get('coverage') or {}).get('state'))), row['id']))
    return candidates


def timeout_options(slots, failed_source):
    criteria = SearchCriteria.from_slots(slots)
    choices = []
    for meta in list_scrapers():
        ready, _ = check_ready(meta.id)
        compatible = ready and meta.record_kind == criteria.record_kind
        try:
            validate_params(meta.id, {'limit': 1, 'keyword': criteria.category,
                'us_state': criteria.us_state, 'city': criteria.city})
        except InvalidScrapeParams:
            compatible = False
        coverage = meta.coverage or {}
        state = coverage.get('state')
        city = coverage.get('city')
        if state and criteria.us_state and state.casefold() != criteria.us_state.casefold():
            compatible = False
        choices.append({'id': meta.id, 'name': meta.name, 'description': meta.description,
            'coverage': coverage, 'recordKind': meta.record_kind, 'compatible': compatible, 'ready': ready})
    alternatives = [row for row in choices if row['id'] != failed_source and row['compatible']]
    # Prefer a source with specific matching geographic coverage over a broad one.
    alternatives.sort(key=lambda row: (-int(bool(row['coverage'].get('state'))), row['id']))
    return {'retrySource': failed_source, 'scrapers': choices,
        'recommendedSource': alternatives[0]['id'] if alternatives else None}


def timeout_reply(facts):
    options = facts.get('timeoutOptions') or {}
    lines = ['The scraper was stopped after five minutes without returning new records.',
             'The requested requirements were not met.' if not facts.get('requestFulfilled') else 'The requested matching rows are shown.',
             f"{facts.get('matchingRecordsDelivered') or 0} requested matches were delivered; the table contains {facts.get('recordsDelivered') or 0} recovered records saved with deduplication.",
             'Would you like to rerun this scraper or try another compatible scraper?']
    for source in options.get('scrapers', []):
        lines.append(f"{source['name']}: {source['description']}")
    recommended = next((source for source in options.get('scrapers', []) if source['id'] == options.get('recommendedSource')), None)
    lines.append(f"The best compatible alternative is {recommended['name']}, based on its record type and geographic coverage." if recommended else
                 'No other configured scraper covers this record type and location.')
    return '\n\n'.join(lines)
