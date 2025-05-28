# Universal Cloudflare Tunnel Manager

## A cosa serve

L'Universal Cloudflare Tunnel Manager è un'applicazione web che semplifica la creazione e gestione di tunnel Cloudflare per servizi Docker. Permette di:

- Esporre container Docker su Internet tramite tunnel Cloudflare temporanei
- Gestire la durata dei tunnel con scadenza automatica
- Visualizzare e controllare tutti i tunnel attivi tramite interfaccia web
- Mantenere configurazione persistente

## Prerequisiti

- **Docker Engine** e **Docker Compose** (per installazione Docker)
- **Python 3.8+** e **pip** (per installazione Python)
- Connessione Internet
- Sistema Linux (raccomandato)

## Installazione

### Opzione 1: Python Virtual Environment

1. **Clona il repository:**
   ```bash
   git clone <URL_REPOSITORY>
   cd interface
   ```

2. **Crea e attiva virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/Mac
   # oppure: venv\Scripts\activate  # Windows
   ```

3. **Installa dipendenze:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Installa cloudflared:**
   ```bash
   # Linux
   wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
   chmod +x cloudflared-linux-amd64
   sudo mv cloudflared-linux-amd64 /usr/local/bin/cloudflared
   ```

5. **Avvia l'applicazione:**
   ```bash
   python app.py
   ```

### Opzione 2: Docker Compose

1. **Clona il repository:**
   ```bash
   git clone <URL_REPOSITORY>
   cd interface
   ```

2. **Avvia con Docker Compose:**
   ```bash
   docker-compose up --build -d
   ```

3. **Verifica i log:**
   ```bash
   docker-compose logs -f
   ```

## Utilizzo

1. **Accedi all'interfaccia web:**
   - Vai su `http://localhost:5001`

2. **Gestione tunnel:**
   - **Avvia tunnel:** Seleziona porta e durata, clicca "Avvia Tunnel"
   - **Estendi tunnel:** Inserisci nuova durata e clicca "Estendi"
   - **Ferma tunnel:** Clicca "Ferma" per singoli tunnel o "Ferma Tutti"

## Gestione Docker

```bash
# Visualizza log
docker-compose logs -f

# Ferma applicazione
docker-compose down

# Riavvia
docker-compose restart

# Rimuovi dati persistenti
docker-compose down -v
```

## Struttura Progetto

```
interface/
├── app.py                 # Applicazione Flask principale
├── Dockerfile            # Configurazione container
├── docker-compose.yml    # Orchestrazione Docker
├── requirements.txt      # Dipendenze Python
├── templates/
│   └── universal.html    # Interfaccia web
└── static/
    └── style.css         # Stili CSS
```

## Risoluzione Problemi

- **URL non appare:** Controlla log per errori cloudflared e connettività Internet
- **Nessun servizio Docker:** Verifica mount di `/var/run/docker.sock` e container attivi
- **Problemi permessi:** Aggiungi utente al gruppo docker: `sudo usermod -aG docker $USER`

## Licenza

Questo progetto è rilasciato sotto licenza **GNU General Public License v3.0 (GPL-3.0)**.

Vedi il file LICENSE per i dettagli completi. In sintesi:
- Puoi usare, modificare e distribuire questo software
- Devi mantenere la stessa licenza per opere derivate
- Devi fornire il codice sorgente se distribuisci il software

---

Per supporto e contributi, consulta la documentazione del progetto.
