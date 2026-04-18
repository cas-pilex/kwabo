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
    # Ferney (10001) — uit Ferney inkooporder 4200056148.pdf
    ("10001", "23532", "1515155", "Ferney STUCLOPER WIT 1.30m 60m2"),
    ("10001", "24230", "1515158", "Ferney BESCHERMFOL.ZELFKL.TR. 60MX70CM 75MU"),
    ("10001", "23552", "1515178", "Ferney AFDEKVLIES 1.00m 25m2"),
    # TABS / PontMeyer (10002) — uit Bestelling 4506782407 157.pdf
    ("10002", "K700100007", "228321", "TABS stucloper/protectiekarton 950-1050mm rol 50m2"),
    # Isero (10003) — uit INKOOPORDER IO2029003
    ("10003", "24300", "2597768", "Isero Stucloper 65cm 30m2 wit"),
    # BMN (10004) — uit Inkoopopdracht 403602451
    ("10004", "17040", "201291", "BMN KOOFLIJST KW-007 150cm"),
    ("10004", "19831", "83461", "BMN KWABO STATIEGELD KIST"),
    # Omtzigt (10005) — uit Inkooporder 00176482
    ("10005", "9339895", "DUMMY-OMTZIGT-501", "Omtzigt Gipsperklijst KW-501"),
    # Driessen Verf (10006) — uit XO089385
    ("10006", "23559", "DUMMY-DRIESSEN-ETP25", "Driessen ProGold Afdekvlies ETP 25m2"),
    ("10006", "804600", "DUMMY-DRIESSEN-804600", "Driessen interne code 804600"),
    # Stukbouw (10007) — uit Verkoop - Bevestiging Stukbouw.pdf
    ("10007", "17810", "KW-502", "Stukbouw Perklijst 150cm KW-502"),
    ("10007", "17950", "KW-520", "Stukbouw Perklijst 150cm KW-520"),
    ("10007", "20081", "KW-539", "Stukbouw Perklijst 150cm KW-539"),
    ("10007", "20093", "DUMMY-STUKBOUW-TRANS", "Stukbouw Transport/verzendkosten"),
    ("10007", "19832", "DUMMY-STUKBOUW-STAT", "Stukbouw Statiegeld transportkisten"),
    # Enka Bouwmaterialen (10008) — uit Fwd_ Nieuwe order (vrije-tekst bestelling)
    ("10008", "ENK-STU-120", "DUMMY-ENKA-STU120", "Enka stucloper 120cm (vrije tekst)"),
    ("10008", "ENK-HKN-260", "DUMMY-ENKA-HKN260", "Enka hoeknaald 260cm"),
    ("10008", "ENK-HKN-300", "DUMMY-ENKA-HKN300", "Enka hoeknaald 300cm"),
    # Connect Products (10009) — uit PO16260462
    ("10009", "24196", "CICS-100-25", "Connect Products Cover-it Classic Soft 100cm-25m2"),
    ("10009", "24197", "CICS-100-50", "Connect Products Cover-it Classic Soft 100cm-50m2"),
    # Storch-Ciret (10010) — uit Bestellung BD26200984
    ("10010", "49 61 50", "DUMMY-STORCH-496150", "Storch Milchtuetenpapier weiss 50qm PE"),
    ("10010", "496150", "DUMMY-STORCH-496150", "Storch art. 49 61 50 (zonder spaties)"),
    # Kirchner (10011) — uit Bestellung BE60013380 + BE60013417
    ("10011", "238534", "DUMMY-KIRCHNER-238534", "Kirchner OHL25-1P FÖRCH Edition"),
    ("10011", "24497", "DUMMY-KIRCHNER-OHL50-1B", "Kirchner OHL50-1B OHL-BLUE vlies"),
    ("10011", "23909", "DUMMY-KIRCHNER-JV5010", "Kirchner JV5010 Abdeckvlies 50x1m 180g/m2"),
    ("10011", "24209", "DUMMY-KIRCHNER-MP50", "Kirchner MP50-10WW TFC Board 50m2"),
    ("10011", "23992", "DUMMY-KIRCHNER-OHL50-1P", "Kirchner OHL50-1P vlies 160g/m2"),
    # Werkzeuge Dietrich (10012) — uit Bestellung Werkzeuge Dietrich GmbH
    ("10012", "4086-019309", "23733", "WD Abdeckvlies TFC 220g/qm 1x50m"),
    ("10012", "23733", "23733", "WD Abdeckvlies TFC 220g/qm (Ihre Material-Nr.)"),
    # Bugel (10013) — uit Bestellung KWABO Monat April/Mai 26
    ("10013", "1672", "DUMMY-BUGEL-1672", "Bugel Abdeckvlies 160 gr"),
    # BAUHAUS (10014) — uit 2026-03-14_NL_122338 (GLN)
    ("10014", "GLN-122338", "122338", "BAUHAUS via GLN leverancier 122338"),
    ("10014", "31383686", "242191", "BAUHAUS SCHILDERSVLIES 10M2 absorberende toplaag"),
    # Tectis (10015) — uit Purchase Order OT3478
    ("10015", "24462", "47323", "Tectis FLOORCOVER SOFT 1x25m"),
    ("10015", "24463", "47324", "Tectis FLOORCOVER SOFT 1x50m"),
    ("10015", "24461", "47325", "Tectis FLOORCOVER SOFT 0,65x25m"),
    # L. De Vos (10016) — uit Order IOR26/00083
    ("10016", "24245", "975097", "L. De Vos PK Greenboard B1 B/W 75m2 Proshield"),
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
