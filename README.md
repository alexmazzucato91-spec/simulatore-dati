# Postino dati – Simulatore Bolletta

Ogni mese, dal 2 al 10, questo programma gira da solo su GitHub (gratis) e:
1. legge **PUN** (monorario, F1, F2, F3) e **PSV** del mese appena chiuso da due fonti che pubblicano i dati ufficiali GME/ARERA (A2A e Must Energia);
2. li confronta: se differiscono più dell'1% **non** li inserisce;
3. aggiorna `indici.json`.

Il Simulatore, quando lo apri con internet, legge `indici.json` e aggiunge da solo i mesi nuovi. Senza internet usa i dati che ha già.

## Installazione (una volta sola, circa 10 minuti)

1. Crea un account gratuito su **github.com**.
2. In alto a destra **+ → New repository**. Nome: `simulatore-dati`, scegli **Public**, premi **Create repository**.
3. Nella pagina del repository premi **uploading an existing file** e trascina i file `indici.json`, `README.md` e la cartella `postino` (con dentro `aggiorna.py`). Premi **Commit changes**.
4. Crea il file che fa partire il postino: **Add file → Create new file**. Come nome scrivi esattamente
   `.github/workflows/postino.yml`
   e incolla dentro il contenuto del file `postino.yml` che trovi nella cartella `.github/workflows` di questo pacchetto. Premi **Commit changes**.
5. **Settings → Actions → General → Workflow permissions**: scegli **Read and write permissions** e premi **Save**.
6. Scheda **Actions** → a sinistra **Postino indici PUN PSV** → **Run workflow** → **Run workflow**. Dopo un minuto deve comparire la spunta verde.
7. Torna su **Code**, apri `indici.json`, premi **Raw** e copia l'indirizzo della pagina (inizia con `https://raw.githubusercontent.com/...`).
8. Nel Simulatore: **Indici PUN/PSV → Aggiornamento automatico → incolla l'indirizzo → Salva e prova**. Poi **Scarica simulatore aggiornato** e metti il nuovo file sul Drive: anche l'altro PC si aggiornerà da solo.

## Cosa succede se qualcosa non va
- Se una fonte cambia sito o non risponde, GitHub ti manda una **email "Run failed"**. Il simulatore continua a funzionare: inserisci il mese a mano da **Indici PUN/PSV** (5 numeri, link alle fonti nel modulo).
- Se le due fonti non concordano il mese non viene inserito: lo vedi nel log dell'esecuzione (scheda Actions).
- GitHub sospende i lavori programmati dopo 60 giorni senza modifiche al repository: non succede, perché il postino salva ogni mese i dati nuovi. Se capitasse, Actions → **Enable workflow**.

## Fonti
- PUN Index GME mensile per fasce: https://www.a2a.it/assistenza/tutela-cliente/indici/indice-pun · https://www.mustenergia.it/indice-pun-dati-e-tariffe-andamento-del-prezzo-luce/ (fonte originale: GME, mercatoelettrico.org)
- PSV day ahead mensile (€/Smc): https://www.a2a.it/assistenza/tutela-cliente/indici/indice-psv · https://www.mustenergia.it/indice-psv/
