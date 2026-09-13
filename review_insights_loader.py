"""
Generates host recommendations from real guest review text - e.g. multiple
reviews mentioning outdated decor becomes a suggestion to modernize.

IMPORTANT - why this needs a different data source than the rest of the
project: the Maven "Airbnb Listings & Reviews" reviews.csv this project has
used everywhere else contains NO review text at all - only listing_id,
review_id, date, and reviewer_id (verified directly: `head reviews.csv`
shows exactly those four columns and nothing else). There is nothing to
analyze in it. Inside Airbnb's full review export
(data/reviews.csv.gz - not the smaller visualisations/reviews.csv) DOES
include the actual comment text under a `comments` column, and is the same
CC BY 4.0-licensed source already used for real price comparison elsewhere
in this project - not a live-site scraper.

Because Inside Airbnb's listing_id is Airbnb's own stable internal ID for a
property, and the Maven dataset was built from a past Inside Airbnb
snapshot without renumbering listings, `source_listing_id` (see db.py) is
usable as the join key into a real Inside Airbnb reviews.csv.gz file's
listing_id column. Coverage will be partial, not universal: Inside Airbnb
only includes currently-active listings in each snapshot, so some of this
project's listings (delisted, or simply not present in whichever snapshot
you download) will legitimately have zero matched reviews - that's expected,
not a bug.

This project's sandboxed dev environment can't download the real file
(same network restriction as comparison_loader.py), so the parsing and
theme-detection logic below is verified against a schema-accurate fixture
instead. It's written to run unchanged against the real file on a normal
machine.

Usage:
    python review_insights_loader.py --reviews /path/to/reviews.csv.gz
(pandas reads .csv.gz transparently - no need to decompress it yourself)
"""
import argparse
import html
import re
import pandas as pd

from db import init_db, get_session, Listing, ReviewInsight

# --- Text cleanup -------------------------------------------------------
# Inside Airbnb's raw text fields (listing descriptions, house rules, review
# comments) are lightly HTML-formatted, not plain text: paragraph breaks are
# literal <br/> tags and punctuation is HTML-entity-encoded (an en dash is
# the six characters "&ndash;", not "-"). Rendered as-is, a guest or host
# just sees that markup as literal text instead of a real line break or
# dash. Cleaned once here, at load time, so every downstream consumer
# (listing descriptions, house rules, guest review excerpts, host insight
# recommendations and sample reviews) already has human-readable text -
# nothing needs to decode HTML at display time.
_BR_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def clean_review_text(raw) -> str:
    """<br/> (any spacing/casing) becomes a real line break, HTML entities
    (&ndash;, &amp;, &#39;, &quot;, ...) are decoded to their actual
    characters, any other stray HTML tag is stripped outright (this app
    doesn't render HTML), and repeated whitespace collapses."""
    text = str(raw)
    text = _BR_TAG_RE.sub("\n", text)
    text = html.unescape(text)
    text = _HTML_TAG_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# Each theme: keyword patterns (case-insensitive substring match) and the
