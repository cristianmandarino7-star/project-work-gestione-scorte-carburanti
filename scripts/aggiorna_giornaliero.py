"""Aggiunge il giorno corrente al confronto tra marchi, usando i file giornalieri del MIMIT.

L'archivio trimestrale arriva fino al 30/09/2026: per seguire l'effetto dei tetti ai prezzi
di fine settembre servono i giorni di ottobre. Il MIMIT pubblica ogni mattina i file del giorno:
  https://www.mimit.gov.it/images/exportCSV/prezzo_alle_8.csv
  https://www.mimit.gov.it/images/exportCSV/anagrafica_impianti_attivi.csv

Eseguirlo una volta al giorno (anche con l'Utilita' di pianificazione di Windows):
  py scripts/aggiorna_giornaliero.py

Aggiorna solo data/prezzi_marchi_giornalieri_mimit.csv (le medie mensili restano ferme a settembre,
cosi' la previsione del Q4 resta confrontabile con i dati effettivi quando arriveranno).
"""

from __future__ import annotations

import sys
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scarica_mimit import RE_DATA, colonna, elabora_giorno, leggi_csv  # noqa: E402
from src.config import DATA_DIR, PROVINCIA_REGIONE, normalizza_bandiera  # noqa: E402

URL = "https://www.mimit.gov.it/images/exportCSV/{}.csv"


def scarica(nome: str) -> bytes:
    req = urllib.request.Request(URL.format(nome), headers={"User-Agent": "Mozilla/5.0 (project work)"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def main():
    raw_prezzi = scarica("prezzo_alle_8")
    raw_ana = scarica("anagrafica_impianti_attivi")
    prima_riga = raw_prezzi[:200].decode("utf-8", errors="replace").splitlines()[0]
    m = RE_DATA.search(prima_riga)
    giorno = f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else date.today().isoformat()

    ana = leggi_csv(raw_ana)
    cid, cprov, cband = colonna(ana, "idimpianto"), colonna(ana, "provincia"), colonna(ana, "bandiera")
    impianti = dict(zip(ana[cid].str.strip(),
                        zip(ana[cprov].str.strip().str.upper().map(PROVINCIA_REGIONE),
                            ana[cband].map(normalizza_bandiera))))

    acc, acc_marchi = defaultdict(lambda: [0.0, 0]), defaultdict(lambda: [0.0, 0])
    n = elabora_giorno(leggi_csv(raw_prezzi), giorno, impianti, acc, acc_marchi)
    nuovo = pd.DataFrame([{"data": k[0], "marchio": k[1], "regione": k[2], "carburante": k[3],
                           "somma": round(s, 4), "n": c} for k, (s, c) in acc_marchi.items() if c])

    dest = DATA_DIR / "prezzi_marchi_giornalieri_mimit.csv"
    if dest.exists():
        vecchio = pd.read_csv(dest)
        nuovo = pd.concat([vecchio[vecchio["data"] != giorno], nuovo], ignore_index=True)
    nuovo.sort_values(["data", "marchio", "regione", "carburante"]).to_csv(dest, index=False)
    print(f"Aggiunto il {giorno}: {n} prezzi validi -> {dest}")


if __name__ == "__main__":
    main()
