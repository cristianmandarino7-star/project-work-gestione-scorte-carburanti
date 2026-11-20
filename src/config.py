"""Configurazione generale: impresa, articoli, parametri di approvvigionamento, mappature territoriali."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

# --------------------------------------------------------------------------------------
# Impresa e periodo di analisi
# --------------------------------------------------------------------------------------
IMPRESA = {
    "nome": "Kuwait Petroleum Italia S.p.A. (marchio Q8)",
    "unita_analizzata": "Deposito di rifornimento della rete stradale in Calabria",
    "settore": "Distribuzione di carburanti per autotrazione (downstream petrolifero)",
}

INIZIO_STORICO = "2025-01"
FINE_STORICO = "2026-09"          # ultimo mese osservato
ORIZZONTE_Q4 = ["2026-10", "2026-11", "2026-12"]
INIZIO_TEST = "2026-01"           # finestra di valutazione dell'accuratezza (gen-set 2026)

# --------------------------------------------------------------------------------------
# Articoli: andamenti di domanda volutamente diversi (richiesto dalla traccia)
# Quantita' in migliaia di litri al mese, prezzi di acquisto in EUR/litro
# --------------------------------------------------------------------------------------
ARTICOLI = {
    "Benzina": {
        "andamento": "stagionale (picco estivo per il turismo)",
        "livello": 1800, "trend_mensile": -0.002, "rumore": 0.035,
        "stagionalita": [0.86, 0.82, 0.91, 0.97, 1.02, 1.12, 1.26, 1.36, 1.04, 0.95, 0.86, 0.93],
        "costo_acquisto": 1.45, "lead_time_giorni": 4, "dev_lead_time_giorni": 1,
    },
    "Gasolio": {
        "andamento": "stazionario (trasporto merci e pendolarismo)",
        "livello": 4200, "trend_mensile": 0.0, "rumore": 0.03,
        "stagionalita": [0.97, 0.96, 1.00, 1.00, 1.02, 1.03, 1.04, 1.02, 1.01, 1.00, 0.98, 0.97],
        "costo_acquisto": 1.38, "lead_time_giorni": 4, "dev_lead_time_giorni": 1,
    },
    "AdBlue": {
        "andamento": "trend crescente (rinnovo parco veicoli diesel Euro 6)",
        "livello": 140, "trend_mensile": 0.022, "rumore": 0.03,
        "stagionalita": [1.0] * 12,
        "costo_acquisto": 0.55, "lead_time_giorni": 10, "dev_lead_time_giorni": 3,
    },
    "GPL": {
        "andamento": "irregolare / casuale con lieve calo",
        "livello": 620, "trend_mensile": -0.004, "rumore": 0.11,
        "stagionalita": [1.0] * 12,
        "costo_acquisto": 0.48, "lead_time_giorni": 7, "dev_lead_time_giorni": 2,
    },
}

# Parametri economici di default (modificabili dalla dashboard)
COSTO_ORDINE_EUR = 650.0        # costo fisso per ordine/consegna con autobotte
MANTENIMENTO_ANNUO = 0.18       # costo di mantenimento annuo in % del valore
LIVELLO_SERVIZIO = 0.95
FLESSIBILITA_CAPACITA = 0.10    # capacita' mensile di approvvigionamento = media * (1 + flessibilita')

# --------------------------------------------------------------------------------------
# Mappatura province -> regioni (nomi identici al GeoJSON openpolis)
# Sono incluse anche le sigle storiche della Sardegna presenti negli archivi MIMIT.
# --------------------------------------------------------------------------------------
_REG = {
    "Piemonte": "TO VC NO CN AT AL BI VB",
    "Valle d'Aosta/Vallée d'Aoste": "AO",
    "Lombardia": "VA CO SO MI BG BS PV CR MN LC LO MB",
    "Trentino-Alto Adige/Südtirol": "BZ TN",
    "Veneto": "VR VI BL TV VE PD RO",
    "Friuli-Venezia Giulia": "UD GO TS PN",
    "Liguria": "IM SV GE SP",
    "Emilia-Romagna": "PC PR RE MO BO FE RA FC RN",
    "Toscana": "MS LU PT FI LI PI AR SI GR PO",
    "Umbria": "PG TR",
    "Marche": "PU AN MC AP FM",
    "Lazio": "VT RI RM LT FR",
    "Abruzzo": "AQ TE PE CH",
    "Molise": "CB IS",
    "Campania": "CE BN NA AV SA",
    "Puglia": "FG BA TA BR LE BT",
    "Basilicata": "PZ MT",
    "Calabria": "CS CZ RC KR VV",
    "Sicilia": "TP PA ME AG CL EN CT RG SR",
    "Sardegna": "SS NU CA OR SU OT OG VS CI",
}
PROVINCIA_REGIONE = {sigla: reg for reg, sigle in _REG.items() for sigla in sigle.split()}
REGIONI = list(_REG.keys())

CARBURANTI_PREZZI = ["Benzina", "Gasolio", "GPL"]

# --------------------------------------------------------------------------------------
# Confronto tra marchi (campo "Bandiera" dell'anagrafica MIMIT)
# --------------------------------------------------------------------------------------
MARCHI = ["Q8", "Q8 Easy", "IP", "Eni", "Esso", "Tamoil", "Pompe bianche", "Altri"]
MARCHI_CONFRONTO = ("Q8", "IP")        # coppia principale del confronto
MARCHI_RIFERIMENTO = ("Eni", "Pompe bianche")


def normalizza_bandiera(testo) -> str:
    """Riconduce le diciture MIMIT (es. 'Agip Eni', 'Api-Ip', 'Q8 Easy') a un marchio standard."""
    import re
    t = str(testo or "").strip().lower()
    if "q8" in t or "kuwait" in t:
        return "Q8 Easy" if "easy" in t else "Q8"
    if re.search(r"\b(ip|api)\b", t) or "italiana petroli" in t:
        return "IP"
    if re.search(r"\beni\b", t) or "agip" in t or "enilive" in t:
        return "Eni"
    if "esso" in t:
        return "Esso"
    if "tamoil" in t:
        return "Tamoil"
    if "pompe bianche" in t or "pompa bianca" in t:
        return "Pompe bianche"
    return "Altri"


# Eventi di contesto mostrati sui grafici: (data, etichetta breve, descrizione, fonte).
# Aggiungere qui altri eventi, solo se verificati su una fonte citabile.
EVENTI = [
    ("2026-03-11", "Rincari / IP −2 cent", "Rincari dopo l'inizio del conflitto; IP raccomanda −2 cent/l",
     "L'Adige e Quotidiano.net, 11/03/2026"),
    ("2026-05-22", "Fine taglio accise", "Termine della proroga del taglio delle accise", "SicurAuto"),
    ("2026-09-05", "Fine taglio accise gasolio", "Scade il taglio accise sul gasolio (17 cent/l)",
     "Euronews, 27/08/2026"),
    ("2026-09-28", "Tetti ai prezzi", "Tetto ai prezzi Eni dal 28/09; IP annuncia il proprio, applicazione progressiva",
     "QuiFinanza, 27/09/2026"),
]