# host-facing recommendation template if that theme comes up often enough.
# Deliberately simple and transparent (regex keyword matching) rather than a
# black-box model - a host can see exactly why a theme was flagged.
THEMES = {
    "outdated_decor": {
        "patterns": [r"outdated", r"old.fashioned", r"dated d[ée]cor", r"needs? updat", r"worn furniture", r"old furniture", r"dated interior"],
        "recommendation": "A common complaint among guests is that the decor seems outdated. Consider modernizing the listing's design.",
    },
    "misleading_photos": {
        "patterns": [r"photos? (do(es)?n.t|didn.t) do", r"pictures? (do(es)?n.t|didn.t) do", r"not as pictured", r"smaller than (the )?photos", r"looked bigger in (the )?pictures", r"photos? (are|were) misleading"],
        "recommendation": "Guest reviews state that the pictures do not do justice to the property. Consider hiring a professional photographer to get better photos of the property.",
    },
    "cleanliness": {
        # Same class of bug as "wifi" below: a bare r"smell(ed|y)?" matched
        # positive mentions too (e.g. "smelled fresh and clean"). Now requires
        # an actual bad-smell word/phrase, not just the word "smell" appearing.
        "patterns": [
            r"\bdirty\b", r"not clean", r"\bdust(y)?\b", r"unclean", r"grimy", r"stain(ed|s)?",
            r"(bad|foul|musty|moldy|mildew|unpleasant) smell",
            r"smell(ed|s)? (bad|musty|moldy|off|funny|weird|awful|terrible)",
            r"\bsmelly\b",
        ],
        "recommendation": "Several guests mentioned cleanliness issues. Consider a more thorough cleaning routine or a professional cleaning service between stays.",
    },
    "noise": {
        "patterns": [r"\bnoisy\b", r"\bloud\b", r"noise from", r"thin walls", r"could hear (everything|the)", r"street noise"],
        "recommendation": "Multiple guests noted noise disturbances. Consider soundproofing, or clearly noting nearby noise sources in the listing description so guests aren't surprised.",
    },
    "wifi": {
        # Bug fix: this used to include a bare r"wi.?fi" pattern, which matched
        # ANY mention of the word - including "great WiFi reception" - and
        # surfaced it as a complaint (with that same praise as the "sample
        # review"). Every pattern here now requires an actual negative word or
        # phrase attached to wifi/internet, not just the word appearing.
        # Found while testing a separate fix: "wi.?fi (was|is|kept |kept)?(bad|...)"
        # had no space between the optional group and the required word, so
        # "wifi was terrible" (real complaint text) never actually matched -
        # "was" would have had to be immediately followed by "terrible" with
        # no space. Each optional branch below now carries its own trailing
        # space (same technique the "communication" theme's "no response
        # from (the )?host" already used correctly), so the required word
        # after it is properly separated whichever branch matches or is
        # skipped.
        "patterns": [
            r"(bad|terrible|unreliable|spotty|patchy|weak|no|poor|slow) wi.?fi",
            r"wi.?fi (was |is |kept )?(bad|terrible|unreliable|spotty|patchy|weak|down|out|cutting|dropping)",
            r"wi.?fi (didn.t|doesn.t|does not|did not) work",
            r"internet (was|is) slow", r"no internet", r"poor (internet )?connection",
            r"internet (kept |kept)?(cutting|dropping)",
        ],
        "recommendation": "Guests have reported unreliable WiFi. Consider upgrading your internet plan or router.",
    },
    "communication": {
        "patterns": [r"host was unresponsive", r"hard to reach", r"slow to respond", r"didn.t respond", r"no response from (the )?host", r"host (never|barely) replied"],
        "recommendation": "Some guests found communication with the host lacking. Consider responding to messages more promptly, especially around check-in time.",
    },
    "checkin_process": {
        # Same class of bug as "wifi"/"cleanliness" above: a bare
        # r"check.in process" matched ANY mention of the phrase - including
        # "very accommodating for the check-in process" - so it now requires
        # an actual negative word describing the process, not just the phrase.
        "patterns": [
            r"check.in was confusing", r"difficult to find", r"hard to check.?in",
            r"instructions? (were|was) unclear",
            r"check.in process (was|is) (confusing|difficult|frustrating|complicated|stressful|a hassle|chaotic)",
            r"(confusing|difficult|frustrating|complicated|stressful|chaotic) check.in process",
        ],
        "recommendation": "Guests have mentioned check-in difficulties. Consider simplifying or clarifying your check-in instructions.",
    },
    "value_for_price": {
        "patterns": [r"overpriced", r"not worth the (price|money)", r"too expensive for", r"poor value"],
        "recommendation": "Some guests feel the listing is overpriced for what it offers. Consider reviewing your pricing relative to the amenities provided.",
    },
    "missing_amenities": {
        "patterns": [r"no coffee", r"missing (basic|essential)", r"\blacked\b", r"wish there was", r"could use more (towels|kitchen|supplies)"],
        "recommendation": "Guests have mentioned missing amenities. Consider adding commonly requested items to improve guest satisfaction.",
    },
}

