"""Regressie: een artikelmapping (klant-SKU -> kwabo-artikel) kan via de API
verwijderd worden. Voorheen kon je mappings alleen toevoegen/importeren maar
nooit corrigeren/opruimen vanuit de UI. Delete-by-id, net als aliases.
Ontdekt 01-06-2026.
"""
from __future__ import annotations


def test_artikelmapping_delete(client):
    r = client.post(
        "/api/klanten/10001/artikelen",
        json={"klant_artikelnr": "DEL-K", "kwabo_artikelnr": "DEL-Q"},
    )
    assert r.status_code == 200
    mid = r.json()["id"]

    r = client.delete(f"/api/klanten/10001/artikelen/{mid}")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = client.get("/api/klanten/10001/artikelen")
    assert all(m["id"] != mid for m in r.json())


def test_artikelmapping_delete_not_found(client):
    r = client.delete("/api/klanten/10001/artikelen/999999")
    assert r.status_code == 404


def test_artikelmapping_delete_wrong_klant_is_404(client):
    """Een mapping van klant A mag niet via klant B's pad verwijderd worden."""
    r = client.post(
        "/api/klanten/10001/artikelen",
        json={"klant_artikelnr": "WK-K", "kwabo_artikelnr": "WK-Q"},
    )
    mid = r.json()["id"]

    r = client.delete(f"/api/klanten/10002/artikelen/{mid}")
    assert r.status_code == 404

    # En de mapping bestaat nog onder de juiste klant.
    r = client.get("/api/klanten/10001/artikelen")
    assert any(m["id"] == mid for m in r.json())
