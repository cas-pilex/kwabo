"""Seed klantenkaarten + artikelmappings + prijsafspraken uit PDF §2.3."""
from __future__ import annotations

from datetime import date

from sqlmodel import Session

from kwabo.db.models import Klantenkaart, KlantenkaartArtikel, Prijsafspraak
from kwabo.db.session import engine, init_db

# Gebaseerd op de 17 voorbeelden uit de PDF en de email-bestanden.
KLANTEN_SEED = [
    # nav_klantnr, naam, email, email_bestelling, taal
    ("10001", "Ferney Diabolo B.V.", "purchaseorders@ferney.nl", "orders@ferney.nl", "NL"),
    ("10002", "TABS / PontMeyer", "supplychain@tabsholland.nl", None, "NL"),
    ("10003", "Isero Ijzerwaren B.V.", "fransvanvliet@isero.nl", None, "NL"),
    ("10004", "BMN Bouwmaterialen", "jeroen.vanschooten@bmn.nl", None, "NL"),
    ("10005", "Omtzigt Bouw", "kg@omtzigt-bouwmaterialen.nl", None, "NL"),
    ("10006", "Driessen Verf b.v.", "bestellenhelmond@driessenverf.nl", None, "NL"),
    ("10007", "Stukbouw B.V.", "willy@stukbouw.nl", "magazijn@stukbouw.nl", "NL"),
    ("10008", "Enka Bouwmaterialen", "e.sun@enkabouwmarkt.nl", None, "NL"),
    ("10009", "Connect Products GmbH", "patricia@connectproducts.nl", None, "DE"),
    ("10010", "Storch-Ciret GmbH", "s.wilke@storch-ciret.com", None, "DE"),
    ("10011", "Kirchner GmbH", "tobias.leyhausen@kirchner-online.com", None, "DE"),
    ("10012", "Werkzeuge Dietrich GmbH & Co. KG", "malte.klippstein@werkzeuge-dietrich.de", None, "DE"),
    ("10013", "Bugel AG", "r.carvalho@bugel.ch", None, "DE"),
    ("10014", "BAUHAUS", "supplier@bahag.com", None, "NL"),
    ("10015", "Tectis OÜ", "maarjaliisa.nomm@tectis.ee", None, "EN"),
    ("10016", "L. De Vos sa/nv", "anja@lucdevos.be", None, "NL"),
]

# klant_nr, klant_artikelnr, kwabo_artikelnr, omschrijving
ARTIKEL_MAPPING_SEED = [
    ("10001", "23532", "1515155", "Ferney product 23532"),
    ("10002", "K700100007", "228321", "TABS K700100007"),
    ("10003", "24300", "2597768", "Isero product"),
    ("10004", "17040", "201291", "BMN product 17040"),
    ("10004", "19831", "83461", "BMN product 19831"),
    ("10005", "9339895", "DUMMY-OMTZIGT", "Omtzigt product"),
    ("10006", "23559", "DUMMY-DRIESSEN", "Driessen Verf"),
    ("10011", "238534", "DUMMY-KIRCHNER-238534", "Kirchner FÖRCH editie"),
    ("10013", "1672", "DUMMY-BUGEL", "Bugel Zwitserse klant"),
    ("10014", "GLN-122338", "122338", "BAUHAUS via GLN"),
    ("10015", "24462", "47323", "Tectis Proshield"),
    ("10016", "24245", "975097", "L. De Vos Greenboard"),
    ("10012", "24196", "CICS-100-25", "Werkzeuge Dietrich"),
    ("10012", "24197", "CICS-100-25", "Werkzeuge Dietrich variant"),
]

# klant_nr, kwabo_artikelnr, prijs
PRIJS_SEED = [
    ("10001", "1515155", 15.00),
    ("10002", "228321", 12.50),
    ("10003", "2597768", 18.75),
    ("10004", "201291", 8.90),
    ("10004", "83461", 6.40),
    ("10015", "47323", 22.10),
    ("10016", "975097", 14.00),
]


def seed(session: Session) -> None:
    from sqlmodel import select

    for nav, naam, email, email_b, taal in KLANTEN_SEED:
        existing = session.exec(select(Klantenkaart).where(Klantenkaart.nav_klantnr == nav)).first()
        if not existing:
            session.add(
                Klantenkaart(
                    nav_klantnr=nav,
                    naam=naam,
                    email=email,
                    email_bestelling=email_b,
                    taal=taal,
                )
            )
    session.commit()

    for klant_nr, klant_art, kwabo_art, oms in ARTIKEL_MAPPING_SEED:
        exists = session.exec(
            select(KlantenkaartArtikel).where(
                (KlantenkaartArtikel.klant_nr == klant_nr) & (KlantenkaartArtikel.klant_artikelnr == klant_art)
            )
        ).first()
        if not exists:
            session.add(
                KlantenkaartArtikel(
                    klant_nr=klant_nr,
                    klant_artikelnr=klant_art,
                    kwabo_artikelnr=kwabo_art,
                    omschrijving=oms,
                )
            )
    session.commit()

    for klant_nr, kwabo_art, prijs in PRIJS_SEED:
        exists = session.exec(
            select(Prijsafspraak).where(
                (Prijsafspraak.klant_nr == klant_nr) & (Prijsafspraak.kwabo_artikelnr == kwabo_art)
            )
        ).first()
        if not exists:
            session.add(
                Prijsafspraak(
                    klant_nr=klant_nr,
                    kwabo_artikelnr=kwabo_art,
                    prijs=prijs,
                    geldig_van=date(2024, 1, 1),
                    geldig_tot=date(2030, 12, 31),
                )
            )
    session.commit()


def main() -> None:
    init_db()
    with Session(engine) as session:
        seed(session)
    print("DB seeded.")


if __name__ == "__main__":
    main()
