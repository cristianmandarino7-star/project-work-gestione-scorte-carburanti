"""Metodi previsionali e valutazione dell'accuratezza.

Ogni metodo e' una funzione  f(storico: np.ndarray, mesi: list[int], h: int) -> np.ndarray
che restituisce h previsioni a partire dalla fine dello storico.
`mesi` contiene il mese di calendario (1-12) di ogni osservazione: serve al metodo stagionale.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ------------------------------------------------------------------------------------------
# Metodi
# ------------------------------------------------------------------------------------------


def media_mobile_semplice(y, mesi, h, n=3):
    return np.repeat(np.mean(y[-n:]), h)


def media_mobile_ponderata(y, mesi, h, pesi=(1, 2, 3)):
    w = np.array(pesi, dtype=float)[-len(y):]
    return np.repeat(np.dot(y[-len(w):], w) / w.sum(), h)


def _ses(y, alpha):
    livello = y[0]
    sse = 0.0
    for v in y[1:]:
        sse += (v - livello) ** 2
        livello = alpha * v + (1 - alpha) * livello
    return livello, sse


def attenuazione_esponenziale(y, mesi, h):
    """Smorzamento esponenziale semplice; alpha scelto minimizzando l'errore quadratico in-sample."""
    migliore = min((_ses(y, a)[1], a) for a in np.arange(0.05, 1.0, 0.05))
    livello, _ = _ses(y, migliore[1])
    return np.repeat(livello, h)


def _holt(y, a, b):
    livello, trend = y[0], y[1] - y[0]
    sse = 0.0
    for v in y[1:]:
        prev = livello + trend
        sse += (v - prev) ** 2
        nuovo = a * v + (1 - a) * prev
        trend = b * (nuovo - livello) + (1 - b) * trend
        livello = nuovo
    return livello, trend, sse


def holt(y, mesi, h):
    """Smorzamento esponenziale doppio (Holt): livello + trend."""
    griglia = np.arange(0.1, 1.0, 0.1)
    _, a, b = min((_holt(y, a, b)[2], a, b) for a in griglia for b in griglia)
    livello, trend, _ = _holt(y, a, b)
    return livello + trend * np.arange(1, h + 1)


def regressione_lineare(y, mesi, h):
    t = np.arange(len(y))
    m, q = np.polyfit(t, y, 1)
    return q + m * np.arange(len(y), len(y) + h)


def indici_stagionali(y, mesi):
    """Indici moltiplicativi per mese di calendario: rapporto osservato / trend lineare, normalizzati a media 1."""
    t = np.arange(len(y))
    m, q = np.polyfit(t, y, 1)
    rapporti = y / (q + m * t)
    idx = pd.Series(rapporti).groupby(np.asarray(mesi)).mean().reindex(range(1, 13))
    idx = idx.fillna(1.0)
    return (idx / idx.mean()).to_numpy(), (m, q)


def stagionale_moltiplicativo(y, mesi, h):
    """Trend (regressione sulla serie destagionalizzata) x indice stagionale del mese."""
    if len(y) < 12:
        return regressione_lineare(y, mesi, h)
    idx, _ = indici_stagionali(y, mesi)
    destag = y / idx[np.asarray(mesi) - 1]
    t = np.arange(len(y))
    m, q = np.polyfit(t, destag, 1)
    futuri_t = np.arange(len(y), len(y) + h)
    futuri_mesi = [((mesi[-1] - 1 + k) % 12) + 1 for k in range(1, h + 1)]
    return (q + m * futuri_t) * idx[np.array(futuri_mesi) - 1]


METODI = {
    "Media mobile semplice (3)": media_mobile_semplice,
    "Media mobile ponderata (3-2-1)": media_mobile_ponderata,
    "Attenuazione esponenziale": attenuazione_esponenziale,
    "Holt (livello + trend)": holt,
    "Regressione lineare (trend)": regressione_lineare,
    "Stagionale moltiplicativo": stagionale_moltiplicativo,
}

# ------------------------------------------------------------------------------------------
# Valutazione
# ------------------------------------------------------------------------------------------


def backtest(serie: pd.Series, inizio_test: str) -> pd.DataFrame:
    """Previsioni a 1 passo con finestra crescente su ogni mese del periodo di test.

    serie: indice PeriodIndex mensile, valori di domanda.
    Restituisce un DataFrame long: mese, metodo, effettivo, previsto.
    """
    y = serie.to_numpy(dtype=float)
    mesi = [p.month for p in serie.index]
    start = serie.index.get_loc(pd.Period(inizio_test, "M"))
    righe = []
    for i in range(start, len(y)):
        for nome, f in METODI.items():
            prev = float(f(y[:i], mesi[:i], 1)[0])
            righe.append({"mese": serie.index[i], "metodo": nome, "effettivo": y[i], "previsto": prev})
    return pd.DataFrame(righe)


def metriche(bt: pd.DataFrame) -> pd.DataFrame:
    e = bt["effettivo"] - bt["previsto"]
    bt = bt.assign(err=e, abs_err=e.abs(), sq=e ** 2, ape=(e.abs() / bt["effettivo"]) * 100)
    out = bt.groupby("metodo").agg(MAE=("abs_err", "mean"), MAPE=("ape", "mean"),
                                   RMSE=("sq", lambda s: np.sqrt(s.mean())), Bias=("err", "mean"))
    # Tracking signal: somma errori / MAD -> segnala previsioni sistematicamente distorte
    out["Tracking signal"] = bt.groupby("metodo")["err"].sum() / out["MAE"]
    return out.reindex(METODI.keys())


def previsione(serie: pd.Series, metodo: str, h: int) -> pd.Series:
    y = serie.to_numpy(dtype=float)
    mesi = [p.month for p in serie.index]
    valori = METODI[metodo](y, mesi, h)
    idx = pd.period_range(serie.index[-1] + 1, periods=h, freq="M")
    return pd.Series(np.maximum(valori, 0), index=idx)


def valori_adattati(serie: pd.Series, metodo: str, min_obs: int = 3) -> pd.Series:
    """Previsione a 1 passo per ogni mese dello storico (per il grafico 'storico vs modello')."""
    y = serie.to_numpy(dtype=float)
    mesi = [p.month for p in serie.index]
    out = [np.nan] * min_obs + [float(METODI[metodo](y[:i], mesi[:i], 1)[0]) for i in range(min_obs, len(y))]
    return pd.Series(out, index=serie.index)
