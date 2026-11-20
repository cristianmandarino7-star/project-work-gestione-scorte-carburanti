# Fonti, licenze e trattamento dei dati

## Dati di terzi

| Dato | Titolare | Licenza | Uso nel progetto |
|---|---|---|---|
| Prezzi praticati e anagrafica degli impianti di distribuzione carburanti | Ministero delle Imprese e del Made in Italy (MIMIT) | [IODL 2.0](https://www.dati.gov.it/iodl/2.0/) | Scaricati da `scripts/scarica_mimit.py`; nella repository solo medie aggregate per regione, marchio e mese/giorno |
| Confini amministrativi delle regioni (`data/regioni_italia.geojson`) | ISTAT, elaborazione [openpolis/geojson-italy](https://github.com/openpolis/geojson-italy) | CC BY 4.0 | Geometrie semplificate per la mappa |

Attribuzioni richieste:
- *Contiene dati del Ministero delle Imprese e del Made in Italy rilasciati con licenza IODL 2.0.*
- *Confini amministrativi © ISTAT, elaborazione openpolis, CC BY 4.0. Geometrie semplificate da questo progetto.*

## Dati generati

`data/domanda_mensile.csv` e i file `*_demo*` sono **generati** da `scripts/genera_dati_demo.py`:
- non derivano da dati riservati di alcuna impresa;
- i volumi di vendita sono ipotesi dichiarate nella relazione.

## Librerie

Le librerie non sono incluse nella repository: si installano da PyPI con `requirements.txt`.

| Libreria | Licenza |
|---|---|
| Streamlit | Apache 2.0 |
| Plotly | MIT |
| pandas | BSD 3-Clause |
| NumPy | BSD 3-Clause (modificata) |

## Marchi

I nomi Q8, IP, Eni, Esso, Tamoil e degli altri marchi sono citati solo per identificare le reti di distribuzione, così come compaiono nel campo "Bandiera" dei dati pubblici MIMIT. Il progetto:
- non usa loghi né elementi grafici dei marchi;
- non è affiliato alle società citate.

Kuwait Petroleum Italia è usata come caso di studio. Il deposito analizzato e i suoi volumi sono ipotetici.

## Dati personali

- L'anagrafica MIMIT contiene il campo "Gestore", che può riportare il nome di persone fisiche. Gli script leggono soltanto identificativo dell'impianto, provincia e bandiera; il nome del gestore, l'indirizzo e le coordinate non vengono mai salvati.
- I file prodotti contengono solo medie e conteggi aggregati per regione e marchio: da essi non si risale al singolo impianto.
- Gli archivi grezzi scaricati (`data/raw_mimit/`) sono esclusi dalla repository tramite `.gitignore`.
- Il codice non raccoglie dati degli utenti e non usa credenziali, chiavi API o servizi esterni oltre ai download pubblici del MIMIT.
