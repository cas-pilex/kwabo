"""Repository layer — query helpers."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import defer
from sqlmodel import Session, select

from kwabo.utils import utcnow

from kwabo.db.models import (
    ArtikelEenheid,
    ArtikelKruisverwijzing,
    ArtikelMatchingHistory,
    ArtikelPalletKennis,
    Artikelkaart,
    Klantenkaart,
    KlantEmailAlias,
    KlantenkaartArtikel,
    KlantenkaartShipTo,
    OrderLog,
    Prijsafspraak,
)


def _split_emails(raw: str | None) -> set[str]:
    """NAV stores several addresses in one field, separated by ; , / or
    whitespace (e.g. "purchaseorders@ferney.nl; magazijn@ferney.nl"). Split
    into a normalized set of individual addresses."""
    if not raw:
        return set()
    return {p.strip().lower() for p in re.split(r"[;,/\s]+", raw) if "@" in p}


class KlantRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def by_email(self, email: str) -> Optional[Klantenkaart]:
        if not email:
            return None
        normalized = email.strip().lower()
        # NAV stores emails in mixed case (e.g. EINKAUF-KW@JOKA.DE) but the
        # mail parser lowercases inbound From-headers. Match case-insensitively
        # so a customer like 60645 isn't lost between sync and intake.
        stmt = select(Klantenkaart).where(
            (func.lower(Klantenkaart.email) == normalized)
            | (func.lower(Klantenkaart.email_bestelling) == normalized)
        )
        hit = self.s.exec(stmt).first()
        if hit:
            return hit
        alias = self.s.exec(
            select(KlantEmailAlias).where(
                func.lower(KlantEmailAlias.email) == normalized
            )
        ).first()
        if alias:
            return self.by_nav_nr(alias.klant_nr)
        # Fallback: the address may be one entry in a multi-address field that
        # exact equality missed (Ferney 50262 stores three addresses in one
        # field). Narrow with LIKE, then verify it is a real token. Only accept
        # an UNAMBIGUOUS single customer — a shared address such as
        # confirmation@tabsholland.nl belongs to many customers and must go to
        # manual review instead of an arbitrary pick.
        like = f"%{normalized}%"
        candidates = self.s.exec(
            select(Klantenkaart).where(
                func.lower(Klantenkaart.email).like(like)
                | func.lower(Klantenkaart.email_bestelling).like(like)
            )
        ).all()
        matches = [
            c
            for c in candidates
            if normalized in (_split_emails(c.email) | _split_emails(c.email_bestelling))
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def by_email_domain(self, email: str) -> list[Klantenkaart]:
        """Alle klanten waarvan het email/email_bestelling-veld het DOMEIN van
        `email` bevat (token-geverifieerd). Een agent-/groepsmailbox (TABS:
        supplychain@/confirmation@tabsholland.nl) deelt zo één domein over veel
        vestigingen/merken. De caller herkent 'gedeeld' aan de telling en
        disambigueert dan op het leveradres i.p.v. een lukrake kaart te pakken."""
        if not email or "@" not in email:
            return []
        domain = email.rsplit("@", 1)[1].strip().lower()
        if not domain:
            return []
        like = f"%@{domain}%"
        rows = self.s.exec(
            select(Klantenkaart).where(
                func.lower(Klantenkaart.email).like(like)
                | func.lower(Klantenkaart.email_bestelling).like(like)
            )
        ).all()
        out: list[Klantenkaart] = []
        for c in rows:
            domains = {
                e.rsplit("@", 1)[1]
                for e in (_split_emails(c.email) | _split_emails(c.email_bestelling))
            }
            if domain in domains:
                out.append(c)
        return out

    def by_domain_alias(self, email: str) -> list[Klantenkaart]:
        """Klanten met een domein-alias ("@pontmeyer.nl"-rij in
        klant_email_aliases) dat het domein van `email` dekt. Bewust een
        aparte stap náást by_email: een domein kan bij een franchise
        meerdere vestigingen dekken, dus de caller bepaalt confidence en
        review — nooit de vlagvrije conf 1.0 van een exacte match."""
        if not email or "@" not in email:
            return []
        domain = "@" + email.rsplit("@", 1)[1].strip().lower()
        aliases = self.s.exec(
            select(KlantEmailAlias).where(func.lower(KlantEmailAlias.email) == domain)
        ).all()
        out: list[Klantenkaart] = []
        seen: set[str] = set()
        for a in aliases:
            if a.klant_nr in seen:
                continue
            seen.add(a.klant_nr)
            k = self.by_nav_nr(a.klant_nr)
            if k:
                out.append(k)
        return out

    def list_aliases(self, nav_klantnr: str) -> list[KlantEmailAlias]:
        return list(
            self.s.exec(
                select(KlantEmailAlias).where(KlantEmailAlias.klant_nr == nav_klantnr)
            ).all()
        )

    def add_alias(self, nav_klantnr: str, email: str, label: Optional[str] = None) -> KlantEmailAlias:
        normalized = email.strip().lower()
        existing = self.s.exec(
            select(KlantEmailAlias).where(
                (KlantEmailAlias.klant_nr == nav_klantnr)
                & (KlantEmailAlias.email == normalized)
            )
        ).first()
        if existing:
            if label is not None:
                existing.label = label
                self.s.add(existing)
                self.s.commit()
            return existing
        row = KlantEmailAlias(klant_nr=nav_klantnr, email=normalized, label=label)
        self.s.add(row)
        self.s.commit()
        self.s.refresh(row)
        return row

    def delete_alias(self, alias_id: int) -> bool:
        row = self.s.get(KlantEmailAlias, alias_id)
        if not row:
            return False
        self.s.delete(row)
        self.s.commit()
        return True

    def by_nav_nr(self, nav_klantnr: str) -> Optional[Klantenkaart]:
        return self.s.exec(
            select(Klantenkaart).where(Klantenkaart.nav_klantnr == nav_klantnr)
        ).first()

    def all(self) -> list[Klantenkaart]:
        return list(self.s.exec(select(Klantenkaart)).all())

    def upsert(self, klant: Klantenkaart) -> Klantenkaart:
        existing = self.by_nav_nr(klant.nav_klantnr)
        if existing:
            for field in ("naam", "email", "email_bestelling", "telefoon", "taal"):
                val = getattr(klant, field)
                if val is not None:
                    setattr(existing, field, val)
            existing.updated_at = utcnow()
            self.s.add(existing)
            self.s.commit()
            return existing
        self.s.add(klant)
        self.s.commit()
        self.s.refresh(klant)
        return klant


class ArtikelRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def mapping(self, klant_nr: str, klant_artikelnr: str) -> Optional[KlantenkaartArtikel]:
        return self.s.exec(
            select(KlantenkaartArtikel).where(
                (KlantenkaartArtikel.klant_nr == klant_nr)
                & (KlantenkaartArtikel.klant_artikelnr == klant_artikelnr)
            )
        ).first()

    def mappings_for(self, klant_nr: str) -> list[KlantenkaartArtikel]:
        return list(
            self.s.exec(
                select(KlantenkaartArtikel).where(KlantenkaartArtikel.klant_nr == klant_nr)
            ).all()
        )

    def upsert_mapping(
        self,
        klant_nr: str,
        klant_artikelnr: str,
        kwabo_artikelnr: str,
        omschrijving: str | None = None,
    ) -> KlantenkaartArtikel:
        existing = self.mapping(klant_nr, klant_artikelnr)
        if existing:
            existing.kwabo_artikelnr = kwabo_artikelnr
            if omschrijving:
                existing.omschrijving = omschrijving
            self.s.add(existing)
            self.s.commit()
            return existing
        new = KlantenkaartArtikel(
            klant_nr=klant_nr,
            klant_artikelnr=klant_artikelnr,
            kwabo_artikelnr=kwabo_artikelnr,
            omschrijving=omschrijving,
        )
        self.s.add(new)
        self.s.commit()
        self.s.refresh(new)
        return new

    def delete_mapping(self, klant_nr: str, mapping_id: int) -> bool:
        """Verwijder één mapping op id. Geeft False als hij niet bestaat of
        niet bij deze klant hoort (voorkomt cross-klant delete)."""
        row = self.s.get(KlantenkaartArtikel, mapping_id)
        if not row or row.klant_nr != klant_nr:
            return False
        self.s.delete(row)
        self.s.commit()
        return True

    def best_history(
        self, klant_nr: str, klant_artikelnr: str
    ) -> Optional[ArtikelMatchingHistory]:
        from sqlalchemy import func

        stmt = (
            select(
                ArtikelMatchingHistory.kwabo_artikelnr,
                func.count(ArtikelMatchingHistory.id).label("freq"),
            )
            .where(
                (ArtikelMatchingHistory.klant_nr == klant_nr)
                & (ArtikelMatchingHistory.klant_artikelnr == klant_artikelnr)
            )
            .group_by(ArtikelMatchingHistory.kwabo_artikelnr)
            .order_by(func.count(ArtikelMatchingHistory.id).desc())
            .limit(1)
        )
        row = self.s.exec(stmt).first()
        if not row:
            return None
        kwabo_nr = row[0] if isinstance(row, tuple) else row.kwabo_artikelnr
        return self.s.exec(
            select(ArtikelMatchingHistory).where(
                (ArtikelMatchingHistory.klant_nr == klant_nr)
                & (ArtikelMatchingHistory.klant_artikelnr == klant_artikelnr)
                & (ArtikelMatchingHistory.kwabo_artikelnr == kwabo_nr)
            )
        ).first()

    def add_history(
        self,
        klant_nr: str,
        klant_artikelnr: Optional[str],
        klant_omschrijving: Optional[str],
        kwabo_artikelnr: str,
        match_methode: str,
        was_correctie: bool = False,
    ) -> ArtikelMatchingHistory:
        row = ArtikelMatchingHistory(
            klant_nr=klant_nr,
            klant_artikelnr=klant_artikelnr,
            klant_omschrijving=klant_omschrijving,
            kwabo_artikelnr=kwabo_artikelnr,
            match_methode=match_methode,
            was_correctie=was_correctie,
            order_datum=date.today(),
        )
        self.s.add(row)
        self.s.commit()
        self.s.refresh(row)
        return row


class PrijsRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def current(self, klant_nr: str, kwabo_artikelnr: str) -> Optional[Prijsafspraak]:
        today = date.today()
        stmt = (
            select(Prijsafspraak)
            .where(
                (Prijsafspraak.klant_nr == klant_nr)
                & (Prijsafspraak.kwabo_artikelnr == kwabo_artikelnr)
                & ((Prijsafspraak.geldig_tot.is_(None)) | (Prijsafspraak.geldig_tot >= today))
            )
            .order_by(Prijsafspraak.geldig_tot.desc())
            .limit(1)
        )
        return self.s.exec(stmt).first()

    def best_match(
        self, klant_nr: str, kwabo_artikelnr: str, hoeveelheid: float = 0
    ) -> Optional[Prijsafspraak]:
        """Cascade lookup: most specific price (pallet > mix > topcoat > standaard).

        Pallet/mix alleen als hoeveelheid >= min_hoeveelheid.
        """
        today = date.today()
        stmt = (
            select(Prijsafspraak)
            .where(
                (Prijsafspraak.klant_nr == klant_nr)
                & (Prijsafspraak.kwabo_artikelnr == kwabo_artikelnr)
                & ((Prijsafspraak.geldig_tot.is_(None)) | (Prijsafspraak.geldig_tot >= today))
            )
        )
        all_matches = list(self.s.exec(stmt).all())
        if not all_matches:
            return None
        # Priority: pallet > mix > topcoat > standaard
        type_priority = {"pallet": 0, "mix": 1, "topcoat": 2, "standaard": 3}
        eligible = []
        for pa in all_matches:
            if pa.type in ("pallet", "mix") and pa.min_hoeveelheid:
                if hoeveelheid < pa.min_hoeveelheid:
                    continue
            eligible.append(pa)
        if not eligible:
            # None match the hoeveelheid criteria — fall back to standaard
            standaard = [p for p in all_matches if p.type == "standaard"]
            return standaard[0] if standaard else all_matches[0]
        eligible.sort(key=lambda p: type_priority.get(p.type, 99))
        return eligible[0]


class OrderLogRepo:
    def __init__(self, session: Session) -> None:
        self.s = session

    def create(self, **kwargs: Any) -> OrderLog:
        row = OrderLog(**kwargs)
        self.s.add(row)
        self.s.commit()
        self.s.refresh(row)
        return row

    def get(self, order_id: int) -> Optional[OrderLog]:
        return self.s.get(OrderLog, order_id)

    def by_email(self, email_id: str) -> Optional[OrderLog]:
        return self.s.exec(select(OrderLog).where(OrderLog.email_id == email_id)).first()

    # Heavy JSON columns the dashboard/list summary never reads. Deferring
    # them keeps the list query from pulling (and the driver from
    # transferring) potentially large blobs for every row. `stappen_log` is
    # append-only and grows per order; `correcties` is unused by _to_summary.
    # NB: `order_state` is intentionally NOT deferred — _to_summary still
    # reads needs_review_count / parent_log_id / sub_order_index from it.
    # Eliminating that one needs denormalised columns (a migration) — see plan.
    _LIST_DEFER = (defer(OrderLog.stappen_log), defer(OrderLog.correcties))

    def list_by_status(self, status: str | None = None) -> list[OrderLog]:
        stmt = (
            select(OrderLog)
            .options(*self._LIST_DEFER)
            .order_by(OrderLog.created_at.desc())
        )
        if status:
            stmt = stmt.where(OrderLog.status == status)
        return list(self.s.exec(stmt).all())

    def list_all(self) -> list[OrderLog]:
        stmt = (
            select(OrderLog)
            .options(*self._LIST_DEFER)
            .order_by(OrderLog.created_at.desc())
        )
        return list(self.s.exec(stmt).all())

    def update(self, order_id: int, **fields: Any) -> Optional[OrderLog]:
        row = self.s.get(OrderLog, order_id)
        if not row:
            return None
        for k, v in fields.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, default=str)
            setattr(row, k, v)
        row.updated_at = utcnow()
        self.s.add(row)
        self.s.commit()
        self.s.refresh(row)
        return row


class ArtikelkaartRepo:
    """NAV item card mirror — read-side cache populated by the NAV sync job."""

    def __init__(self, session: Session) -> None:
        self.s = session

    def get(self, artikelnr: str) -> Optional[Artikelkaart]:
        return self.s.get(Artikelkaart, artikelnr)

    def upsert(self, record: Artikelkaart) -> Artikelkaart:
        existing = self.get(record.kwabo_artikelnr)
        if existing:
            # NAV-mirror semantics: unconditional overwrite. If NAV reports
            # False / None, that is the new truth — do NOT preserve prior
            # values the way KlantRepo does for user-edited fields.
            for field in ("naam", "basis_eenheid", "verkoop_eenheid", "mixprijzen", "palletable"):
                setattr(existing, field, getattr(record, field))
            existing.updated_at = utcnow()
            self.s.add(existing)
            self.s.commit()
            self.s.refresh(existing)
            return existing
        self.s.add(record)
        self.s.commit()
        self.s.refresh(record)
        return record

    def list_with_mixprijzen(self) -> list[Artikelkaart]:
        return list(
            self.s.exec(select(Artikelkaart).where(Artikelkaart.mixprijzen.is_(True))).all()
        )

    def list_eenheden(self, artikelnr: str) -> list[ArtikelEenheid]:
        """All Item-Unit-of-Measure rows for an article (from the NAV sync)."""
        return list(
            self.s.exec(
                select(ArtikelEenheid).where(
                    ArtikelEenheid.kwabo_artikelnr == artikelnr
                )
            ).all()
        )

    def valid_uom_codes(self, artikelnr: str) -> set[str]:
        """Upper-cased set of unit codes NAV accepts for this article.

        Empty when the item-UOM table hasn't been synced for this article —
        callers must treat "empty" as "unknown" (fall back to base unit),
        not as "no valid units".
        """
        return {
            e.eenheid_code.strip().upper()
            for e in self.list_eenheden(artikelnr)
            if e.eenheid_code
        }


class ShipToRepo:
    """Mirror of NAV ship-to addresses (table 222)."""

    def __init__(self, session: Session) -> None:
        self.s = session

    def list_for_klant(self, klant_nr: str) -> list[KlantenkaartShipTo]:
        return list(
            self.s.exec(
                select(KlantenkaartShipTo).where(KlantenkaartShipTo.klant_nr == klant_nr)
            ).all()
        )

    def upsert(self, record: KlantenkaartShipTo) -> KlantenkaartShipTo:
        existing = self.s.get(
            KlantenkaartShipTo, (record.klant_nr, record.ship_to_code)
        )
        if existing:
            for field in ("naam", "straat", "postcode", "plaats", "land", "is_default"):
                val = getattr(record, field)
                if val is not None:
                    setattr(existing, field, val)
            self.s.add(existing)
            self.s.commit()
            self.s.refresh(existing)
            return existing
        self.s.add(record)
        self.s.commit()
        self.s.refresh(record)
        return record


class KruisverwijzingRepo:
    """NAV Item Reference (table 5717) — customer artikel-nr -> Kwabo artikel-nr."""

    def __init__(self, session: Session) -> None:
        self.s = session

    def lookup(self, klant_nr: str, klant_artikelnr: str) -> Optional[str]:
        row = self.s.get(ArtikelKruisverwijzing, (klant_nr, klant_artikelnr))
        return row.kwabo_artikelnr if row else None

    def upsert(self, record: ArtikelKruisverwijzing) -> ArtikelKruisverwijzing:
        existing = self.s.get(
            ArtikelKruisverwijzing, (record.klant_nr, record.klant_artikelnr)
        )
        if existing:
            existing.kwabo_artikelnr = record.kwabo_artikelnr
            if record.eenheid_klant is not None:
                existing.eenheid_klant = record.eenheid_klant
            if record.bron:
                existing.bron = record.bron
            self.s.add(existing)
            self.s.commit()
            self.s.refresh(existing)
            return existing
        self.s.add(record)
        self.s.commit()
        self.s.refresh(record)
        return record


class PalletKennisRepo:
    """Self-learning europallet table — used by europallet decision logic."""

    def __init__(self, session: Session) -> None:
        self.s = session

    def lookup(self, kwabo_artikelnr: str, eenheid: str) -> Optional[ArtikelPalletKennis]:
        return self.s.get(ArtikelPalletKennis, (kwabo_artikelnr, eenheid))

    def upsert(self, record: ArtikelPalletKennis) -> ArtikelPalletKennis:
        existing = self.lookup(record.kwabo_artikelnr, record.eenheid)
        if existing:
            existing.pallet_required = record.pallet_required
            existing.per_pallet = record.per_pallet
            existing.confidence = record.confidence
            existing.laatst_bevestigd_op = record.laatst_bevestigd_op or utcnow()
            if record.bevestigd_door is not None:
                existing.bevestigd_door = record.bevestigd_door
            self.s.add(existing)
            self.s.commit()
            self.s.refresh(existing)
            return existing
        if record.laatst_bevestigd_op is None:
            record.laatst_bevestigd_op = utcnow()
        self.s.add(record)
        self.s.commit()
        self.s.refresh(record)
        return record
