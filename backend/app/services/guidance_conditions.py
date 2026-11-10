"""Guidance conditions for one stored profile (FR-49).

Shared by ``app.services.guidance`` and the assistant's profile tool, so both
pick the same guidance items for the same answers. It imports nothing from the
tax engine, which keeps the assistant module free of engine imports.
"""

from __future__ import annotations

from typing import Protocol


class _ProfileAnswers(Protocol):
    spouse_tax_status: str
    has_selected_article_17: bool | None
    has_sole_proprietor_company: bool | None
    is_new_taxpayer_current_year: bool | None


def profile_guidance_conditions(profile: _ProfileAnswers) -> set[str]:
    """Return the guidance conditions a profile's onboarding answers select.

    ``None`` is an unanswered question and selects the matching ``*_unknown``
    condition. It is never read as ``False``. ``cap_warning`` depends on
    transactions, not on the profile, so callers add it themselves.
    """
    conditions = {"always", profile.spouse_tax_status}
    if profile.has_selected_article_17 is True:
        conditions.add("article17")
    elif profile.has_selected_article_17 is None:
        conditions.add("article17_unknown")
    if profile.has_sole_proprietor_company is True:
        conditions.add("company")
    elif profile.has_sole_proprietor_company is None:
        conditions.add("company_unknown")
    if profile.is_new_taxpayer_current_year is None:
        conditions.add("new_taxpayer_unknown")
    return conditions
