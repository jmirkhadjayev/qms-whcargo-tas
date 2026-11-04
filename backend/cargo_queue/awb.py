import re

_AWB_RE = re.compile(r"^(\d{3})-?(\d{8})$")


def normalize_awb(raw: str | None) -> str | None:
    """Return the AWB as NNN-NNNNNNNN, or None if the format is invalid (decision K21)."""
    if not raw:
        return None
    match = _AWB_RE.match(raw.strip().replace(" ", ""))
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}"