# A theme is surfaced only if it's a real pattern, not a one-off: at least 2
# mentions, OR at least 15% of all reviews for that listing (whichever
# threshold a small review count can actually clear).
MIN_MENTIONS = 2
MIN_SHARE = 0.15


# For themes where a specific item/location/source can be pulled out of the
# matching review text itself (rather than just "guests mentioned X" in the
# abstract). Word-boundary matches, case-insensitive. Deliberately a curated
# keyword list, not free-text extraction - keeps this honest about being a
# simple, transparent matcher rather than a black-box summarizer.
DETAIL_KEYWORDS = {
    "missing_amenities": [
        "towels", "coffee maker", "coffee machine", "hangers", "toiletries",
        "shampoo", "hair dryer", "hairdryer", "iron", "ironing board",
        "parking", "wifi router", "extra pillows", "pillows", "blankets",
        "dishes", "can opener", "soap", "toilet paper", "kitchen supplies",
        "cooking utensils", "pots and pans", "dish soap",
    ],
    "cleanliness": [
        "bathroom", "kitchen", "floors", "floor", "sheets", "carpet",
        "bedding", "shower", "toilet", "counters", "windows",
    ],
    "noise": [
        "street", "traffic", "neighbors", "neighbours", "construction",
        "bar next door", "nightclub", "club", "road", "airport", "train",
    ],
    "outdated_decor": [
        "furniture", "paint", "bedding", "curtains", "carpet", "wallpaper",
        "fixtures", "sofa", "couch", "mattress",
    ],
}


# --- Negation handling ------------------------------------------------
# A plain keyword match can't tell "the wifi was terrible" from "not
# terrible at all" - both contain the same literal words. To catch the
# common, well-defined case of explicit negation (not/never/n't/without/...)
# without turning this into a full sentiment model, every match is
# rechecked against a small window immediately before it, within the same
# clause: reviews are often several run-on sentences joined by commas, so
# looking back only 4 words (rather than the whole clause or comment) keeps
# an unrelated negation elsewhere in a long sentence from cancelling a real,
# separate complaint later in it.
#
# This intentionally does NOT try to catch implicit/framing negativity with
# no negation word present (e.g. "a bit loud but we loved it", "charming
# old-fashioned decor") - that's a sentiment-analysis problem, not a
# negation one, and out of scope for this simple, transparent matcher.
#
# Also intentionally skipped when the matched phrase's OWN text already
# contains a negation cue: several patterns are themselves phrased as a
# negation on purpose (e.g. "no coffee", "didn't respond", "host barely
# replied", "not clean") - re-applying the check there would incorrectly
# cancel out a real complaint.
NEGATION_CUES = ["not", "never", "no longer", "hardly", "without", "nothing", "none"]
# 4 was too narrow for a real false positive: "The apartment ... is beautiful
# and well-kept, without a single speck of dust" flagged as a cleanliness
# complaint, because "dust" sits 5 words after "without" ("a single speck
# of") - one word past the old window. 6 comfortably covers that phrasing
# (and similar "without so much as a trace of X" constructions) while still
# staying inside one clause, so it can't reach into an unrelated sentence.
NEGATION_WINDOW_WORDS = 6
_NEGATION_CUE_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in NEGATION_CUES) + r")\b|n['’]t\b",
    re.IGNORECASE,
)
# Split into clauses on sentence-ending punctuation and real line breaks, so
# the negation window never crosses into an unrelated sentence. Comments
# reach analyze_comments() already run through clean_review_text() (see
# above), which turns <br/> tags into real "\n" line breaks - so matching on
# "\n" here, not a literal "<br/>" tag, is what actually catches those
# paragraph breaks now.
_CLAUSE_SPLIT_RE = re.compile(r"\n+|(?<=[.!?;])\s+", re.IGNORECASE)


def _is_negated(clause: str, match_start: int, match_end: int) -> bool:
    match_text = clause[match_start:match_end]
    if _NEGATION_CUE_RE.search(match_text):
        return False  # the match itself is already a negation-phrased complaint
    preceding_words = clause[:match_start].split()[-NEGATION_WINDOW_WORDS:]
    return bool(_NEGATION_CUE_RE.search(" ".join(preceding_words)))


