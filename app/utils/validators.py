"""
Validators
Reusable validation helpers.
"""

import re
from typing import Optional


def is_valid_image_id_format(image_id: str) -> bool:
    """Check that image_id loosely matches X.Y.Z numeric format."""
    return bool(re.fullmatch(r"\d+\.\d+\.\d+", image_id.strip()))


def extract_version_from_branch(branch: str) -> Optional[str]:
    """
    Extract version string from branch name.
    'V5.0' → '5.0'
    'V6.0' → '6.0'
    'main'  → None
    """
    match = re.fullmatch(r"[Vv](\d+\.\d+)", branch.strip())
    return match.group(1) if match else None


def build_image_id(branch: str, pr_number: int) -> Optional[str]:
    """
    Build a properly formatted image ID from branch + PR number.
    'V5.0', 123  → '5.0.123'
    'V6.0', 89   → '6.0.89'
    """
    version = extract_version_from_branch(branch)
    if version is None:
        return None
    return f"{version}.{pr_number}"


def sanitize_string(value: str) -> str:
    """Strip whitespace and remove potentially dangerous chars."""
    return re.sub(r"[^\w.\-]", "", value.strip())
