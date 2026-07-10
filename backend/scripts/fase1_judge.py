"""FASE 1 — judge + vastlegging voor de her-diagnose-baseline (pure module).

Herkomst: de functies _norm/regels_view/summarize/judge zijn hier gestart als
LETTERLIJKE kopie van scripts/upgrade_baseline.py (Fase A2, commit 8355402),
zodat backend/tests/test_fase1_judge.py de bewezen judge-gaten eerst ROOD kon
aantonen (TDD). Wijzigingen t.o.v. Fase A worden per gat in de zelftest
gedocumenteerd en hier pas ná een rode test doorgevoerd.

Deze module heeft BEWUST geen imports met bijwerkingen (geen .env, geen
kwabo-imports, geen DB) zodat de testsuite hem veilig kan importeren.
"""
from __future__ import annotations


def _norm(v) -> str:
    return "".join(str(v or "").split()).lower()


def regels_view(out: dict) -> list[dict]:
    return [{
        "pos": r.get("positie"),
        "art_klant": r.get("artikelnummer_klant"),
        "art_matched": r.get("artikelnummer_kwabo_matched") or r.get("artikelnummer_kwabo"),
        "oms": (r.get("omschrijving") or "")[:48],
        "hoeveelheid": r.get("hoeveelheid"),
        "eenheid": r.get("eenheid"),
        "eenheid_origineel": r.get("eenheid_origineel"),
        "eenheid_default": r.get("eenheid_default"),
        "verkoop_uom": r.get("verkoop_uom_gekozen"),
        "verkoop_aantal": r.get("verkoop_aantal"),
        "mix_uom": r.get("mix_uom_gekozen"),
        "mix_aantal": r.get("mix_aantal"),
        "methode": r.get("match_methode"),
        "conf": r.get("match_confidence"),
        "eenheid_bron": r.get("eenheid_bron"),
    } for r in (out.get("orderregels") or [])]


def summarize(out: dict) -> dict:
    km = out.get("klant_match") or {}
    nrf = out.get("needs_review_fields") or []
    afl = out.get("afleveradres") or {}
    ep = out.get("europallet_regel") or None
    ep_meta = ((out.get("_meta") or {}).get("europallet") or {})
    nav_ops = out.get("nav_operations") or []
    regels_zonder_match = [r.get("positie") for r in (out.get("orderregels") or [])
                           if isinstance(r, dict) and not r.get("artikelnummer_kwabo_matched")]
    warnings = out.get("validatie_warnings") or []
    # compose_order.py:80-85 zet per overgeslagen regel een expliciete warning;
    # regelverlies zonder die warning is precies de stille '1???'-klasse.
    regelverlies_gevlagd = all(
        any(f"Regel {pos} " in str(w) for w in warnings) for pos in regels_zonder_match
    ) if regels_zonder_match else True
    if out.get("compose_error"):
        compose_status = "error"
    elif nav_ops:
        compose_status = "ok"
    else:
        compose_status = "leeg"
    return {
        "extract": {
            "klantnaam_besteller": out.get("klantnaam_besteller"),
            "bestelnummer_klant": out.get("bestelnummer_klant"),
            "taal": out.get("taal"),
            "afleveradres": {k: afl.get(k) for k in ("naam", "straat", "postcode", "plaats", "land")}
            if isinstance(afl, dict) else afl,
            # adres_rollen is geen OrderState-channel en wordt door LangGraph
            # na extract gedropt; de rollen overleven in _meta['adressen'].value.
            "adres_rollen": out.get("adres_rollen") or (
                ((out.get("_meta") or {}).get("adressen") or {}).get("value")),
            "verzendwijze": out.get("verzendwijze"),
            "n_regels": len(out.get("orderregels") or []),
        },
        "klant": {"nr": km.get("navision_klantnr"), "naam": km.get("klantnaam"),
                  "bron": km.get("match_bron"), "conf": km.get("match_confidence"),
                  "vlag": "klant_match" in nrf,
                  "kandidaten": [{"nr": k.get("navision_klantnr"), "naam": k.get("klantnaam")}
                                 for k in (out.get("klant_kandidaten") or [])]},
        "ship_to_gekozen": out.get("ship_to_gekozen"),
        "ship_to_kandidaten": [{"code": k.get("ship_to_code"), "pc": k.get("postcode"),
                                "plaats": k.get("plaats")}
                               for k in (out.get("ship_to_kandidaten") or [])],
        "regels": regels_view(out),
        "europallet": {"regel": {k: ep.get(k) for k in ("hoeveelheid", "eenheid", "confidence")}
                       if isinstance(ep, dict) else None,
                       "uitleg": ep_meta.get("uitleg"),
                       "onderbouwing_regels": ep_meta.get("regels"),
                       "onbekend": ep_meta.get("onbekend") or []},
        "compose": {
            "status": compose_status,
            "error": out.get("compose_error"),
            "nav_ops_count": len(nav_ops),
            "ops": [{"op": op.get("op"), "path": op.get("path"),
                     "body_keys": sorted((op.get("body") or {}).keys()),
                     "optional": bool(op.get("optional"))}
                    for op in nav_ops if isinstance(op, dict)],
            "regels_zonder_match": regels_zonder_match,
            "regelverlies_gevlagd": regelverlies_gevlagd,
        },
        "needs_review_fields": nrf,
        "validatie_warnings": warnings,
        "is_order": out.get("is_order"),
    }