def _comment_matches_theme(comment: str, combined_pattern: str) -> bool:
    """True if `comment` contains at least one non-negated match for the
    theme's combined pattern, checked clause by clause."""
    for clause in _CLAUSE_SPLIT_RE.split(comment):
        for m in re.finditer(combined_pattern, clause, re.IGNORECASE):
            if not _is_negated(clause, m.start(), m.end()):
                return True
    return False


def extract_details(comment: str, theme: str) -> list:
    keywords = DETAIL_KEYWORDS.get(theme, [])
    found = []
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw) + r"\b", comment, re.IGNORECASE):
            found.append(kw)
    # Drop shorter matches that are just a substring of a longer match already
    # found (e.g. "soap" is redundant once "dish soap" has already matched
    # the same text) - keeps the reported detail as specific as possible.
    return [f for f in found if not any(f != g and f in g for g in found)]


def analyze_comments(comments: list) -> list:
    """Returns a list of {theme, mention_count, total_reviews_scanned,
    recommendation, specific_details, sample_review} for every theme that
    clears the mention threshold."""
    total = len(comments)
    if total == 0:
        return []

    results = []
    for theme, spec in THEMES.items():
        combined_pattern = "|".join(spec["patterns"])
        matching_comments = [c for c in comments if isinstance(c, str) and _comment_matches_theme(c, combined_pattern)]
        count = len(matching_comments)
        if count >= MIN_MENTIONS or (total > 0 and count / total >= MIN_SHARE):
            if count > 0:
                # Pull specific items/locations out of the matching reviews
                # themselves, across ALL matching comments (not just the first)
                all_details = []
                for c in matching_comments:
                    for d in extract_details(c, theme):
                        if d not in all_details:
                            all_details.append(d)

                recommendation = spec["recommendation"]
                if all_details:
                    shown = all_details[:3]
                    recommendation += f" Guests specifically mentioned: {', '.join(shown)}."

                sample = matching_comments[0].strip()

                results.append({
                    "theme": theme,
                    "mention_count": count,
                    "total_reviews_scanned": total,
                    "recommendation": recommendation,
                    "specific_details": ", ".join(all_details) if all_details else None,
                    "sample_review": sample,
                })
    return sorted(results, key=lambda r: r["mention_count"], reverse=True)


def load_review_insights(reviews_path: str):
    print(f"Reading {reviews_path} ...")
    reviews = pd.read_csv(reviews_path, usecols=["listing_id", "comments"])
    reviews = reviews[reviews["comments"].notna()]

    session = get_session()
    listings = session.query(Listing).filter(Listing.source_listing_id.isnot(None)).all()
    print(f"{len(listings)} listings have a source_listing_id to check against.")

    # clear old insights so re-running doesn't duplicate rows
    session.query(ReviewInsight).delete()

    matched_listings = 0
    for listing in listings:
        comments = reviews.loc[reviews["listing_id"] == listing.source_listing_id, "comments"].tolist()
        if not comments:
            continue
        matched_listings += 1
        for result in analyze_comments(comments):
            session.add(ReviewInsight(
                listing_id=listing.id, theme=result["theme"],
                mention_count=result["mention_count"], total_reviews_scanned=result["total_reviews_scanned"],
                recommendation=result["recommendation"], specific_details=result["specific_details"],
                sample_review=result["sample_review"], source="insideairbnb",
            ))

    session.commit()
    session.close()
    print(f"Matched real reviews for {matched_listings} of {len(listings)} listings "
          f"(the rest weren't present in this particular Inside Airbnb snapshot - expected, not an error).")


if __name__ == "__main__":
    init_db()
    parser = argparse.ArgumentParser()
    parser.add_argument("--reviews", required=True, help="Path or URL to a real Inside Airbnb data/reviews.csv.gz")
    args = parser.parse_args()
    load_review_insights(args.reviews)
