"""FUN MESSAGE BANK — har game ke 50+ message templates, har bar alag aayega.
random.choice se pick hota hai, aur last used ka dhyan rakhta hai taaki
repeat na ho (bar-bar same message nahi aayega)."""

import random

# Har game ke liye last-message track karta hai (repeat avoid)
_last_used: dict = {}


def pick(game: str, templates: list) -> str:
    """Random template pick karo, par last-used wala nahi (variation guarantee).
    Agar 3+ templates hain toh last 3 bhi avoid karo."""
    if not templates:
        return ""
    recent = _last_used.setdefault(game, [])
    # Jo recently use nahi hue, unme se choose karo
    pool = [t for t in templates if t not in recent]
    if not pool:  # sab use ho chuke — reset
        recent.clear()
        pool = templates
    choice = random.choice(pool)
    recent.append(choice)
    if len(recent) > min(3, len(templates) - 1):
        recent.pop(0)
    return choice
