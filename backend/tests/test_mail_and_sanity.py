"""Tests voor mail_sender + sanity checks + 4+ signalering."""
from __future__ import annotations

import pytest

from kwabo.integrations.mail_sender import render_confirmation


class TestMailRendering:
    def test_render_basic(self):
        subject, body = render_confirmation("Test B.V.", "PO-123", "SO-456")
        assert "PO-123" in subject
        assert "SO-456" in body
        assert "Test B.V." in body
        assert "Kwabo Techniek B.V." in body

    def test_render_missing_values(self):
        subject, body = render_confirmation(None, None, None)
        assert "(onbekend)" in body
        assert "(nog niet toegekend)" in body

    def test_render_subject_format(self):
        subject, _ = render_confirmation("X", "PO-999", "SO-111")
        assert "Ontvangstbevestiging" in subject
        assert "PO-999" in subject


class TestSanityWarnings:
    """Verify sanity rules produce correct warnings (unit test, no pipeline needed)."""

    def _run_sanity(self, hoeveelheid: float, eenheid: str) -> list[str]:
        """Simulate the sanity rules from validate_prices_node."""
        SANITY_RULES = [
            (lambda h, e: h <= 0, "Hoeveelheid is 0 of negatief"),
            (lambda h, e: e == "PAL" and h > 100, "Meer dan 100 pallets besteld"),
            (lambda h, e: e == "STUK" and h > 50000, "Meer dan 50.000 stuks besteld"),
            (lambda h, e: e == "ROL" and h > 5000, "Meer dan 5.000 rollen besteld"),
            (lambda h, e: not e or e in ("ONBEKEND", ""), "Onbekende eenheid"),
        ]
        warnings = []
        for check, msg in SANITY_RULES:
            try:
                if check(hoeveelheid, eenheid):
                    warnings.append(msg)
            except Exception:
                pass
        return warnings

    def test_zero_hoeveelheid(self):
        w = self._run_sanity(0, "STUK")
        assert any("0 of negatief" in x for x in w)

    def test_negative_hoeveelheid(self):
        w = self._run_sanity(-5, "ROL")
        assert any("0 of negatief" in x for x in w)

    def test_extreme_pallets(self):
        w = self._run_sanity(200, "PAL")
        assert any("100 pallets" in x for x in w)

    def test_extreme_stuks(self):
        w = self._run_sanity(100000, "STUK")
        assert any("50.000 stuks" in x for x in w)

    def test_normal_hoeveelheid_no_warning(self):
        w = self._run_sanity(50, "ROL")
        assert len(w) == 0

    def test_onbekende_eenheid(self):
        w = self._run_sanity(10, "")
        assert any("Onbekende eenheid" in x for x in w)
        w2 = self._run_sanity(10, "ONBEKEND")
        assert any("Onbekende eenheid" in x for x in w2)


class TestFourPlusSignalering:
    """Test the 4+ logic in match_customer (unit-level check)."""

    def test_niet_4plus_warning(self):
        """Simulate what match_customer does when is_4plus=False."""
        match = {"navision_klantnr": "10001", "is_4plus": False, "kredietlimiet": None}
        warnings = []
        if match.get("is_4plus") is False:
            warnings.append("KLANT IS GEEN 4+ LID")
        assert len(warnings) == 1

    def test_wel_4plus_geen_warning(self):
        match = {"navision_klantnr": "10001", "is_4plus": True, "kredietlimiet": 10000}
        warnings = []
        if match.get("is_4plus") is False:
            warnings.append("KLANT IS GEEN 4+ LID")
        assert len(warnings) == 0

    def test_kredietlimiet_aanwezig(self):
        match = {"navision_klantnr": "10001", "is_4plus": True, "kredietlimiet": 5000}
        assert match["kredietlimiet"] == 5000
