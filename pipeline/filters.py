"""Job-level filters applied before snapshot write.

The site is positioned as an EU jobboard. Jobs that are explicitly tied to
a US (or Canadian / Latin-American) location should be dropped, even when
the company is in our seed — keeping them dilutes the EU signal for users
who can't realistically apply (timezone, work auth, no relocation).

The filter is conservative on purpose:
  - DROP only when there's a clear US/NA-only signal in `location` AND no
    EU/global signal in the same string AND the LLM tagger hasn't already
    classified the job as `remote-global` / `remote-eu`.
  - KEEP empty-location jobs (no signal = can't tell, default to inclusion).
  - KEEP jobs whose `remote_policy` says they're remote-global or
    remote-eu — those are reachable regardless of where the company is HQ'd.
"""

from __future__ import annotations

import re

from pipeline.models import Job

# Cities + countries / regions that signal a non-EU-relevant locality.
# Covers: US + Canada + LatAm + Asia + Middle East + Oceania.
# Globally-remote strings ("Remote", "Anywhere in the World", "Worldwide")
# don't match here — they're caught by the EU/global counter-pattern below
# and so always KEPT.
_NON_EU_PAT = re.compile(
    r"\b("
    # Americas
    r"USA|U\.S\.A?\.?|United States|United States of America|US\b|"
    r"North America|Americas|Latin America|LATAM|Canada|Mexico|"
    r"San Francisco|San Jose|Palo Alto|Mountain View|Sunnyvale|Berkeley|"
    r"Oakland|Los Angeles|San Diego|Sacramento|New York|NYC|Brooklyn|"
    r"Manhattan|Boston|Cambridge|Chicago|Seattle|Austin|Denver|Atlanta|"
    r"Miami|Portland|Phoenix|Dallas|Houston|Toronto|Montréal|Montreal|"
    r"Vancouver|Calgary|Ottawa|Pittsburgh|Philadelphia|Washington, D\.C\.|"
    r"Washington DC|Detroit|Minneapolis|St\.?\s*Louis|Tampa|Orlando|"
    r"Nashville|Charlotte|Raleigh|Salt Lake|Las Vegas|Honolulu|Anchorage|"
    r"Quebec|Québec|São Paulo|Buenos Aires|Bogotá|Bogota|Santiago|Lima|"
    r"Mexico City|Guadalajara|"
    # Asia (subcontinent)
    r"India|Bengaluru|Bangalore|Mumbai|Bombay|New Delhi|Delhi|Pune|"
    r"Hyderabad|Chennai|Madras|Gurugram|Gurgaon|Noida|Kolkata|Calcutta|"
    r"Ahmedabad|Jaipur|Lucknow|"
    # East / Southeast Asia
    r"Singapore|Singapur|Tokyo|Tōkyō|Osaka|Yokohama|Kyoto|Nagoya|Sapporo|"
    r"Japan|Beijing|Shanghai|Shenzhen|Guangzhou|Hangzhou|Chengdu|China|"
    r"Hong Kong|Macau|Taipei|Taiwan|Seoul|South Korea|Republic of Korea|"
    r"Bangkok|Thailand|Manila|Cebu|Quezon|Philippines|"
    r"Jakarta|Surabaya|Indonesia|"
    r"Kuala Lumpur|Penang|Malaysia|"
    r"Ho Chi Minh|Hanoi|Vietnam|"
    # Middle East
    r"Dubai|Abu Dhabi|United Arab Emirates|UAE|Sharjah|"
    r"Riyadh|Jeddah|Saudi Arabia|"
    r"Doha|Qatar|Kuwait|Bahrain|Oman|"
    r"Tel Aviv|Jerusalem|Haifa|Israel|"
    # Oceania
    r"Sydney|Melbourne|Brisbane|Perth|Adelaide|Canberra|Australia|"
    r"Auckland|Wellington|New Zealand|"
    # Africa / South Africa
    r"Johannesburg|Cape Town|Pretoria|Durban|South Africa|"
    r"Lagos|Nigeria|Cairo|Egypt|Nairobi|Kenya|Casablanca|Morocco"
    r")\b",
    re.IGNORECASE,
)

# Backwards-compat alias — old code referenced _US_NA_PAT.
_US_NA_PAT = _NON_EU_PAT

# US state postal codes — match when prefixed by ", " to avoid false hits
# on words like "in", "or", "co" that overlap with state abbreviations.
_US_STATE_PAT = re.compile(
    r",\s*("
    r"AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|"
    r"MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|"
    r"VT|VA|WA|WV|WI|WY"
    r")\b",
    re.IGNORECASE,
)

