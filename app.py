"""Mini-dashboard: previsione della domanda e pianificazione delle scorte - rete carburanti.

Avvio:  streamlit run app.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src import config as C
from src import forecasting as F
from src.inventory import ParametriScorte, applica_scenario, calcola_scorte

# --------------------------------------------------------------------------------------------
# Stile (palette categoriale validata per daltonismo, rampa sequenziale blu per la mappa)
# --------------------------------------------------------------------------------------------
BLU, ARANCIO, ACQUA, GIALLO, GRIGIO = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a8984"
COLORI_SCORTE = {"Ciclica": BLU, "Sicurezza": ARANCIO, "Anticipata": ACQUA, "Pipeline": GIALLO}
SCALA_MAPPA = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

st.set_page_config(page_title="Domanda e scorte carburanti", page_icon="⛽", layout="wide")
st.markdown("""<style>
div[data-testid="stMetricValue"] {font-size: 1.6rem;}
.block-container {padding-top: 1.6rem;}
.nota {color: #6b6a66; font-size: 0.85rem;}
</style>""", unsafe_allow_html=True)


MESI_IT = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"]
BREVE = {"Media mobile semplice (3)": "Media mobile", "Media mobile ponderata (3-2-1)": "Media ponderata",
         "Attenuazione esponenziale": "Esponenziale", "Holt (livello + trend)": "Holt",
         "Regressione lineare (trend)": "Regressione", "Stagionale moltiplicativo": "Stagionale"}


def etichette(periodi) -> list[str]:
    return [f"{MESI_IT[p.month - 1]} {str(p.year)[2:]}" for p in periodi]


def stile(fig: go.Figure, altezza: int = 380, legenda: bool = True) -> go.Figure:
    fig.update_layout(
        template="plotly_white", height=altezza, margin=dict(l=10, r=10, t=40, b=10),
        hovermode="x unified", font=dict(size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0) if legenda else None,
        showlegend=legenda,
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="rgba(128,128,128,0.15)", zeroline=False)
    return fig


# --------------------------------------------------------------------------------------------
# Dati
# --------------------------------------------------------------------------------------------
@st.cache_data
def carica_domanda() -> dict[str, pd.Series]:
    df = pd.read_csv(C.DATA_DIR / "domanda_mensile.csv")
    out = {}
    for art, g in df.groupby("articolo"):
        out[art] = pd.Series(g["quantita"].to_numpy(), index=pd.PeriodIndex(g["mese"], freq="M"))
    return {a: out[a] for a in C.ARTICOLI if a in out}


@st.cache_data
def carica_prezzi() -> tuple[pd.DataFrame, str]:
    reali = C.DATA_DIR / "prezzi_regionali_mensili_mimit.csv"
    if reali.exists():
        return pd.read_csv(reali), "Dati reali MIMIT (prezzo alle 8, media mensile per regione) · licenza IODL 2.0"
    return (pd.read_csv(C.DATA_DIR / "prezzi_regionali_mensili_demo.csv"),
            "Dati DIMOSTRATIVI - eseguire scripts/scarica_mimit.py per i prezzi reali MIMIT")


@st.cache_data
def carica_geojson() -> dict:
    return json.loads((C.DATA_DIR / "regioni_italia.geojson").read_text(encoding="utf-8"))


@st.cache_data
def valuta(serie: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    bt = F.backtest(serie, C.INIZIO_TEST)
    return bt, F.metriche(bt)


@st.cache_data
def prezzi_con_previsione(prezzi: pd.DataFrame, carburante: str, criterio: str):
    """Prevede Q4 per ogni regione con il metodo migliore sulla serie nazionale."""
    sub = prezzi[prezzi["carburante"] == carburante]
    naz = sub.groupby("mese")["prezzo_medio"].mean()
    naz.index = pd.PeriodIndex(naz.index, freq="M")
    _, met = valuta(naz)
    metodo = met[criterio].idxmin()
    righe = []
    for reg, g in sub.groupby("regione"):
        s = pd.Series(g["prezzo_medio"].to_numpy(), index=pd.PeriodIndex(g["mese"], freq="M")).sort_index()
        for m, v in F.previsione(s, metodo, 3).items():
            righe.append({"mese": str(m), "regione": reg, "carburante": carburante, "prezzo_medio": v,
                          "previsto": True})
    storico = sub.assign(previsto=False)
    return pd.concat([storico, pd.DataFrame(righe)], ignore_index=True), metodo, met, naz


@st.cache_data
def carica_marchi() -> tuple[pd.DataFrame, str, bool]:
    reali = C.DATA_DIR / "prezzi_marchi_giornalieri_mimit.csv"
    if reali.exists():
        df, fonte, demo = pd.read_csv(reali), "Dati reali MIMIT (prezzo alle 8, self service per benzina e gasolio) · licenza IODL 2.0", False
    else:
        df = pd.read_csv(C.DATA_DIR / "prezzi_marchi_giornalieri_demo.csv.gz")
        fonte, demo = "Dati DIMOSTRATIVI - eseguire scripts/scarica_mimit.py per i prezzi reali per marchio", True
    df["data"] = pd.to_datetime(df["data"])
    return df, fonte, demo


def media_marchi(df: pd.DataFrame, chiavi: list[str]) -> pd.DataFrame:
    """Media ponderata sul numero di osservazioni (somma prezzi / numero prezzi)."""
    g = df.groupby(chiavi, as_index=False)[["somma", "n"]].sum()
    return g.assign(prezzo=g["somma"] / g["n"])


domanda = carica_domanda()
prezzi, fonte_prezzi = carica_prezzi()

# --------------------------------------------------------------------------------------------
# Barra laterale: scenario
# --------------------------------------------------------------------------------------------
st.sidebar.title("⛽ Configura scenario")
articolo = st.sidebar.selectbox("Articolo", list(domanda.keys()))
info = C.ARTICOLI[articolo]
st.sidebar.caption(f"Andamento: {info['andamento']}")

st.sidebar.subheader("Caratteristiche della domanda")
var_mult = st.sidebar.slider("Variabilità (× componente casuale)", 0.0, 3.0, 1.0, 0.25)
trend_mult = st.sidebar.slider("Trend (× pendenza)", -2.0, 3.0, 1.0, 0.25)
stag_mult = st.sidebar.slider("Stagionalità (× ampiezza)", 0.0, 2.0, 1.0, 0.25)
shock = st.sidebar.slider("Variazione livello domanda (%)", -30, 30, 0, 5)

st.sidebar.subheader("Approvvigionamento")
lt = st.sidebar.slider("Lead time (giorni)", 1, 45, int(info["lead_time_giorni"]))
dev_lt = st.sidebar.slider("Variabilità lead time (dev. std, giorni)", 0, 15, int(info["dev_lead_time_giorni"]))
servizio = st.sidebar.slider("Livello di servizio", 0.80, 0.995, C.LIVELLO_SERVIZIO, 0.005, format="%.3f")
flex = st.sidebar.slider("Flessibilità capacità di fornitura (%)", 0, 50, int(C.FLESSIBILITA_CAPACITA * 100), 5)

with st.sidebar.expander("Parametri economici"):
    costo_ordine = st.number_input("Costo per ordine (€)", 50.0, 10000.0, C.COSTO_ORDINE_EUR, 50.0)
    mantenimento = st.number_input("Costo mantenimento annuo (% valore)", 1.0, 60.0, C.MANTENIMENTO_ANNUO * 100, 1.0) / 100
    costo_acq = st.number_input("Costo d'acquisto (€/litro)", 0.1, 3.0, float(info["costo_acquisto"]), 0.01)

st.sidebar.subheader("Previsione")
criterio = st.sidebar.radio("Indicatore per scegliere il metodo", ["MAPE", "MAE", "RMSE"], horizontal=True)
scelta_metodo = st.sidebar.selectbox("Metodo usato per scorte", ["Automatico (migliore)"] + list(F.METODI))
st.sidebar.caption("Fonti: prezzi MIMIT (IODL 2.0) · confini regionali © ISTAT, elaborazione openpolis "
                   "(CC BY 4.0) · domanda del deposito: dati generati. Dettagli in ATTRIBUZIONI.md")

# --------------------------------------------------------------------------------------------
# Calcoli
# --------------------------------------------------------------------------------------------
serie_base = domanda[articolo]
scenario_modificato = (var_mult, trend_mult, stag_mult, shock) != (1.0, 1.0, 1.0, 0)
serie = applica_scenario(serie_base, var_mult, trend_mult, stag_mult, shock) if scenario_modificato else serie_base

bt, met = valuta(serie)
migliore = met[criterio].idxmin()
metodo = migliore if scelta_metodo.startswith("Automatico") else scelta_metodo
prev12 = F.previsione(serie, metodo, 12)
prevQ4 = prev12.iloc[:3]


def parametri(lead=lt, dev=dev_lt, art_info=None) -> ParametriScorte:
    return ParametriScorte(costo_acq if art_info is None else art_info["costo_acquisto"], lead, dev,
                           costo_ordine, mantenimento, servizio, flex / 100)


scorte = calcola_scorte(prev12, met.loc[metodo, "RMSE"], parametri())

# scenario base (dati originali, lead time di default) per il confronto
bt0, met0 = valuta(serie_base)
met_base = met0[criterio].idxmin()
scorte_base = calcola_scorte(F.previsione(serie_base, met_base, 12), met0.loc[met_base, "RMSE"],
                             parametri(info["lead_time_giorni"], info["dev_lead_time_giorni"]))

# --------------------------------------------------------------------------------------------
# Intestazione
# --------------------------------------------------------------------------------------------
st.title("Previsione della domanda e pianificazione delle scorte")
st.markdown(f"**{C.IMPRESA['nome']}** · {C.IMPRESA['unita_analizzata']}  \n"
            f"<span class='nota'>Storico gen 2025 – set 2026 · previsione ottobre – dicembre 2026 · "
            f"quantità in migliaia di litri</span>", unsafe_allow_html=True)
if scenario_modificato:
    st.info("Scenario modificato attivo: la domanda storica è stata ricostruita con i parametri della barra laterale.")

tab_dom, tab_scorte, tab_prezzi, tab_marchi, tab_metodo = st.tabs(
    ["📈 Domanda e previsioni", "📦 Scorte e scenari", "🗺️ Prezzi per regione", "🏷️ Confronto marchi",
     "ℹ️ Metodologia"])

# ============================================================================================
# TAB 1 - Domanda
# ============================================================================================
with tab_dom:
    q4_2025 = serie.loc[pd.Period("2025-10", "M"):pd.Period("2025-12", "M")].sum()
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Previsione Q4 2026", f"{prevQ4.sum():,.0f}".replace(",", "."),
              f"{(prevQ4.sum() / q4_2025 - 1) * 100:+.1f}% vs Q4 2025")
    k2.metric("Metodo utilizzato", BREVE.get(metodo, metodo), help=metodo)
    k3.metric(f"{criterio} del metodo", f"{met.loc[metodo, criterio]:.2f}" + ("%" if criterio == "MAPE" else ""))
    k4.metric("Bias medio (eff. − prev.)", f"{met.loc[metodo, 'Bias']:+.1f}")

    mostra_tutti = st.toggle("Mostra la previsione Q4 di tutti i metodi", value=False)
    fig = go.Figure()
    if scenario_modificato:
        fig.add_scatter(x=etichette(serie_base.index), y=serie_base, name="Storico originale",
                        line=dict(color=GRIGIO, width=1.5, dash="dot"))
    fig.add_scatter(x=etichette(serie.index), y=serie, name="Domanda storica",
                    mode="lines+markers", line=dict(color=BLU, width=2), marker=dict(size=7))
    bt_sel = bt[bt["metodo"] == metodo]
    fig.add_scatter(x=etichette(pd.PeriodIndex(bt_sel["mese"])), y=bt_sel["previsto"],
                    name="Previsione a 1 passo (backtest)", mode="lines+markers",
                    line=dict(color=GRIGIO, width=1.5, dash="dash"), marker=dict(size=6, symbol="diamond"))
    ponte = pd.concat([serie.iloc[-1:], prevQ4])
    fig.add_scatter(x=etichette(ponte.index), y=ponte, name="Previsione Q4 2026",
                    mode="lines+markers", line=dict(color=ARANCIO, width=2.5), marker=dict(size=9))
    if mostra_tutti:
        for nome in F.METODI:
            if nome != metodo:
                p = pd.concat([serie.iloc[-1:], F.previsione(serie, nome, 3)])
                fig.add_scatter(x=etichette(p.index), y=p, name=nome, line=dict(width=1), opacity=0.6)
    n = len(serie)
    fig.add_vrect(x0=n - 0.5, x1=n + 2.5, fillcolor=ARANCIO, opacity=0.07, line_width=0,
                  annotation_text="Q4 previsto", annotation_position="top left")
    fig.add_vrect(x0=n - 9.5, x1=n - 0.5, fillcolor=GRIGIO, opacity=0.05, line_width=0,
                  annotation_text="finestra di test", annotation_position="top left")
    fig.update_xaxes(type="category", categoryorder="array",
                     categoryarray=etichette(pd.period_range(serie.index[0], periods=n + 3, freq="M")))
    fig.update_yaxes(title="migliaia di litri")
    st.plotly_chart(stile(fig, 420), width="stretch")

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(f"**Accuratezza dei metodi** · backtest a 1 passo, gen–set 2026 · criterio: {criterio}")
        ordinati = met.sort_values(criterio)
        figm = go.Figure(go.Bar(
            x=ordinati[criterio], y=ordinati.index, orientation="h",
            marker_color=[ARANCIO if i == migliore else BLU for i in ordinati.index],
            text=[f"{v:.2f}" for v in ordinati[criterio]], textposition="outside",
            hovertemplate="%{y}: %{x:.2f}<extra></extra>"))
        figm.update_yaxes(autorange="reversed")
        figm.update_xaxes(title=criterio + (" (%)" if criterio == "MAPE" else " (migliaia di litri)"),
                          range=[0, ordinati[criterio].max() * 1.15])
        st.plotly_chart(stile(figm, 320, legenda=False).update_layout(hovermode="closest"),
                        width="stretch")
    with c2:
        st.markdown("**Indicatori di errore**")
        st.dataframe(met.style.format("{:.2f}").highlight_min(subset=["MAE", "MAPE", "RMSE"], color="#ffe1d3"),
                     width="stretch", height=280)
        st.caption("Tracking signal oltre ±4 indica una previsione sistematicamente distorta.")

    st.markdown("**Riepilogo per articolo** (dati originali)")
    righe = []
    for art, s in domanda.items():
        _, m = valuta(s)
        best = m[criterio].idxmin()
        p = F.previsione(s, best, 3)
        righe.append({"Articolo": art, "Andamento": C.ARTICOLI[art]["andamento"], "Metodo migliore": best,
                      "MAPE %": round(m.loc[best, "MAPE"], 2),
                      "Ott 26": round(p.iloc[0]), "Nov 26": round(p.iloc[1]), "Dic 26": round(p.iloc[2]),
                      "Totale Q4": round(p.sum())})
    st.dataframe(pd.DataFrame(righe), width="stretch", hide_index=True)

# ============================================================================================
# TAB 2 - Scorte
# ============================================================================================
with tab_scorte:
    comp = scorte["composizione"]
    totale = sum(comp.values())
    base_tot = sum(scorte_base["composizione"].values())
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Scorta media totale", f"{totale:,.0f} k l".replace(",", "."),
              f"{(totale / base_tot - 1) * 100:+.1f}% vs base" if base_tot else None, delta_color="inverse")
    k2.metric("Valore immobilizzato", f"€ {sum(scorte['valore_eur'].values()) / 1e6:,.2f} mln")
    k3.metric("Copertura", f"{scorte['copertura_giorni']:.1f} giorni")
    k4.metric("Lotto economico (EOQ)", f"{scorte['eoq']:,.0f} k l".replace(",", "."),
              f"{scorte['ordini_anno']:.0f} ordini/anno", delta_color="off")
    k5.metric("Punto di riordino", f"{scorte['punto_riordino']:,.0f} k l".replace(",", "."))

    if "scenari" not in st.session_state:
        st.session_state.scenari = {}
    c_save1, c_save2 = st.columns([3, 1])
    nome_scen = c_save1.text_input("Nome scenario da salvare",
                                   value=f"{articolo} · LT {lt} gg · var ×{var_mult} · serv. {servizio:.1%}")
    if c_save2.button("💾 Salva scenario", width="stretch"):
        st.session_state.scenari[nome_scen] = {"articolo": articolo, **comp}
    if st.session_state.scenari and st.button("Svuota scenari salvati"):
        st.session_state.scenari = {}

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown(f"**Composizione delle scorte nei diversi scenari** · {articolo} · scorta media, migliaia di litri")
        confronto = {"Base": scorte_base["composizione"], "Scenario corrente": comp}
        confronto.update({k: {t: v[t] for t in COLORI_SCORTE}
                          for k, v in st.session_state.scenari.items() if v["articolo"] == articolo})
        nomi = list(confronto)
        figc = go.Figure()
        for tipo, col in COLORI_SCORTE.items():
            figc.add_bar(x=nomi, y=[confronto[n][tipo] for n in nomi], name=tipo, marker_color=col,
                         marker_line=dict(color="white", width=2),
                         hovertemplate=f"{tipo}: %{{y:,.0f}} k l<extra></extra>")
        tot = [sum(confronto[n].values()) for n in nomi]
        figc.add_scatter(x=nomi, y=tot, mode="text", text=[f"{t:,.0f}" for t in tot],
                         textposition="top center", showlegend=False, hoverinfo="skip")
        figc.update_layout(barmode="stack", bargap=0.45)
        figc.update_yaxes(title="migliaia di litri")
        st.plotly_chart(stile(figc, 400), width="stretch")
    with c2:
        st.markdown("**Dettaglio scenario corrente**")
        tab = pd.DataFrame({
            "Scorta media (k l)": comp, "Valore (€)": scorte["valore_eur"],
            "Base (k l)": scorte_base["composizione"]}).round(0)
        tab.loc["Totale"] = tab.sum()
        st.dataframe(tab.style.format("{:,.0f}"), width="stretch")
        st.markdown(
            f"<span class='nota'>z = {scorte['z']:.2f} · costo mantenimento annuo ≈ "
            f"€ {scorte['costo_mantenimento_annuo']:,.0f} · capacità fornitura "
            f"{scorte['capacita_mensile']:,.0f} k l/mese · metodo: {metodo}</span>", unsafe_allow_html=True)

    st.markdown("**Scorta anticipata: domanda prevista dei prossimi 12 mesi vs capacità di fornitura**")
    figa = go.Figure()
    figa.add_bar(x=etichette(prev12.index), y=prev12, name="Domanda prevista", marker_color=BLU)
    figa.add_scatter(x=etichette(prev12.index), y=[scorte["capacita_mensile"]] * 12, name="Capacità mensile",
                     line=dict(color=GRIGIO, dash="dash", width=2))
    figa.add_scatter(x=etichette(prev12.index), y=scorte["anticipata_profilo"], name="Scorta anticipata (fine mese)",
                     mode="lines+markers", line=dict(color=ACQUA, width=2), marker=dict(size=8))
    figa.update_yaxes(title="migliaia di litri")
    st.plotly_chart(stile(figa, 340), width="stretch")

    st.markdown("**Confronto tra articoli** · parametri di default, metodo migliore")
    righe = []
    for art, s in domanda.items():
        a = C.ARTICOLI[art]
        _, m = valuta(s)
        best = m[criterio].idxmin()
        r = calcola_scorte(F.previsione(s, best, 12), m.loc[best, "RMSE"],
                           parametri(a["lead_time_giorni"], a["dev_lead_time_giorni"], a))
        righe.append({"Articolo": art, **r["composizione"], "Copertura (gg)": r["copertura_giorni"]})
    df_art = pd.DataFrame(righe).set_index("Articolo")
    figx = go.Figure()
    for tipo, col in COLORI_SCORTE.items():
        figx.add_bar(y=df_art.index, x=df_art[tipo] / df_art[list(COLORI_SCORTE)].sum(axis=1) * 100,
                     name=tipo, orientation="h", marker_color=col, marker_line=dict(color="white", width=2),
                     hovertemplate=f"{tipo}: %{{x:.1f}}%<extra></extra>")
    figx.update_layout(barmode="stack", hovermode="y unified")
    figx.update_xaxes(title="% della scorta media totale", range=[0, 100])
    st.plotly_chart(stile(figx, 300), width="stretch")

# ============================================================================================
# TAB 3 - Prezzi per regione
# ============================================================================================
with tab_prezzi:
    st.caption(fonte_prezzi)
    c0, c1, c2 = st.columns([1, 1, 2])
    carb = c0.radio("Carburante", C.CARBURANTI_PREZZI, horizontal=False)
    dati_p, metodo_p, met_p, naz = prezzi_con_previsione(prezzi, carb, criterio)
    mesi_disp = sorted(dati_p["mese"].unique())
    mese_sel = c1.selectbox("Mese sulla mappa", mesi_disp, index=len(mesi_disp) - 1,
                            format_func=lambda m: m + (" (previsione)" if m in C.ORIZZONTE_Q4 else ""))
    c2.markdown(f"Previsione Q4 con **{metodo_p}** (miglior {criterio} sulla serie nazionale: "
                f"{met_p.loc[metodo_p, criterio]:.2f}{'%' if criterio == 'MAPE' else ''})")

    vista = dati_p[dati_p["mese"] == mese_sel]
    cm, cr = st.columns([3, 2])
    with cm:
        figmap = go.Figure(go.Choroplethmap(
            geojson=carica_geojson(), featureidkey="properties.reg_name",
            locations=vista["regione"], z=vista["prezzo_medio"], colorscale=SCALA_MAPPA,
            marker_line_width=1, marker_line_color="white", marker_opacity=0.95,
            colorbar=dict(title="€/l", thickness=12),
            hovertemplate="<b>%{location}</b><br>%{z:.3f} €/l<extra></extra>"))
        figmap.update_layout(map=dict(style="white-bg", center=dict(lat=41.8, lon=12.8), zoom=4.6),
                             height=560, margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(figmap, width="stretch", config={"scrollZoom": False})
    with cr:
        st.markdown(f"**Prezzo medio per regione** · {carb} · {mese_sel}")
        ord_v = vista.sort_values("prezzo_medio")
        media = ord_v["prezzo_medio"].mean()
        figr = go.Figure(go.Bar(
            x=ord_v["prezzo_medio"] - media, y=ord_v["regione"].str.split("/").str[0], orientation="h",
            marker_color=[ARANCIO if v > media else BLU for v in ord_v["prezzo_medio"]],
            customdata=ord_v["prezzo_medio"],
            hovertemplate="%{y}: %{customdata:.3f} €/l (%{x:+.3f} vs media)<extra></extra>"))
        figr.update_xaxes(title=f"scostamento dalla media nazionale ({media:.3f} €/l)")
        st.plotly_chart(stile(figr, 540, legenda=False).update_layout(hovermode="closest"),
                        width="stretch")

    st.markdown(f"**Andamento mensile del prezzo medio** · {carb}")
    regione_trend = st.selectbox("Area", ["Italia (media regionale)"] + C.REGIONI,
                                 index=1 + C.REGIONI.index("Calabria"))
    if regione_trend.startswith("Italia"):
        trend = dati_p.groupby(["mese", "previsto"])["prezzo_medio"].mean().reset_index()
    else:
        trend = dati_p[dati_p["regione"] == regione_trend][["mese", "previsto", "prezzo_medio"]]
    figt = go.Figure()
    for flag, nome, col in [(False, "Storico", BLU), (True, "Previsione Q4 2026", ARANCIO)]:
        t = trend[trend["previsto"] == flag]
        figt.add_bar(x=etichette(pd.PeriodIndex(t["mese"], freq="M")), y=t["prezzo_medio"], name=nome, marker_color=col,
                     hovertemplate="%{x}: %{y:.3f} €/l<extra></extra>")
    ymin = trend["prezzo_medio"].min()
    figt.update_yaxes(title="€/litro", range=[ymin * 0.97, trend["prezzo_medio"].max() * 1.01])
    figt.update_layout(bargap=0.25)
    st.plotly_chart(stile(figt, 360), width="stretch")
    st.caption("L'asse verticale non parte da zero per rendere leggibili variazioni di pochi centesimi.")

# ============================================================================================
# TAB 4 - Confronto tra marchi
# ============================================================================================
COLORI_MARCHI = {"Q8": BLU, "IP": ARANCIO, "Eni": ACQUA, "Pompe bianche": GIALLO, "Esso": "#e87ba4",
                 "Tamoil": "#008300", "Q8 Easy": "#4a3aa7", "Altri": GRIGIO}

with tab_marchi:
    marchi_df, fonte_marchi, marchi_demo = carica_marchi()
    st.caption(fonte_marchi)
    if marchi_demo:
        st.warning("I prezzi per marchio sono dimostrativi: differenze e tendenze qui sotto non vanno interpretate "
                   "finché non si eseguono gli script MIMIT.")

    disponibili = [m for m in C.MARCHI if m in set(marchi_df["marchio"])]
    st.markdown("**Coppia da confrontare** · il differenziale è sempre calcolato come *A − B*")
    a1, a2, a3, a4 = st.columns([1.2, 1.2, 1, 1.4])
    def_a = disponibili.index(C.MARCHI_CONFRONTO[0]) if C.MARCHI_CONFRONTO[0] in disponibili else 0
    ma = a1.selectbox("Marchio A", disponibili, index=def_a, key="marchio_a")
    altri = [m for m in disponibili if m != ma]
    def_b = altri.index(C.MARCHI_CONFRONTO[1]) if C.MARCHI_CONFRONTO[1] in altri else 0
    mb = a2.selectbox("Marchio B", altri, index=def_b, key="marchio_b")
    carb_m = a3.radio("Carburante ", C.CARBURANTI_PREZZI, key="carb_marchi")
    area_m = a4.selectbox("Area", ["Italia"] + C.REGIONI, key="area_marchi")
    riferimento = [m for m in C.MARCHI_RIFERIMENTO if m in disponibili and m not in (ma, mb)]
    extra = st.multiselect("Altri marchi da mostrare sul grafico dei prezzi (riferimento)",
                           [m for m in disponibili if m not in (ma, mb)], default=riferimento)
    scelti = [ma, mb] + extra
    d_min, d_max = marchi_df["data"].min().date(), marchi_df["data"].max().date()
    periodo = st.slider("Periodo", d_min, d_max, (d_min, d_max), format="DD/MM/YYYY")

    sub = marchi_df[(marchi_df["carburante"] == carb_m)
                    & marchi_df["data"].between(pd.Timestamp(periodo[0]), pd.Timestamp(periodo[1]))]
    if area_m != "Italia":
        sub = sub[sub["regione"] == area_m]
    giorn = media_marchi(sub, ["data", "marchio"])
    tab_g = giorn.pivot(index="data", columns="marchio", values="prezzo").sort_index()

    if ma in tab_g and mb in tab_g:
        diff = (tab_g[ma] - tab_g[mb]).dropna() * 100           # centesimi/litro
        n_imp = sub.groupby(["data", "marchio"])["n"].sum().groupby("marchio").mean()
        k1, k2, k3, k4 = st.columns(4)
        k1.metric(f"Prezzo medio {ma}", f"{tab_g[ma].mean():.3f} €/l")
        k2.metric(f"Prezzo medio {mb}", f"{tab_g[mb].mean():.3f} €/l")
        k3.metric(f"Differenza media {ma} − {mb}", f"{diff.mean():+.1f} cent/l",
                  help=f"Ultimo giorno del periodo: {diff.iloc[-1]:+.1f} cent/l")
        k4.metric(f"Giorni con {ma} più economica", f"{(diff < 0).mean() * 100:.0f}%")
        st.caption(f"Ultimo giorno: {ma} − {mb} = {diff.iloc[-1]:+.1f} cent/l · "
                   f"Impianti con prezzo rilevato al giorno (media): {ma} {n_imp.get(ma, 0):,.0f} · "
                   f"{mb} {n_imp.get(mb, 0):,.0f}".replace(",", "."))

    liscia = st.toggle("Media mobile a 7 giorni", value=True)
    figp = go.Figure()
    for m in scelti:
        if m in tab_g:
            y = tab_g[m].rolling(7, min_periods=1).mean() if liscia else tab_g[m]
            figp.add_scatter(x=y.index, y=y, name=m, mode="lines",
                             line=dict(color=COLORI_MARCHI.get(m, GRIGIO), width=2.8 if m in (ma, mb) else 1.3,
                                       dash="solid" if m in (ma, mb) else "dot"),
                             hovertemplate=f"{m}: %{{y:.3f}} €/l<extra></extra>")
    for data_ev, etichetta, descr_ev, fonte_ev in C.EVENTI:
        t = pd.Timestamp(data_ev)
        if pd.Timestamp(periodo[0]) <= t <= pd.Timestamp(periodo[1]):
            figp.add_vline(x=t, line=dict(color=GRIGIO, dash="dot", width=1))
            figp.add_annotation(x=t, y=1, yref="paper", text=etichetta, showarrow=False, textangle=-90,
                                xanchor="right", yanchor="top", font=dict(size=10, color="#6b6a66"),
                                hovertext=f"{descr_ev} (fonte: {fonte_ev})")
    figp.update_yaxes(title="€/litro")
    st.markdown(f"**Prezzo medio giornaliero per marchio** · {carb_m} · {area_m}")
    st.plotly_chart(stile(figp, 440), width="stretch")

    if ma in tab_g and mb in tab_g:
        cs, cm = st.columns([3, 2])
        with cs:
            st.markdown(f"**Differenziale {ma} − {mb}** · media settimanale, centesimi/litro")
            sett = diff.resample("W-MON").mean()
            figd = go.Figure(go.Bar(
                x=sett.index, y=sett, marker_color=[ARANCIO if v > 0 else BLU for v in sett],
                hovertemplate="settimana del %{x|%d/%m/%Y}: %{y:+.2f} cent<extra></extra>"))
            figd.add_hline(y=0, line=dict(color=GRIGIO, width=1))
            figd.update_yaxes(title=f"cent/l (arancio = {ma} più cara)")
            st.plotly_chart(stile(figd, 360, legenda=False).update_layout(hovermode="closest"), width="stretch")
        with cm:
            st.markdown(f"**Differenziale medio per regione** · {ma} − {mb}, cent/l")
            reg = media_marchi(marchi_df[(marchi_df["carburante"] == carb_m) & marchi_df["data"].between(
                pd.Timestamp(periodo[0]), pd.Timestamp(periodo[1]))], ["regione", "marchio"])
            reg = reg.pivot(index="regione", columns="marchio", values="prezzo")
            if ma in reg and mb in reg:
                gap = ((reg[ma] - reg[mb]) * 100).dropna()
                lim = max(abs(gap.min()), abs(gap.max()), 0.1)
                figg = go.Figure(go.Choroplethmap(
                    geojson=carica_geojson(), featureidkey="properties.reg_name", locations=gap.index, z=gap,
                    colorscale=[[0, "#256abf"], [0.5, "#f0efec"], [1, "#e34948"]], zmin=-lim, zmax=lim,
                    marker_line_width=1, marker_line_color="white", colorbar=dict(title="cent/l", thickness=12),
                    hovertemplate="<b>%{location}</b><br>%{z:+.2f} cent/l<extra></extra>"))
                figg.update_layout(map=dict(style="white-bg", center=dict(lat=41.8, lon=12.8), zoom=4.1),
                                   height=360, margin=dict(l=0, r=0, t=0, b=0))
                st.plotly_chart(figg, width="stretch", config={"scrollZoom": False})
                st.caption(f"Blu: {ma} più economica · rosso: {ma} più cara")

    st.markdown("**Prima e dopo un evento** · variazione del prezzo medio per marchio")
    e1, e2 = st.columns([2, 1])
    opzioni_ev = {f"{d} – {t}": d for d, _, t, _ in C.EVENTI}
    scelta_ev = e1.selectbox("Evento", list(opzioni_ev) + ["Data personalizzata"])
    data_ev = (e1.date_input("Data", value=d_max, min_value=d_min, max_value=d_max)
               if scelta_ev == "Data personalizzata" else pd.Timestamp(opzioni_ev[scelta_ev]).date())
    finestra = e2.slider("Giorni prima / dopo", 3, 30, 7)
    t0 = pd.Timestamp(data_ev)
    base_ev = marchi_df[marchi_df["carburante"] == carb_m]
    if area_m != "Italia":
        base_ev = base_ev[base_ev["regione"] == area_m]
    prima = media_marchi(base_ev[base_ev["data"].between(t0 - pd.Timedelta(days=finestra), t0 - pd.Timedelta(days=1))],
                         ["marchio"]).set_index("marchio")["prezzo"]
    dopo = media_marchi(base_ev[base_ev["data"].between(t0, t0 + pd.Timedelta(days=finestra - 1))],
                        ["marchio"]).set_index("marchio")["prezzo"]
    giorni_dopo = base_ev[base_ev["data"] >= t0]["data"].nunique()
    if prima.empty or dopo.empty:
        st.info("Non ci sono dati sufficienti prima o dopo la data scelta: per gli eventi di fine settembre "
                "servono i giorni di ottobre (scripts/aggiorna_giornaliero.py).")
    else:
        ev = pd.DataFrame({"Prima (€/l)": prima, "Dopo (€/l)": dopo}).reindex(
            [m for m in C.MARCHI if m in prima.index and m in dopo.index])
        ev["Variazione (cent/l)"] = (ev["Dopo (€/l)"] - ev["Prima (€/l)"]) * 100
        st.dataframe(ev.style.format({"Prima (€/l)": "{:.3f}", "Dopo (€/l)": "{:.3f}",
                                      "Variazione (cent/l)": "{:+.2f}"}), width="stretch")
        if giorni_dopo < finestra:
            st.caption(f"Attenzione: dopo la data ci sono solo {min(giorni_dopo, finestra)} giorni di dati.")

    st.markdown("**Previsione Q4 2026 del prezzo medio mensile per marchio**")
    mens = media_marchi(marchi_df[marchi_df["carburante"] == carb_m].assign(
        mese=lambda d: d["data"].dt.to_period("M"))
        .pipe(lambda d: d if area_m == "Italia" else d[d["regione"] == area_m]), ["mese", "marchio"])
    righe_prev = []
    for m in [x for x in scelti if x in set(mens["marchio"])]:
        s_m = mens[mens["marchio"] == m].set_index("mese")["prezzo"].sort_index()
        s_m = s_m[s_m.index <= pd.Period(C.FINE_STORICO, "M")]
        if len(s_m) < 13:
            continue
        _, met_m = valuta(s_m)
        best_m = met_m[criterio].idxmin()
        pv = F.previsione(s_m, best_m, 3)
        righe_prev.append({"Marchio": m, "Set 26": s_m.iloc[-1], "Ott 26": pv.iloc[0], "Nov 26": pv.iloc[1],
                           "Dic 26": pv.iloc[2], "Metodo": best_m, "MAPE %": met_m.loc[best_m, "MAPE"]})
    if righe_prev:
        st.dataframe(pd.DataFrame(righe_prev).style.format(
            {"Set 26": "{:.3f}", "Ott 26": "{:.3f}", "Nov 26": "{:.3f}", "Dic 26": "{:.3f}", "MAPE %": "{:.2f}"}),
            width="stretch", hide_index=True)
        st.caption("I metodi statistici proiettano lo storico: non conoscono i tetti ai prezzi decisi a fine "
                   "settembre. Confrontare queste previsioni con i prezzi effettivi di ottobre mostra quanto una "
                   "decisione strategica dell'impresa possa spiazzare una previsione basata solo sul passato.")

# ============================================================================================
# TAB 5 - Metodologia
# ============================================================================================
with tab_metodo:
    st.markdown(f"""
### Impresa e dati
- **Impresa:** {C.IMPRESA['nome']} – {C.IMPRESA['settore']}.
- **Unità analizzata:** {C.IMPRESA['unita_analizzata']}; rifornisce i punti vendita della rete.
- **Domanda:** serie mensili gen 2025 – set 2026 per quattro articoli con andamenti diversi
  (stagionale, stazionario, trend, irregolare), generate coerentemente con i volumi regionali
  e con i parametri in `src/config.py`.
- **Prezzi:** archivio MIMIT dei prezzi praticati (prezzo alle 8), aggregato per regione e mese
  con `scripts/scarica_mimit.py`.

### Metodi previsionali
Media mobile semplice e ponderata, attenuazione esponenziale (α ottimizzato), Holt,
regressione lineare del trend, metodo stagionale moltiplicativo (trend × indici mensili).
L'accuratezza è misurata con un **backtest a finestra crescente**: per ogni mese gen–set 2026
ogni metodo prevede il mese successivo usando solo i dati precedenti. Indicatori: MAE, MAPE,
RMSE, bias e tracking signal. Il metodo con l'indicatore scelto più basso viene usato per Q4.

### Scorte
| Tipo | Criterio |
|---|---|
| Ciclica | Q*/2, con Q* = √(2·D·S / h) (lotto economico di Wilson) |
| Sicurezza | z · √(LT·σₑ² + d²·σ_LT²): incertezza su domanda (RMSE del metodo) e lead time |
| Pipeline | d · LT: merce ordinata e in transito |
| Anticipata | accumulo prima dei picchi quando la domanda supera la capacità C = d̄·(1+flessibilità) |

### Scenari
Lo storico viene scomposto in trend × stagionalità × componente casuale; i cursori riscalano
ciascuna componente, poi previsioni e scorte vengono ricalcolate.

### Confronto tra marchi (default Q8 vs IP, coppia selezionabile)
Ogni impianto dell'anagrafica MIMIT viene ricondotto al proprio marchio (campo *Bandiera*); il prezzo
medio giornaliero di un marchio è la media di tutti i prezzi self service (GPL: qualsiasi modalità)
rilevati alle 8 nei suoi impianti. Il differenziale A − B tra i due marchi scelti è espresso in
centesimi al litro (positivo = A più caro).
L'analisi "prima e dopo" confronta la media dei N giorni precedenti un evento con quella dei N giorni
successivi. Limiti: le reti hanno diffusione territoriale diversa (per questo si può filtrare per regione),
e Q8 Easy, rete a basso costo, è tenuta separata da Q8.
""")
