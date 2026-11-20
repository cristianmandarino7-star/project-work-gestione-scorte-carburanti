"""Scarica l'archivio MIMIT dei prezzi carburanti e produce la media mensile per regione.

Fonte: https://www.mimit.gov.it/it/open-data/elenco-dataset/carburanti-archivio-prezzi
Ogni trimestre ha due archivi .tar.gz con un CSV per giorno:
  - prezzo_alle_8           : idImpianto, descCarburante, prezzo, isSelf, dtComu
  - anagrafica_impianti_attivi: idImpianto, Gestore, Bandiera, Tipo Impianto, Nome, Indirizzo, Comune, Provincia, Lat, Lon

Elaborazione:
  1. per ogni trimestre si legge l'anagrafica dell'ultimo giorno disponibile (idImpianto -> Provincia -> Regione);
  2. si leggono i prezzi giornalieri, si tengono Benzina e Gasolio in self service e il GPL;
  3. si scartano i prezzi anomali (fuori dall'intervallo 0,40 - 3,50 EUR/l);
  4. si calcola la media mensile per regione e carburante su tutte le osservazioni impianto-giorno;
  5. si calcola anche la media GIORNALIERA per marchio (Q8, IP, Eni, ...), regione e carburante.

Output (usati automaticamente dalla dashboard):
  - data/prezzi_regionali_mensili_mimit.csv
  - data/prezzi_marchi_giornalieri_mimit.csv

Gli archivi scaricati restano in data/raw_mimit: una seconda esecuzione non riscarica nulla.

Uso:
  python scripts/scarica_mimit.py                     # 2025 T1 -> 2026 T3, tutti i giorni
  python scripts/scarica_mimit.py --ogni 7            # un giorno ogni 7 (piu' veloce)
  python scripts/scarica_mimit.py --elimina-archivi    # libera spazio a fine elaborazione
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import tarfile
import urllib.request
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import DATA_DIR, PROVINCIA_REGIONE, normalizza_bandiera  # noqa: E402

BASE = "https://opendatacarburanti.mise.gov.it/categorized"
RAW = DATA_DIR / "raw_mimit"
CARBURANTI = {"benzina": "Benzina", "gasolio": "Gasolio", "gpl": "GPL"}
RE_DATA = re.compile(r"(20\d{2})[-_/]?([01]\d)[-_/]?([0-3]\d)")


def trimestri(da: str, a: str):
    y, q = map(int, da.split("-"))
    y2, q2 = map(int, a.split("-"))
    while (y, q) <= (y2, q2):
        yield y, q
        y, q = (y, q + 1) if q < 4 else (y + 1, 1)


def scarica(tipo: str, anno: int, trim: int) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    dest = RAW / f"{tipo}_{anno}_{trim}.tar.gz"
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    url = f"{BASE}/{tipo}/{anno}/{anno}_{trim}_tr.tar.gz"
    print(f"  scarico {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (project work)"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    return dest


def leggi_csv(raw: bytes) -> pd.DataFrame:
    testo = raw.decode("utf-8", errors="replace")
    righe = testo.splitlines()
    if righe and righe[0].lower().startswith("estrazione"):   # prima riga descrittiva nei file MIMIT
        testo = "\n".join(righe[1:])
    sep = "|" if testo[:500].count("|") > testo[:500].count(";") else ";"
    return pd.read_csv(io.StringIO(testo), sep=sep, dtype=str, on_bad_lines="skip", engine="python")


def membri_csv(archivio: Path):
    with tarfile.open(archivio, "r:gz") as tar:
        for m in tar:
            if m.isfile() and m.name.lower().endswith(".csv"):
                yield m.name, tar.extractfile(m).read()


def colonna(df: pd.DataFrame, *candidati: str) -> str:
    norm = {c.lower().replace(" ", "").replace("_", ""): c for c in df.columns}
    for c in candidati:
        if c in norm:
            return norm[c]
    raise KeyError(f"colonna {candidati} non trovata in {list(df.columns)}")


def mappa_impianti(archivio: Path) -> dict[str, tuple[str, str]]:
    """idImpianto -> (regione, marchio), dall'ultimo file di anagrafica del trimestre."""
    ultimo = None
    for nome, raw in membri_csv(archivio):
        if ultimo is None or nome > ultimo[0]:
            ultimo = (nome, raw)
    df = leggi_csv(ultimo[1])
    cid, cprov = colonna(df, "idimpianto"), colonna(df, "provincia")
    cband = colonna(df, "bandiera")
    reg = df[cprov].str.strip().str.upper().map(PROVINCIA_REGIONE)
    marchio = df[cband].map(normalizza_bandiera)
    return dict(zip(df[cid].str.strip(), zip(reg, marchio)))


