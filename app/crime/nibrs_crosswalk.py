from __future__ import annotations

# NIBRS offense description -> (offense_category, nibrs_group), keyed on the lowercase
# (casefold) SPD nibrs_description text. Group A "crime against" assignments follow the FBI
# NIBRS classification (authoritative). Group B are arrest-only offenses with no formal NIBRS
# "crime against" category, so their assignments are BEST-EFFORT (see inline notes); the
# stakes are low because an unrecognized description simply stays uncategorized.
NIBRS_CROSSWALK: dict[str, tuple[str, str]] = {
    # --- Group A · Crime Against PERSON ---
    "murder & nonnegligent manslaughter": ("PERSON", "A"),
    "negligent manslaughter": ("PERSON", "A"),
    "justifiable homicide": ("PERSON", "A"),
    "kidnapping/abduction": ("PERSON", "A"),
    "rape": ("PERSON", "A"),
    "sodomy": ("PERSON", "A"),
    "sexual assault with an object": ("PERSON", "A"),
    "fondling": ("PERSON", "A"),
    "incest": ("PERSON", "A"),
    "statutory rape": ("PERSON", "A"),
    "aggravated assault": ("PERSON", "A"),
    "simple assault": ("PERSON", "A"),
    "intimidation": ("PERSON", "A"),
    "human trafficking, commercial sex acts": ("PERSON", "A"),
    "human trafficking, involuntary servitude": ("PERSON", "A"),
    # --- Group A · Crime Against PROPERTY ---
    "arson": ("PROPERTY", "A"),
    "bribery": ("PROPERTY", "A"),
    "burglary/breaking & entering": ("PROPERTY", "A"),
    "counterfeiting/forgery": ("PROPERTY", "A"),
    "destruction/damage/vandalism": ("PROPERTY", "A"),
    "destruction/damage/vandalism of property": ("PROPERTY", "A"),
    "embezzlement": ("PROPERTY", "A"),
    "extortion/blackmail": ("PROPERTY", "A"),
    "false pretenses/swindle/confidence game": ("PROPERTY", "A"),
    "credit card/automated teller machine fraud": ("PROPERTY", "A"),
    "impersonation": ("PROPERTY", "A"),
    "welfare fraud": ("PROPERTY", "A"),
    "wire fraud": ("PROPERTY", "A"),
    "identity theft": ("PROPERTY", "A"),
    "hacking/computer invasion": ("PROPERTY", "A"),
    "money laundering": ("PROPERTY", "A"),  # best-effort: financial → property
    "robbery": ("PROPERTY", "A"),
    "pocket-picking": ("PROPERTY", "A"),
    "purse-snatching": ("PROPERTY", "A"),
    "shoplifting": ("PROPERTY", "A"),
    "theft from building": ("PROPERTY", "A"),
    "theft from coin-operated machine or device": ("PROPERTY", "A"),
    "theft from motor vehicle": ("PROPERTY", "A"),
    "theft of motor vehicle parts or accessories": ("PROPERTY", "A"),
    "all other larceny": ("PROPERTY", "A"),
    "motor vehicle theft": ("PROPERTY", "A"),
    "stolen property offenses": ("PROPERTY", "A"),
    # --- Group A · Crime Against SOCIETY ---
    "drug/narcotic violations": ("SOCIETY", "A"),
    "drug equipment violations": ("SOCIETY", "A"),
    "betting/wagering": ("SOCIETY", "A"),
    "operating/promoting/assisting gambling": ("SOCIETY", "A"),
    "gambling equipment violations": ("SOCIETY", "A"),
    "sports tampering": ("SOCIETY", "A"),
    "pornography/obscene material": ("SOCIETY", "A"),
    "prostitution": ("SOCIETY", "A"),
    "assisting or promoting prostitution": ("SOCIETY", "A"),
    "purchasing prostitution": ("SOCIETY", "A"),
    "weapon law violations": ("SOCIETY", "A"),
    "animal cruelty": ("SOCIETY", "A"),
    # --- Group B (arrest-only) · best-effort ---
    "bad checks": ("PROPERTY", "B"),  # best-effort: financial instrument → property
    "curfew/loitering/vagrancy violations": ("SOCIETY", "B"),
    "disorderly conduct": ("SOCIETY", "B"),
    "driving under the influence": ("SOCIETY", "B"),
    "drunkenness": ("SOCIETY", "B"),
    "family offenses, nonviolent": ("PERSON", "B"),  # best-effort: against family members
    "liquor law violations": ("SOCIETY", "B"),
    "peeping tom": ("PERSON", "B"),  # best-effort: privacy of a person
    "trespass of real property": ("PROPERTY", "B"),  # best-effort: against real property
    "all other offenses": ("SOCIETY", "B"),
}


def classify_nibrs(description: str | None) -> tuple[str | None, str | None]:
    """Map a NIBRS offense description to (offense_category, nibrs_group). Returns (None, None)
    for a missing/blank/unrecognized description — the arrest still ingests, uncategorized."""
    if not description:
        return (None, None)
    return NIBRS_CROSSWALK.get(description.strip().casefold(), (None, None))
