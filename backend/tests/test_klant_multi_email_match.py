"""Regressie: NAV bewaart vaak meerdere e-mailadressen in één veld, gescheiden
door ';' (bv. Ferney 50262: "purchaseorders@ferney.nl; magazijn@ferney.nl;
jesse.frankenhuizen@ferney.nl"). Exact-equality in KlantRepo.by_email miste die
→ élke multi-adres-klant viel uit op handmatige review i.p.v. auto-match.
Ontdekt 31-05-2026 tijdens de live E2E-verificatie in productie.
"""
from __future__ import annotations

from kwabo.db.models import Klantenkaart
from kwabo.db.repository import KlantRepo, _split_emails


def _add(session, nr: str, naam: str, email: str | None = None,
         email_bestelling: str | None = None) -> None:
    session.add(Klantenkaart(nav_klantnr=nr, naam=naam, email=email,
                             email_bestelling=email_bestelling))
    session.commit()


def test_split_emails():
    assert _split_emails("a@x.nl; b@y.nl; c@z.nl") == {"a@x.nl", "b@y.nl", "c@z.nl"}
    assert _split_emails("A@X.NL , B@Y.NL") == {"a@x.nl", "b@y.nl"}
    assert _split_emails(None) == set()
    assert _split_emails("") == set()
    # geen @-token wordt genegeerd
    assert _split_emails("n.v.t.; geen") == set()


def test_match_address_inside_multi_email_field(session):
    repo = KlantRepo(session)
    # Unieke adressen die niet in de demo-seed voorkomen (bewust geen ferney.nl).
    _add(session, "59001", "Multi Group B.V.",
         email="inkoop@multigroep59001.nl; magazijn@multigroep59001.nl; jan@multigroep59001.nl")
    # Het eerste adres in de lijst matcht.
    hit = repo.by_email("inkoop@multigroep59001.nl")
    assert hit and hit.nav_klantnr == "59001"
    # Een later adres in dezelfde lijst matcht ook.
    hit2 = repo.by_email("jan@multigroep59001.nl")
    assert hit2 and hit2.nav_klantnr == "59001"


def test_match_in_email_bestelling_field(session):
    repo = KlantRepo(session)
    _add(session, "59002", "Multi Besteller B.V.",
         email_bestelling="inkoop@multi.nl;orders@multi.nl")
    hit = repo.by_email("orders@multi.nl")
    assert hit and hit.nav_klantnr == "59002"


def test_shared_address_stays_ambiguous(session):
    """Een gedeeld adres (bv. confirmation@tabsholland.nl bij 98 klanten) mag
    NIET willekeurig één klant kiezen — het hoort naar handmatige review."""
    repo = KlantRepo(session)
    _add(session, "59010", "Filiaal A", email="confirmation@shared.nl; a@filiaala.nl")
    _add(session, "59011", "Filiaal B", email="confirmation@shared.nl; b@filiaalb.nl")
    assert repo.by_email("confirmation@shared.nl") is None
    # Het unieke adres per filiaal matcht wél.
    assert repo.by_email("a@filiaala.nl").nav_klantnr == "59010"


def test_no_substring_false_positive(session):
    """LIKE %adres% mag geen substring-false-positive geven; de split-verificatie
    voorkomt dat xpurchaseorders@... als purchaseorders@... telt."""
    repo = KlantRepo(session)
    _add(session, "59020", "Langer Adres B.V.", email="xinkoop@uniek59020.nl")
    assert repo.by_email("inkoop@uniek59020.nl") is None
