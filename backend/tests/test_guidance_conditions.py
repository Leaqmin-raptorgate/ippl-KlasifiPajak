"""F20-4: guidance and the assistant pick conditions from one function (FR-49)."""

import pytest
from sqlalchemy import select
from test_tax_crud_trace_quota import _auth, _profile

from app.db import SessionLocal
from app.models import Profile as ProfileRow
from app.services import assistant, guidance
from app.services.guidance_conditions import profile_guidance_conditions


@pytest.mark.parametrize(
    ("answer", "expects_unknown"),
    [(True, False), (False, False), (None, True)],
    ids=["new", "not_new", "unanswered"],
)
def test_guidance_and_assistant_select_the_same_conditions(
    client, monkeypatch, answer, expects_unknown
):
    _auth(client)
    created = _profile(client, is_new_taxpayer_current_year=answer)
    assert created.status_code == 200, created.text
    assert created.json()["is_new_taxpayer_current_year"] is answer

    seen: dict[str, list[set[str]]] = {"guidance": [], "assistant": []}

    def _spy(path):
        def _wrapped(profile):
            found = profile_guidance_conditions(profile)
            seen[path].append(set(found))
            return found

        return _wrapped

    monkeypatch.setattr(guidance, "profile_guidance_conditions", _spy("guidance"))
    monkeypatch.setattr(assistant, "profile_guidance_conditions", _spy("assistant"))

    response = client.get("/api/v1/guidance")
    assert response.status_code == 200, response.text
    via_guidance = {item["id"] for item in response.json()["items"]}

    db = SessionLocal()
    try:
        rows = db.scalars(select(ProfileRow)).all()
        assert len(rows) == 1
        via_assistant = {item["id"] for item in assistant._guidance_for(list(rows))}
    finally:
        db.close()

    assert len(seen["guidance"]) == 1
    assert len(seen["assistant"]) == 1
    assert seen["guidance"][0] == seen["assistant"][0]
    assert ("new_taxpayer_unknown" in seen["guidance"][0]) is expects_unknown
    # No transactions, so the guidance path adds no cap_warning on top.
    assert via_guidance == via_assistant
    assert ("new_taxpayer_unknown" in via_assistant) is expects_unknown
