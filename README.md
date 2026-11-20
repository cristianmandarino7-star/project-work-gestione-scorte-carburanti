# Previsione della domanda e pianificazione delle scorte – rete carburanti

Project Work n. 24 – CdS Informatica per le Aziende Digitali (L-31).
Mini-dashboard in Python (Streamlit + Plotly) per prevedere la domanda di quattro articoli
di un deposito carburanti, confrontare i metodi previsionali e stimare le scorte
cicliche, di sicurezza, anticipate e pipeline in diversi scenari.

- **Impresa:** Kuwait Petroleum Italia S.p.A. (marchio Q8) – deposito che rifornisce la rete stradale in Calabria
- **Storico:** gennaio 2025 – settembre 2026 (mensile)
- **Previsione:** ottobre – dicembre 2026 (Q4) e 12 mesi per la scorta anticipata

## Avvio rapido (Windows)

Doppio clic su `installa.bat` (crea l'ambiente virtuale `.venv` e installa le librerie), poi su `avvia_dashboard.bat`.

## Avvio rapido (manuale)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    |   Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Si apre il browser su http://localhost:8501.

## Dati

| File | Contenuto | Origine |
|---|---|---|
| `data/domanda_mensile.csv` | domanda mensile (migliaia di litri) di Benzina, Gasolio, AdBlue, GPL | generata con `scripts/genera_dati_demo.py` (parametri in `src/config.py`) |
| `data/prezzi_regionali_mensili_demo.csv` | prezzi medi mensili per regione (illustrativi) | generata con lo stesso script |
| `data/prezzi_regionali_mensili_mimit.csv` | prezzi medi mensili reali per regione | **da creare** con `scripts/scarica_mimit.py` |
| `data/prezzi_marchi_giornalieri_demo.csv.gz` | prezzi giornalieri per marchio (illustrativi) | `scripts/genera_dati_demo.py` |
| `data/prezzi_marchi_giornalieri_mimit.csv` | prezzi giornalieri reali per marchio, regione e carburante | **da creare** con `scripts/scarica_mimit.py`, aggiornato da `scripts/aggiorna_giornaliero.py` |
| `data/regioni_italia.geojson` | confini regionali semplificati | openpolis/geojson-italy (CC BY 4.0) |

I quattro articoli hanno andamenti volutamente diversi:

| Articolo | Andamento |
|---|---|
| Benzina | stagionale, con picco estivo |
| Gasolio | stazionario |
| AdBlue | trend crescente |
| GPL | irregolare |

### Prezzi reali MIMIT

```bash
python scripts/scarica_mimit.py            # tutti i giorni, 2025 T1 -> 2026 T3 (~1,1 GB da scaricare)
python scripts/scarica_mimit.py --ogni 7   # un giorno a settimana, molto più veloce
python scripts/aggiorna_giornaliero.py     # aggiunge il giorno corrente (da ottobre 2026 in poi)
```

Gli archivi scaricati restano in `data/raw_mimit`, quindi una seconda esecuzione non riscarica nulla.
Per cancellarli a fine elaborazione si usa `--elimina-archivi`.

Per il confronto tra marchi conviene usare tutti i giorni (senza `--ogni`), così si vedono bene
le variazioni attorno agli eventi.

Lo script scarica gli archivi trimestrali dell'[archivio MIMIT](https://www.mimit.gov.it/it/open-data/elenco-dataset/carburanti-archivio-prezzi):
anagrafica impianti e prezzo alle 8. Poi associa ogni impianto alla regione tramite la provincia e calcola
la media mensile per regione e carburante (Benzina e Gasolio self, GPL).
Quando il file `prezzi_regionali_mensili_mimit.csv` esiste, la dashboard lo usa al posto dei dati dimostrativi.

### Domanda reale (facoltativo)

Per ancorare i volumi a dati ufficiali si possono usare:
- le vendite regionali e provinciali di prodotti petroliferi pubblicate dal MASE (Bollettino petrolifero);
- i comunicati mensili UNEM sui consumi.

Basta sostituire `data/domanda_mensile.csv`, mantenendo le colonne `mese,articolo,quantita`.

## Confronto tra marchi

La scheda "Confronto marchi" confronta due marchi a scelta (A e B, per default Q8 e IP), con altri marchi come riferimento.
- **Prezzi giornalieri** per marchio, con gli eventi di contesto segnati sul grafico.
- **Differenziale A − B** settimana per settimana e per regione.
- **Analisi "prima e dopo" un evento:** confronta la media dei giorni precedenti con quella dei giorni successivi.
- **Previsione Q4** del prezzo di ogni marchio.

Gli eventi si modificano in `src/config.py` (lista `EVENTI`).

## Struttura

```
app.py                     dashboard Streamlit
src/config.py              impresa, articoli, parametri, mappatura province -> regioni
src/forecasting.py         metodi previsionali, backtest, indicatori di errore
src/inventory.py           scorte cicliche/sicurezza/anticipate/pipeline, scenari
scripts/genera_dati_demo.py
scripts/scarica_mimit.py
scripts/aggiorna_giornaliero.py
data/
```

## Metodi

**Previsione.** Il programma confronta sei metodi:
- media mobile semplice (3 mesi);
- media mobile ponderata (pesi 3-2-1);
- attenuazione esponenziale (α ottimizzato);
- Holt;
- regressione lineare;
- stagionale moltiplicativo.

L'accuratezza si misura con un backtest a 1 passo e finestra crescente sui mesi gennaio–settembre 2026.
Gli indicatori sono MAE, MAPE, RMSE, bias e tracking signal. Per ogni articolo la dashboard sceglie
il metodo con l'indicatore selezionato più basso.

**Scorte.**

| Tipo | Formula |
|---|---|
| Ciclica | EOQ/2 |
| Sicurezza | z·√(LT·σₑ² + d²·σ_LT²), con σₑ = RMSE del metodo scelto |
| Pipeline | d·LT |
| Anticipata | accumulo prima dei mesi in cui la domanda supera la capacità d̄·(1+flessibilità) |

**Scenari.** Lo storico viene scomposto in trend × stagionalità × componente casuale.
I cursori riscalano ciascuna componente e modificano il lead time e la sua variabilità.
Gli scenari si possono salvare e confrontare nel grafico di composizione delle scorte.

## Aggiornare il codice senza perdere i dati scaricati

Gli zip delle nuove versioni non contengono `data/*_mimit.csv` né `data/raw_mimit/`.
1. Chiudere la dashboard e fare una copia di sicurezza della cartella `data`.
2. Estrarre lo zip in una cartella temporanea.
3. Copiarne il contenuto nella cartella del progetto, scegliendo "Sostituisci i file nella destinazione".

I file dei prezzi reali restano al loro posto.

## Licenze e attribuzioni

Il codice è rilasciato con licenza MIT (file `LICENSE`).
- Prezzi: contiene dati del Ministero delle Imprese e del Made in Italy, licenza IODL 2.0.
- Confini regionali: © ISTAT, elaborazione openpolis, CC BY 4.0.

Dettagli, librerie e note su marchi e dati personali in `ATTRIBUZIONI.md`.
