#!/usr/bin/env python3
"""
postcode_utils.py
=================
Think of a UK postcode like a label on a drawer in a huge filing cabinet.
If you don't label the drawer EXACTLY right (e.g. 'PL01PF' instead of 'PL0 1PF'),
you will never find the right file.

This file is just a helper that makes sure every postcode is written the same way,
so our computer filing cabinet (SQLite database) can find it quickly.
"""

import re
from typing import Optional


def _insert_postcode_space(raw: str) -> str:
    """
    UK postcodes ALWAYS have a space in the same spot.
    It is like knowing that a phone number always needs a country code.
    
    Examples of correct spacing:
      SW1A 1AA (postcode area + space + rest)
      PL0 1PF
      M1 1AA
    
    If someone gives us a postcode with the space in the wrong place or missing,
    this function puts it in the right place so the database recognises it.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw.upper())
    
    # If the cleaned postcode is already in the right format, just put the space back.
    # The rule is: everything before the last 3 characters, then a space, then the last 3.
    if len(cleaned) < 4:
        return cleaned
    
    outward = cleaned[:-3]
    inward = cleaned[-3:]
    return f"{outward} {inward}"


def normalise_postcode(raw_postcode: Optional[str]) -> Optional[str]:
    """
    This is the friendly front desk of our filing cabinet.
    
    It does three things:
    1. Makes sure the 'raw_postcode' isn't blank or 'None'.
    2. Removes any weird dots, tabs, or extra spaces.
    3. Capitalises everything and fixes the space in the middle.
    
    If the postcode doesn't even look like a UK postcode after cleaning,
    we return 'None' (computer way of saying 'not a proper postcode').
    
    Think of it like a spell-checker that only knows how words SHOULD look.
    """
    if not raw_postcode or not isinstance(raw_postcode, str):
        return None
    
    # Remove any hidden garbage (tabs, newlines, extra spaces)
    cleaned = raw_postcode.strip()
    
    # UK postcodes look like this when stripped of spaces: 5 to 7 letters/numbers.
    # We use a simple check first.
    alphanumeric_only = re.sub(r"[^A-Za-z0-9]", "", cleaned).upper()
    if len(alphanumeric_only) < 5:
        return None
    
    # Now fix the spacing using our helper above.
    formatted = _insert_postcode_space(cleaned)
    
    return formatted


def format_address_street_city_postcode(
    street: Optional[str],
    city: Optional[str],
    postcode: Optional[str]
) -> str:
    """
    Sometimes we want to ask the internet (Nominatim) for help when our local filing cabinet
    doesn't have the postcode. The internet likes an address as a single sentence.
    
    This sticks the street, city, and postcode together into a nice readable sentence,
    like: '10 Downing Street, London, SW1A 2AA'
    """
    parts = [p.strip() for p in [street, city, postcode] if p and str(p).strip()]
    return ", ".join(parts)