def elabora_giorno(df: pd.DataFrame, data: str, impianti: dict, acc: dict, acc_marchi: dict) -> int:
    """Aggiunge un giorno di prezzi agli accumulatori mensili (regione) e giornalieri (marchio)."""
    cid, ccarb = colonna(df, "idimpianto"), colonna(df, "desccarburante")
    cprezzo, cself = colonna(df, "prezzo"), colonna(df, "isself")
    carb = df[ccarb].str.strip().str.lower().map(CARBURANTI)
    self_ok = (df[cself].str.strip() == "1") | (carb == "GPL")
    prezzo = pd.to_numeric(df[cprezzo].str.replace(",", "."), errors="coerce")
    info = df[cid].str.strip().map(impianti)
    reg = info.map(lambda x: x[0] if isinstance(x, tuple) else None)
    marchio = info.map(lambda x: x[1] if isinstance(x, tuple) else None)
    ok = carb.notna() & self_ok & prezzo.between(0.40, 3.50) & reg.notna()
    base = pd.DataFrame({"regione": reg[ok], "marchio": marchio[ok], "carburante": carb[ok], "p": prezzo[ok]})
    mese = data[:7]
    for (r, c), row in base.groupby(["regione", "carburante"])["p"].agg(["sum", "count"]).iterrows():
        acc[(mese, r, c)][0] += row["sum"]
        acc[(mese, r, c)][1] += row["count"]
    for (m, r, c), row in base.groupby(["marchio", "regione", "carburante"])["p"].agg(["sum", "count"]).iterrows():
        acc_marchi[(data, m, r, c)][0] += row["sum"]
        acc_marchi[(data, m, r, c)][1] += row["count"]
    return int(ok.sum())


def elabora_prezzi(archivio: Path, impianti: dict, ogni: int, acc: dict, acc_marchi: dict):
    for i, (nome, raw) in enumerate(sorted(membri_csv(archivio), key=lambda x: x[0])):
        if i % ogni:
            continue
        m = RE_DATA.search(Path(nome).name) or RE_DATA.search(nome)
        if not m:
            continue
        data = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        n = elabora_giorno(leggi_csv(raw), data, impianti, acc, acc_marchi)
        print(f"    {data}: {n} prezzi validi")


def salva(acc: dict, acc_marchi: dict):
    if not acc:
        sys.exit("Nessun prezzo elaborato: controllare nomi file e colonne degli archivi.")
    out = pd.DataFrame([{"mese": k[0], "regione": k[1], "carburante": k[2],
                         "prezzo_medio": round(s / n, 4), "n_osservazioni": n}
                        for k, (s, n) in acc.items() if n]).sort_values(["carburante", "mese", "regione"])
    dest = DATA_DIR / "prezzi_regionali_mensili_mimit.csv"
    out.to_csv(dest, index=False)
    print(f"\nScritto {dest} ({len(out)} righe, mesi {out['mese'].min()} - {out['mese'].max()})")

    mar = pd.DataFrame([{"data": k[0], "marchio": k[1], "regione": k[2], "carburante": k[3],
                         "somma": round(s, 4), "n": n} for k, (s, n) in acc_marchi.items() if n])
    dest2 = DATA_DIR / "prezzi_marchi_giornalieri_mimit.csv"
    if dest2.exists():   # conserva i giorni aggiunti da aggiorna_giornaliero.py
        vecchio = pd.read_csv(dest2)
        mar = pd.concat([vecchio[~vecchio["data"].isin(mar["data"])], mar], ignore_index=True)
    mar.sort_values(["data", "marchio", "regione", "carburante"]).to_csv(dest2, index=False)
    print(f"Scritto {dest2} ({mar['data'].nunique()} giorni)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--da", default="2025-1")
    ap.add_argument("--a", default="2026-3")
    ap.add_argument("--ogni", type=int, default=1, help="usa un giorno ogni N")
    ap.add_argument("--elimina-archivi", action="store_true", help="cancella i .tar.gz dopo l'elaborazione")
    args = ap.parse_args()

    acc: dict = defaultdict(lambda: [0.0, 0])
    acc_marchi: dict = defaultdict(lambda: [0.0, 0])
    for anno, trim in trimestri(args.da, args.a):
        print(f"Trimestre {trim}/{anno}")
        ana = scarica("anagrafica_impianti_attivi", anno, trim)
        prz = scarica("prezzo_alle_8", anno, trim)
        impianti = mappa_impianti(ana)
        print(f"  impianti in anagrafica: {len(impianti)}")
        elabora_prezzi(prz, impianti, args.ogni, acc, acc_marchi)
        if args.elimina_archivi:
            ana.unlink(missing_ok=True)
            prz.unlink(missing_ok=True)
    salva(acc, acc_marchi)


if __name__ == "__main__":
    main()
