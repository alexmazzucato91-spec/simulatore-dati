#!/usr/bin/env python3
"""Postino del Simulatore Bolletta.
Scarica gli indici mensili ufficiali (PUN Index GME per fasce e PSV) da due fonti che li pubblicano,
li confronta e aggiorna il file indici.json letto dal simulatore. Nessun dato inventato:
un mese viene aggiunto solo se e' un consuntivo (mese gia' chiuso) e le fonti concordano.
"""
import datetime, html, json, re, sys, urllib.request

FONTI = {
    "pun": [
        ("A2A (dati GME/ARERA)", "https://www.a2a.it/assistenza/tutela-cliente/indici/indice-pun"),
        ("Must Energia", "https://www.mustenergia.it/indice-pun-dati-e-tariffe-andamento-del-prezzo-luce/"),
    ],
    "psv": [
        ("A2A (PSV day ahead)", "https://www.a2a.it/assistenza/tutela-cliente/indici/indice-psv"),
        ("Must Energia", "https://www.mustenergia.it/indice-psv/"),
    ],
}
MESI = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre"]
TOLLERANZA = 0.01  # 1%: oltre, le fonti non concordano e il mese non viene inserito
FILE = "indici.json"


def scarica(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (postino simulatore bolletta)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def testo(pagina):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", pagina)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t))


def leggi_tabella(t, quanti):
    """Righe tipo 'Settembre 2026 0,207540 0,206350 ...' -> {'2026-09': [valori]}"""
    out = {}
    pat = re.compile(r"\b(" + "|".join(MESI) + r")\s+(20\d\d)((?:\s+\d+,\d+)+)", re.I)
    for m in pat.finditer(t):
        nums = [float(x.replace(",", ".")) for x in m.group(3).split()]
        if len(nums) < quanti:
            continue
        k = f"{m.group(2)}-{MESI.index(m.group(1).lower()) + 1:02d}"
        out.setdefault(k, nums[:quanti])  # la prima occorrenza (tabella) vince
    return out


def plausibile(tipo, v):
    lo, hi = (0.02, 0.8) if tipo == "pun" else (0.1, 3.0)
    return all(lo <= x <= hi for x in v)


def main():
    with open(FILE, encoding="utf-8") as f:
        dati = json.load(f)
    oggi = datetime.date.today()
    mese_corrente = f"{oggi.year}-{oggi.month:02d}"
    log, aggiunti = [], []
    for tipo, quanti in (("pun", 4), ("psv", 1)):
        letture = []
        for nome, url in FONTI[tipo]:
            try:
                tab = leggi_tabella(testo(scarica(url)), quanti)
                tab = {k: v for k, v in tab.items() if k < mese_corrente and plausibile(tipo, v)}
                letture.append((nome, tab))
                log.append(f"{tipo.upper()} {nome}: {len(tab)} mesi letti ({min(tab) if tab else '-'} .. {max(tab) if tab else '-'})")
            except Exception as e:  # una fonte giu' non blocca l'altra
                log.append(f"{tipo.upper()} {nome}: ERRORE {e}")
        if not letture:
            continue
        mesi = sorted(set().union(*[set(t) for _, t in letture]))
        for k in mesi:
            valori = [(n, t[k]) for n, t in letture if k in t]
            base_n, base = valori[0]
            ok = all(all(abs(a - b) <= TOLLERANZA * max(a, b) for a, b in zip(base, v)) for _, v in valori[1:])
            if not ok:
                log.append(f"{tipo.upper()} {k}: le fonti NON concordano {valori} -> non inserito")
                continue
            nuovo = base if tipo == "pun" else base[0]
            vecchio = dati[tipo].get(k)
            if vecchio is None:
                dati[tipo][k] = nuovo
                aggiunti.append(f"{tipo.upper()} {k} = {nuovo} ({' + '.join(n for n, _ in valori)})")
    if aggiunti:
        dati["aggiornato"] = oggi.isoformat()
        dati["postino"] = {"ultimo_controllo": oggi.isoformat(), "aggiunti": aggiunti}
    else:
        dati.setdefault("postino", {})["ultimo_controllo"] = oggi.isoformat()
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=1, sort_keys=True)
    print("\n".join(log))
    print("AGGIUNTI:\n" + ("\n".join(aggiunti) if aggiunti else "nessun mese nuovo"))
    # se tutte le fonti sono giu' il workflow fallisce, cosi' GitHub manda una email
    if not any("mesi letti" in x for x in log):
        sys.exit("Nessuna fonte leggibile: controlla i siti o inserisci il mese a mano nel simulatore.")


if __name__ == "__main__":
    main()
