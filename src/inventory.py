"""Stima delle quattro tipologie di scorte e trasformazione di scenario della domanda."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd

GIORNI_MESE = 30.4


@dataclass
class ParametriScorte:
    costo_acquisto: float          # EUR per litro
    lead_time_giorni: float
    dev_lead_time_giorni: float
    costo_ordine: float            # EUR per ordine
    mantenimento_annuo: float      # quota del valore (es. 0.18)
    livello_servizio: float        # es. 0.95
    flessibilita_capacita: float   # es. 0.10


def calcola_scorte(prev_12m: pd.Series, sigma_errore: float, p: ParametriScorte) -> dict:
    """prev_12m: previsione mensile dei prossimi 12 mesi (migliaia di litri).
    sigma_errore: deviazione standard dell'errore di previsione mensile (RMSE del metodo scelto).

    Criteri adottati (da motivare nel rapporto):
    - Ciclica      = Q*/2, con Q* lotto economico di Wilson (EOQ) sulla domanda annua prevista.
    - Sicurezza    = z * sqrt(LT * sigma_e^2 + d^2 * sigma_LT^2)   (LT in mesi; incertezza su domanda e lead time).
    - Pipeline     = d * LT  (merce ordinata e in viaggio durante il lead time).
    - Anticipata   = scorta costruita prima dei picchi quando la domanda supera la capacita' di
                     approvvigionamento mensile C = media * (1 + flessibilita'); media sull'anno.
    """
    d = prev_12m.to_numpy(dtype=float)
    D_annua = d.sum() * 1000                          # litri/anno
    d_mese = d.mean()                                  # migliaia di litri/mese
    h = p.costo_acquisto * p.mantenimento_annuo        # EUR/litro/anno
    eoq = np.sqrt(2 * D_annua * p.costo_ordine / h) / 1000  # migliaia di litri
    ciclica = eoq / 2

    z = NormalDist().inv_cdf(p.livello_servizio)
    lt = p.lead_time_giorni / GIORNI_MESE
    s_lt = p.dev_lead_time_giorni / GIORNI_MESE
    sicurezza = z * np.sqrt(lt * sigma_errore ** 2 + (d_mese ** 2) * s_lt ** 2)

    pipeline = d_mese * lt

    capacita = d_mese * (1 + p.flessibilita_capacita)
    anticipata_profilo = np.zeros(len(d))
    stock = 0.0
    for t in range(len(d) - 1, -1, -1):              # ricorsione all'indietro dai picchi
        anticipata_profilo[t] = stock                 # scorta da avere all'inizio del mese t
        stock = max(0.0, stock + d[t] - capacita)
    anticipata_iniziale = stock
    anticipata = float(np.mean(np.append(anticipata_profilo, anticipata_iniziale)))

    composizione = {"Ciclica": ciclica, "Sicurezza": sicurezza,
                    "Anticipata": anticipata, "Pipeline": pipeline}
    valore = {k: v * 1000 * p.costo_acquisto for k, v in composizione.items()}
    return {
        "composizione": composizione,                  # migliaia di litri (scorta media)
        "valore_eur": valore,
        "eoq": eoq,
        "ordini_anno": D_annua / 1000 / eoq if eoq else 0,
        "punto_riordino": d_mese * lt + sicurezza,
        "z": z,
        "capacita_mensile": capacita,
        "anticipata_profilo": pd.Series(anticipata_profilo, index=prev_12m.index),
        "costo_mantenimento_annuo": sum(valore.values()) * p.mantenimento_annuo,
        "copertura_giorni": sum(composizione.values()) / d_mese * GIORNI_MESE,
    }


def applica_scenario(serie: pd.Series, var_mult=1.0, trend_mult=1.0, stag_mult=1.0,
                     shock_pct=0.0) -> pd.Series:
    """Scompone la serie in trend lineare x indice stagionale x residuo, poi riscala le componenti.

    var_mult   : moltiplica la componente casuale (variabilita')
    trend_mult : moltiplica la pendenza del trend
    stag_mult  : amplifica (>1) o smorza (<1) la stagionalita'
    shock_pct  : variazione percentuale del livello (es. +10 = domanda +10%)
    """
    y = serie.to_numpy(dtype=float)
    t = np.arange(len(y))
    mesi = np.array([p.month for p in serie.index])
    m, q = np.polyfit(t, y, 1)
    trend = q + m * t
    rapp = y / trend
    idx = pd.Series(rapp).groupby(mesi).mean().reindex(range(1, 13)).fillna(1.0)
    idx = idx / idx.mean()
    stag = idx.to_numpy()[mesi - 1]
    resid = rapp / stag

    q_mid = q + m * t.mean()                           # pivot al centro: il livello medio non cambia
    nuovo_trend = q_mid + m * trend_mult * (t - t.mean())
    nuova_stag = 1 + (stag - 1) * stag_mult
    nuovo_resid = 1 + (resid - 1) * var_mult
    out = nuovo_trend * nuova_stag * nuovo_resid * (1 + shock_pct / 100)
    return pd.Series(np.maximum(out, 0), index=serie.index)
