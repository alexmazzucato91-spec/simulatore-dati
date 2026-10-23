#!/usr/bin/env python3
"""Postino del Simulatore Bolletta.
Scarica gli indici mensili ufficiali (PUN Index GME per fasce e PSV) da due fonti che li pubblicano,
li confronta e aggiorna il file indici.json letto dal simulatore. Nessun dato inventato:
un mese viene aggiunto solo se e' un consuntivo (mese gia' chiuso) e DUE fonti lo riportano con valori uguali (scarto < 1%).
"""
import datetime, html, io, json, re, sys, urllib.request, zipfile

FONTI = {
    "pun": [
        ("GME (prezzi orari ufficiali)", "GME"),
        ("A2A (dati GME/ARERA)", "https://www.a2a.it/assistenza/tutela-cliente/indici/indice-pun"),
        ("Must Energia", "https://www.mustenergia.it/indice-pun-dati-e-tariffe-andamento-del-prezzo-luce/"),
    ],
    "psv": [
        ("ARERA (CMEM, PSV day ahead)", "https://www.arera.it/area-operatori/prezzi-e-tariffe/valore-cmemm-vulnerabili"),
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


def ultimo_noto(dati, tipo):
    return max(dati[tipo]) if dati[tipo] else "0000-00"


def leggi_arera_cmem(t):
    """Tabella ARERA: 'settembre 78,8021 21,889472 0,843182' (€/MWh, €/GJ, €/Smc), divisa per anni con righe '2025', '2024'.
    Le righe prima della prima intestazione d'anno sono dell'anno piu' recente (intestazione successiva + 1)."""
    out, anno, sospese = {}, None, []
    pat = re.compile(r"\b(20\d\d)\b(?=[^0-9]{0,80}?\b(?:" + "|".join(MESI) + r")\b)|\b(" + "|".join(MESI) + r")\s+(\d+,\d+)\s+(\d+,\d+)\s+(\d+,\d+)", re.I)
    for m in pat.finditer(t):
        if m.group(1):
            if anno is None and sospese:
                for mese, v in sospese:
                    out.setdefault(f"{int(m.group(1)) + 1}-{mese:02d}", [v])
                sospese = []
            anno = m.group(1)
            continue
        mese, v = MESI.index(m.group(2).lower()) + 1, float(m.group(5).replace(",", "."))
        if anno:
            out.setdefault(f"{anno}-{mese:02d}", [v])
        else:
            sospese.append((mese, v))
    return out


GME_URL = ("https://www.mercatoelettrico.org/it-it/Home/Esiti/Elettricita/MGP/Statistiche/DatiStorici/moduleId/10874/"
           "controller/GmeDatiStoriciItem/action/DownloadFile?fileName=Anno{anno}.zip")


def pasqua(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e, f = b // 4, b % 4, (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    return datetime.date(y, (h + l - 7 * m + 114) // 31, (h + l - 7 * m + 114) % 31 + 1)


def festivi(y):
    p = pasqua(y)
    return {datetime.date(y, 1, 1), datetime.date(y, 1, 6), p + datetime.timedelta(1), datetime.date(y, 4, 25),
            datetime.date(y, 5, 1), datetime.date(y, 6, 2), datetime.date(y, 8, 15), datetime.date(y, 11, 1),
            datetime.date(y, 12, 8), datetime.date(y, 12, 25), datetime.date(y, 12, 26)}


def fascia(d, ora):
    """Fasce ARERA: F1 lun-ven 8-19; F2 lun-ven 7-8 e 19-23, sab 7-23; F3 il resto, domeniche e festivi."""
    h = ora - 1  # nel file GME l'ora 1 e' 00:00-01:00
    if d.weekday() == 6 or d in festivi(d.year):
        return 3
    if d.weekday() == 5:
        return 2 if 7 <= h < 23 else 3
    if 8 <= h < 19:
        return 1
    return 2 if h == 7 or 19 <= h < 23 else 3


def leggi_gme(anni):
    """Scarica l'archivio annuale GME (prezzi orari) e calcola PUN Index medio mensile: monorario, F1, F2, F3 (€/kWh)."""
    import openpyxl
    out = {}
    for anno in anni:
        req = urllib.request.Request(GME_URL.format(anno=anno), headers={"User-Agent": "Mozilla/5.0 (postino simulatore bolletta)"})
        with urllib.request.urlopen(req, timeout=180) as r:
            z = zipfile.ZipFile(io.BytesIO(r.read()))
        nome = next(n for n in z.namelist() if n.endswith("_60.xlsx"))
        ws = openpyxl.load_workbook(io.BytesIO(z.read(nome)), read_only=True, data_only=True)["Prezzi-Prices"]
        intest = [str(x or "") for x in next(ws.iter_rows(max_row=1, values_only=True))]
        col = next(i for i, x in enumerate(intest) if "PUN" in x.upper())
        som = {}
        for r in ws.iter_rows(min_row=2, values_only=True):
            if not r[0] or r[col] is None:
                continue
            d = datetime.datetime.strptime(str(int(r[0])), "%Y%m%d").date()
            a = som.setdefault(d.strftime("%Y-%m"), [0.0] * 8)
            f, v = fascia(d, int(r[1])), float(r[col])
            a[0] += v; a[1] += 1; a[2 * f] += v; a[2 * f + 1] += 1
        for k, a in som.items():
            if all(a[i] for i in (1, 3, 5, 7)):
                out[k] = [round(a[0] / a[1] / 1000, 6)] + [round(a[2 * f] / a[2 * f + 1] / 1000, 6) for f in (1, 2, 3)]
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
                if url == "GME":
                    tab = leggi_gme(sorted({mese_corrente[:4], str(int(mese_corrente[:4]) - 1) if mese_corrente[5:] == "01" else mese_corrente[:4]}))
                else:
                    t = testo(scarica(url))
                    tab = leggi_arera_cmem(t) if "arera.it" in url else leggi_tabella(t, quanti)
                tab = {k: v for k, v in tab.items() if k < mese_corrente and plausibile(tipo, v)}
                letture.append((nome, tab))
                log.append(f"{tipo.upper()} {nome}: {len(tab)} mesi letti ({min(tab) if tab else '-'} .. {max(tab) if tab else '-'})")
            except Exception as e:  # una fonte giu' non blocca l'altra
                log.append(f"{tipo.upper()} {nome}: ERRORE {e}")
        if not letture:
            continue
        mesi = sorted(set().union(*[set(t) for _, t in letture]))
        for k in mesi:
            if k in dati[tipo]:  # mese gia' presente: non si riscrive e non si segnala
                continue
            valori = [(n, t[k]) for n, t in letture if k in t]
            # se le fonti sono 3 basta che 2 concordino: si tiene la coppia che concorda, con la fonte ufficiale per prima
            if len(valori) == 3:
                vic = lambda a, b: all(abs(x - y) <= TOLLERANZA * max(x, y) for x, y in zip(a, b))
                coppie = [(i, j) for i in range(3) for j in range(i + 1, 3) if vic(valori[i][1], valori[j][1])]
                if coppie:
                    i, j = coppie[0]
                    scarto = [valori[x][0] for x in range(3) if x not in (i, j)]
                    if len(coppie) < 3:
                        log.append(f"{tipo.upper()} {k}: {scarto[0]} si discosta, uso {valori[i][0]} + {valori[j][0]}")
                    valori = [valori[i], valori[j]]
            if len(valori) < 2:  # serve la conferma di due fonti indipendenti
                if k not in dati[tipo] and k >= ultimo_noto(dati, tipo):
                    log.append(f"{tipo.upper()} {k}: c'e' solo su {valori[0][0]}, in attesa di conferma -> non inserito")
                continue
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
