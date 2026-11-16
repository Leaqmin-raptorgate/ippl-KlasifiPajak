"""FR-11: the demo's manual sale is classified as business turnover."""

from test_tax_crud_trace_quota import _auth, _profile, _tx


def test_demo_manual_sale(client):
    _auth(client)
    assert _profile(client).status_code == 200
    response = _tx(client, amount_idr=1_000_000, invoice_no="INV-DEMO-MANUAL")
    assert response.status_code == 201, response.text
    assert response.json()["amount_idr"] == 1_000_000
    assert response.json()["category"] == "usaha"
    assert response.json()["classification"]["requires_clarification"] is False
