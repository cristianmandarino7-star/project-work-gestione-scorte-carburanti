"""Genera i dati DEMO coerenti con l'impresa (domanda) e con i livelli di prezzo nazionali (prezzi).

- domanda_mensile.csv: domanda mensile (migliaia di litri) del deposito per 4 articoli, gen 2025 - set 2026.
  Dati STIMATI/GENERATI, come ammesso dalla traccia: livello, trend, stagionalita' e rumore
  sono definiti in src/config.py e motivati nel rapporto.
- prezzi_regionali_mensili_demo.csv: prezzi medi mensili per regione e carburante (ILLUSTRATIVI).
- prezzi_marchi_giornalieri_demo.csv.gz: prezzi giornalieri per marchio (ILLUSTRATIVI).
  Vanno sostituiti con quelli reali prodotti da scripts/scarica_mimit.py.

Uso:  python scripts/genera_dati_demo.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.config import ARTICOLI, DATA_DIR, FINE_STORICO, INIZIO_STORICO, REGIONI  # noqa: E402


def genera_domanda(seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    mesi = pd.period_range(INIZIO_STORICO, FINE_STORICO, freq="M")
    righe = []
    for nome, p in ARTICOLI.items():
        for t, m in enumerate(mesi):
            trend = p["livello"] * (1 + p["trend_mensile"]) ** t
            stag = p["stagionalita"][m.month - 1]
            rumore = rng.normal(1.0, p["rumore"])
            righe.append({"mese": str(m), "articolo": nome, "quantita": round(trend * stag * rumore, 1)})
    return pd.DataFrame(righe)


def genera_prezzi(seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    mesi = pd.period_range(INIZIO_STORICO, FINE_STORICO, freq="M")
    base = {"Benzina": 1.76, "Gasolio": 1.68, "GPL": 0.73}
    # differenziale regionale fisso (EUR/l) + piccolo rumore mensile
    offset = {r: rng.normal(0, 0.018) for r in REGIONI}
    for r in ["Calabria", "Basilicata", "Trentino-Alto Adige/Südtirol", "Sardegna"]:
        offset[r] += 0.02
    righe = []
    for carb, b in base.items():
        livello = b
        for m in mesi:
            livello = livello * (1 + rng.normal(0, 0.012)) + (b - livello) * 0.15
            for r in REGIONI:
                k = 1.0 if carb != "GPL" else 0.5
                prezzo = livello + k * offset[r] + rng.normal(0, 0.004)
                righe.append({"mese": str(m), "regione": r, "carburante": carb,
                              "prezzo_medio": round(prezzo, 4), "n_osservazioni": None})
    return pd.DataFrame(righe)


def genera_marchi(prezzi_mensili: pd.DataFrame, seed: int = 11) -> pd.DataFrame:
    """Prezzi giornalieri per marchio (DIMOSTRATIVI): media mensile regionale + differenziale di marchio + rumore.
    Non simula alcun evento reale: servono solo a far funzionare la scheda finche' non si scaricano i dati MIMIT."""
    rng = np.random.default_rng(seed)
    differenziale = {"Q8": 0.010, "Q8 Easy": -0.030, "IP": 0.015, "Eni": -0.005, "Esso": 0.005,
                     "Tamoil": 0.0, "Pompe bianche": -0.040, "Altri": -0.015}
    impianti = {"Q8": 120, "Q8 Easy": 25, "IP": 220, "Eni": 200, "Esso": 100,
                "Tamoil": 75, "Pompe bianche": 250, "Altri": 100}   # per regione, ordine di grandezza
    giorni = pd.date_range(f"{INIZIO_STORICO}-01", pd.Period(FINE_STORICO, "M").end_time.normalize(), freq="D")
    pm = prezzi_mensili.set_index(["mese", "regione", "carburante"])["prezzo_medio"]
    righe = []
    for g in giorni:
        mese = g.strftime("%Y-%m")
        for (carb), k in [("Benzina", 1.0), ("Gasolio", 1.0), ("GPL", 0.4)]:
            for r in REGIONI:
                base = pm[(mese, r, carb)]
                for m, d in differenziale.items():
                    n = max(5, int(impianti[m] * rng.uniform(0.5, 1.5)))
                    prezzo = base + k * d + rng.normal(0, 0.003)
                    righe.append((g.strftime("%Y-%m-%d"), m, r, carb, round(prezzo * n, 3), n))
    return pd.DataFrame(righe, columns=["data", "marchio", "regione", "carburante", "somma", "n"])


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    genera_domanda().to_csv(DATA_DIR / "domanda_mensile.csv", index=False)
    prezzi = genera_prezzi()
    prezzi.to_csv(DATA_DIR / "prezzi_regionali_mensili_demo.csv", index=False)
    genera_marchi(prezzi).to_csv(DATA_DIR / "prezzi_marchi_giornalieri_demo.csv.gz", index=False)
    print("Creati i file demo in", DATA_DIR)