# Anything in this regex overrides the US match — these strings indicate
# the job is reachable from Europe even when the location string also
# names a US city.
_EU_OR_GLOBAL_PAT = re.compile(
    r"\b("
    r"Europe|EU|EMEA|Worldwide|Anywhere|Global|Remote\s*[-—]\s*Worldwide|"
    r"Paris|London|Berlin|Amsterdam|Munich|München|Barcelona|Madrid|Dublin|"
    r"Stockholm|Copenhagen|Helsinki|Oslo|Warsaw|Krak[óo]w|Wroc[łl]aw|"
    r"Prague|Brno|Vienna|Wien|Zurich|Zürich|Geneva|Genève|Brussels|Bruxelles|"
    r"Rome|Roma|Milan|Milano|Lisbon|Lisboa|Tallinn|Riga|Vilnius|"
    r"Athens|Sofia|Budapest|Bratislava|Ljubljana|Zagreb|Bucharest|Bucure[șs]ti|"
    r"Luxembourg|Reykjavik|Reykjavík|Manchester|Edinburgh|Glasgow|Birmingham|"
    r"Hamburg|Frankfurt|Köln|Cologne|Düsseldorf|Stuttgart|Lyon|Marseille|"
    r"Toulouse|Lille|Nice|Bordeaux|Strasbourg|Rotterdam|Utrecht|Eindhoven|"
    r"Antwerp|Antwerpen|Ghent|Gent|Liège|Luxembourg|Porto|Valencia|Sevilla|"
    r"Bilbao|Naples|Napoli|Turin|Torino|Bologna|Florence|Firenze|Tampere|"
    r"Espoo|Aarhus|Bergen|Trondheim|Lund|Malmö|Gothenburg|G[öo]teborg|"
    r"France|Germany|Spain|Italy|Netherlands|Holland|Belgium|Sweden|"
    r"Denmark|Finland|Norway|Ireland|Portugal|Poland|Polska|Czechia|"
    r"Czech Republic|Austria|Österreich|Switzerland|Schweiz|Estonia|Latvia|"
    r"Lithuania|Greece|Hellas|Romania|Bulgaria|Hungary|Magyar|Slovakia|"
    r"Slovenia|Croatia|Luxembourg|Iceland|United Kingdom|England|Scotland|"
    r"Wales|Northern Ireland|UK\b|GB\b|Great Britain"
    r")\b",
    re.IGNORECASE,
)


def is_non_eu_location(location: str | None) -> bool:
    """True when the location string clearly names a non-EU place (US, Asia,
    ME, Oceania, etc) AND has no EU/global counter-signal. Empty / None /
    unknown → False (keep)."""
    if not location or not location.strip():
        return False
    s = location.strip()
    if _EU_OR_GLOBAL_PAT.search(s):
        return False
    return bool(_NON_EU_PAT.search(s) or _US_STATE_PAT.search(s))


# Backwards-compat alias.
is_us_only_location = is_non_eu_location


import re as _re

# Hard non-tech / non-business-services WTF list. These titles are clearly
# off-scope for an EU AI/tech jobboard regardless of which extractor or
# aggregator surfaced them. Hits 1-3% of the corpus on a good day, mostly
# from broad ATS feeds (Greenhouse handles like 'momentic' that turned out
# to be Pilates franchises) or aggregators (chefs at Ritz Paris via WTTJ).
# Conservative — only drops obvious non-knowledge-work roles.
_NON_TECH_TITLE = _re.compile(
    r"\b("
    r"massage(\s*therapist)?|masseur|masseuse|"
    r"spa\s*(therapist|attendant|technician|host)|"
    r"esthetician|nail\s*technician|hair\s*stylist|barber|"
    r"barista|waiter|waitress|sommelier|bartender|"
    r"chef\s*de\s*(cuisine|partie|patisserie|rang)|"
    r"sous\s*chef|line\s*cook|"
    r"nanny|babysitter|childcare\s*(worker|provider)|"
    r"housekeeper|hotel\s*receptionist|valet|concierge|doorman|bellhop|"
    r"yoga\s*instructor|pilates\s*(instructor|teacher)|fitness\s*instructor|"
    r"personal\s*trainer|"
    r"chiropractor|physiotherapist|kinesiologist|"
    r"real\s*estate\s*agent|insurance\s*agent|"
    r"delivery\s*driver|truck\s*driver|forklift\s*(driver|operator)?|"
    r"warehouse\s*(worker|operator|associate)|packer|"
    r"cleaner|janitor|security\s*guard|guard\s*officer"
    r")\b",
    _re.IGNORECASE,
)


def is_non_tech_title(title: str | None) -> bool:
    if not title:
        return False
    return bool(_NON_TECH_TITLE.search(title))


def keep_job(job: Job) -> bool:
    """Return True iff the job should remain in the EU-focused snapshot."""
    # Drop obvious non-tech roles regardless of location/source. Cheap,
    # effective at killing the long tail of WTF jobs (massage therapists,
    # baristas, hotel chefs) that slip in via broad seeds + aggregators.
    if is_non_tech_title(job.title):
        return False
    # If the LLM tagger says the job is remote-global / remote-eu, keep
    # regardless of where the company is HQ'd or what the location string
    # happens to say.
    if job.remote_policy in ("remote-global", "remote-eu"):
        return True
    return not is_non_eu_location(job.location)


def split_jobs(jobs: list[Job]) -> tuple[list[Job], list[Job]]:
    """Return (kept, dropped) for the given list of jobs."""
    kept: list[Job] = []
    dropped: list[Job] = []
    for j in jobs:
        if keep_job(j):
            kept.append(j)
        else:
            dropped.append(j)
    return kept, dropped