def judge(out: dict, gt: dict | None) -> dict:
    """verify_reality.judge + corpus-uitbreidingen europallet_aantal/verzendwijze."""
    if not gt:
        return {"status": "geen_grondwaarheid", "velden": []}
    km = out.get("klant_match") or {}
    nrf = out.get("needs_review_fields") or []
    klant_flagged = "klant_match" in nrf
    afl = out.get("afleveradres") or {}
    velden: list[dict] = []

    def add(naam, juist, gevlagd, verwacht, kreeg):
        if juist:
            velden.append({"veld": naam, "oordeel": "JUIST"})
        elif gevlagd:
            velden.append({"veld": naam, "oordeel": "FOUT-met-vlag", "verwacht": verwacht, "kreeg": kreeg})
        else:
            velden.append({"veld": naam, "oordeel": "STILLE-FOUT", "verwacht": verwacht, "kreeg": kreeg})

    def _has(v):
        return v not in (None, "")

    if _has(gt.get("klant_nr")):
        got = km.get("navision_klantnr")
        add("klant_nr", _norm(got) == _norm(gt["klant_nr"]), klant_flagged, gt["klant_nr"], got)
    if _has(gt.get("afleveradres_postcode")):
        got = (afl.get("postcode") if isinstance(afl, dict) else None)
        # Vlaggen die het afleveradres dekken: ship_to-ambiguïteit
        # (select_ship_to.py:246), extract-rol-twijfel 'afleveradres'
        # (extract.py:148/160/162) en de meta-herleide vorm 'adressen'
        # (preview.py:_all_needs_review_paths). Fase A kende alleen de eerste.
        adres_flag = ("ship_to_gekozen" in nrf or "afleveradres" in nrf
                      or "adressen" in nrf)
        add("afleveradres_postcode", _norm(got) == _norm(gt["afleveradres_postcode"]),
            adres_flag, gt["afleveradres_postcode"], got)
    if _has(gt.get("ship_to_code")):
        got = out.get("ship_to_gekozen")
        st_flag = "ship_to_gekozen" in nrf
        add("ship_to_code", _norm(got) == _norm(gt["ship_to_code"]), st_flag, gt["ship_to_code"], got)
    if _has(gt.get("verzendwijze")):
        got = out.get("verzendwijze")
        add("verzendwijze", _norm(got) == _norm(gt["verzendwijze"]), False, gt["verzendwijze"], got)
    if _has(gt.get("europallet_aantal")):
        ep = out.get("europallet_regel") or {}
        got = ep.get("hoeveelheid") if isinstance(ep, dict) else None
        ep_flag = any("europallet" in f for f in nrf)
        try:
            ok = abs(float(got) - float(gt["europallet_aantal"])) < 1e-6
        except (TypeError, ValueError):
            ok = False
        add("europallet_aantal", ok, ep_flag, gt["europallet_aantal"], got)
    gt_regels = {int(r["pos"]): r for r in (gt.get("regels") or []) if r.get("pos") is not None}
    for r in (out.get("orderregels") or []):
        pos = r.get("positie")
        g = gt_regels.get(int(pos)) if pos is not None else None
        if not g:
            continue
        # Eenheid-vlaggen: verkoop_eenheid:{pos} (apply_mixprijzen:293),
        # mix_uom:{pos} (apply_mixprijzen:366) en het extract-pad
        # orderregels[i].eenheid. Fase A miste mix_uom -> gevlagde mix-fout
        # telde onterecht als STILLE-FOUT (zelftest: test_mix_uom_vlag_...).
        eenheid_flag = (f"verkoop_eenheid:{pos}" in nrf
                        or f"mix_uom:{pos}" in nrf
                        or f"orderregels[{int(pos)-1}].eenheid" in nrf)
        if _has(g.get("eenheid")):
            got = r.get("verkoop_uom_gekozen") or r.get("mix_uom_gekozen") or r.get("eenheid")
            add(f"regel{pos}.eenheid", _norm(got) == _norm(g["eenheid"]), eenheid_flag,
                g["eenheid"], got)
        if _has(g.get("aantal")):
            got = r.get("verkoop_aantal") if r.get("verkoop_aantal") is not None else (
                r.get("mix_aantal") if r.get("mix_aantal") is not None else r.get("hoeveelheid"))
            try:
                ok = abs(float(got) - float(g["aantal"])) < 1e-6
            except (TypeError, ValueError):
                ok = False
            # eenheid+aantal zijn één beslissing (resolve_line_uom): de
            # eenheid-vlag dekt het omgerekende aantal op dezelfde positie.
            aantal_flag = eenheid_flag or f"orderregels[{int(pos)-1}].hoeveelheid" in nrf
            add(f"regel{pos}.aantal", ok, aantal_flag, g["aantal"], got)
        if _has(g.get("artikel")):
            got = r.get("artikelnummer_kwabo_matched")
            flag = (got is None) or (r.get("match_confidence") or 0) < 0.85 or \
                f"orderregels[{int(pos)-1}].artikelnummer_kwabo_matched" in nrf
            add(f"regel{pos}.artikel", _norm(got) == _norm(g["artikel"]), flag, g["artikel"], got)

    stille = [v for v in velden if v["oordeel"] == "STILLE-FOUT"]
    review = [v for v in velden if v["oordeel"] == "FOUT-met-vlag"]
    status = "STILLE-FOUT" if stille else ("review" if review else "JUIST")
    return {"status": status, "velden": velden,
            "n_stille_fouten": len(stille), "n_review": len(review)}
