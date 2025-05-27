# Universal Cloudflare Tunnel Manager

## Panoramica

L'Universal Cloudflare Tunnel Manager è un'applicazione web progettata per semplificare la creazione e la gestione di tunnel Cloudflare ("quick tunnels") per qualsiasi servizio Docker in esecuzione sul tuo host Linux. Fornisce un'interfaccia utente web intuitiva per:

*   Visualizzare tutti i container Docker attivi.
*   Avviare tunnel Cloudflare per i container selezionati, esponendoli su Internet tramite un URL `trycloudflare.com`.
*   Specificare una durata per i tunnel, con scadenza automatica (default: 48 ore).
*   Estendere la durata dei tunnel attivi.
*   Fermare singoli tunnel o tutti i tunnel contemporaneamente.
*   Mantenere una configurazione persistente dei tunnel (URL, porta, scadenza) anche dopo il riavvio dell'applicazione manager.

L'applicazione è containerizzata utilizzando Docker e orchestrata con Docker Compose per una facile installazione e gestione.

## Funzionalità Principali

*   **Interfaccia Web Semplice:** Gestisci i tunnel tramite un'interfaccia utente web moderna e reattiva.
*   **Rilevamento Automatico Servizi Docker:** Elenca automaticamente tutti i container Docker attivi e le loro porte esposte.
*   **Creazione Tunnel Cloudflare:** Avvia "quick tunnels" Cloudflare con un clic.
*   **Durata Tunnel Configurabile:** Imposta una durata specifica (in ore) per ogni tunnel, con un default di 48 ore.
*   **Scadenza Automatica:** I tunnel si chiudono automaticamente alla loro scadenza.
*   **Estensione Durata:** Prolunga la vita dei tunnel attivi.
*   **Gestione Centralizzata:** Ferma singoli tunnel o tutti insieme.
*   **Persistenza Configurazione:** Salva le informazioni sui tunnel (URL, porta, scadenza) in un file JSON, che viene ricaricato all'avvio.
*   **Accesso tramite Docker Socket:** Comunica con il demone Docker dell'host per ottenere informazioni sui container.
*   **Log Dettagliati:** Fornisce log per il debug e il monitoraggio delle operazioni.

## Prerequisiti (per l'Host Linux)

1.  **Docker Engine:** Devi avere Docker installato e in esecuzione sul tuo sistema Linux.
    *   Segui la [guida ufficiale di installazione Docker](https://docs.docker.com/engine/install/ubuntu/) (o la guida per la tua distribuzione Linux).
    *   Assicurati che l'utente che eseguirà i comandi Docker sia nel gruppo `docker` (o esegui i comandi con `sudo`):
        ```bash
        sudo usermod -aG docker $USER
        # Potrebbe essere necessario un logout/login o 'newgrp docker'
        ```

2.  **Docker Compose:** Devi avere Docker Compose (V2 o la versione plugin `docker compose`) installato.
    *   Se hai una versione recente di Docker Engine, il plugin `docker compose` potrebbe essere già incluso. Prova `docker compose version`.
    *   Altrimenti, segui la [guida ufficiale di installazione Docker Compose](https://docs.docker.com/compose/install/).

3.  **Git (Opzionale):** Se vuoi clonare questo repository.

## Installazione e Avvio

1.  **Clona il Repository (o Scarica i File):**
    Se hai il progetto in un repository Git:
    ```bash
    git clone <URL_DEL_TUO_REPOSITORY>
    cd <NOME_DELLA_CARTELLA_DEL_PROGETTO>
    ```
    Altrimenti, assicurati di avere tutti i file necessari (`app.py`, `Dockerfile`, `docker-compose.yml`, `requirements.txt`, e le cartelle `templates/` e `static/`) in una directory di progetto.

2.  **Naviga nella Directory del Progetto:**
    Apri un terminale e spostati nella directory principale del progetto dove si trovano `Dockerfile` e `docker-compose.yml`.
    ```bash
    cd /percorso/del/tuo/progetto/
    ```

3.  **(Opzionale) Pulizia di Esecuzioni Precedenti:**
    Se hai eseguito versioni precedenti di questa applicazione e vuoi partire da zero (cancellando i dati dei tunnel salvati):
    ```bash
    docker-compose down -v
    ```
    *   `-v` rimuove i volumi nominati, inclusi i dati di configurazione persistenti. Ometti `-v` se vuoi mantenere la configurazione precedente.

4.  **Costruisci l'Immagine Docker e Avvia l'Applicazione:**
    Questo comando costruirà l'immagine Docker (se non esiste o se `--build` è specificato) e avvierà il container in background (modalità detached).
    ```bash
    docker-compose up --build -d
    ```
    *   `--build`: Forza la ricostruzione dell'immagine. Utile la prima volta o se hai modificato `Dockerfile` o i file sorgente dell'applicazione.
    *   `-d`: Esegue i container in background.

5.  **Verifica l'Avvio:**
    Controlla i log per assicurarti che l'applicazione sia partita correttamente:
    ```bash
    docker-compose logs -f
    ```
    Dovresti vedere output da Flask che indica che il server è in ascolto sulla porta 5001. Premi `Ctrl+C` per uscire dalla visualizzazione dei log.

## Utilizzo

1.  **Accedi all'Interfaccia Web:**
    Apri il tuo browser web e naviga a:
    `http://localhost:5001`
    (Se stai accedendo da un'altra macchina sulla stessa rete, sostituisci `localhost` con l'indirizzo IP della macchina Linux che ospita Docker).

2.  **Funzionalità dell'Interfaccia:**
    *   **Elenco Servizi Docker:** La pagina principale mostra una lista di tutti i container Docker attivi sul tuo host. Per ogni servizio, vedrai nome, immagine, stato e porte mappate.
    *   **Avviare un Tunnel:**
        *   Seleziona la **Porta** del container che vuoi esporre.
        *   (Opzionale) Inserisci una **Durata (ore)** per il tunnel. Se lasciato vuoto, verrà usata la durata di default (es. 48 ore).
        *   Clicca su **"Avvia Tunnel"**.
        *   L'interfaccia mostrerà "Ricerca URL in corso...". Dopo alcuni secondi, l'URL `trycloudflare.com` dovrebbe apparire.
    *   **Estendere un Tunnel Attivo:**
        *   Per un tunnel già attivo, puoi inserire una nuova durata (in ore) nel campo "Estendi (ore)".
        *   Clicca su **"Estendi"**. La scadenza del tunnel verrà aggiornata.
    *   **Visualizzare URL e Scadenza:** Per i tunnel attivi, vedrai l'URL pubblico e il tempo rimanente prima della scadenza.
    *   **Fermare un Tunnel:** Clicca sul pulsante **"Ferma"** accanto al tunnel che vuoi chiudere.
    *   **Azioni Globali:**
        *   **"Ferma Tutti i Tunnel"**: Chiude tutti i tunnel Cloudflare attivi gestiti dall'applicazione.
        *   **"Aggiorna Stato"**: Ricarica la lista dei servizi Docker e lo stato dei tunnel.
    *   **Informazioni:** In alto, vedrai l'IP locale rilevato dall'applicazione (che `cloudflared` userà per puntare ai servizi) e la durata di default dei tunnel.

## Gestione dell'Applicazione Docker

*   **Vedere i Log in Tempo Reale:**
    ```bash
    docker-compose logs -f
    ```
    Oppure, specificando il nome del servizio (definito nel `docker-compose.yml`):
    ```bash
    docker-compose logs -f tunnel-manager
    ```

*   **Fermare l'Applicazione:**
    Questo ferma i container ma non rimuove i dati persistenti nel volume.
    ```bash
    docker-compose down
    ```

*   **Fermare l'Applicazione e Rimuovere i Dati Persistenti:**
    ```bash
    docker-compose down -v
    ```

*   **Riavviare l'Applicazione:**
    ```bash
    docker-compose restart tunnel-manager
    ```
    Oppure:
    ```bash
    docker-compose down && docker-compose up -d
    ```

*   **Ricostruire l'Immagine (se hai modificato il codice sorgente o `Dockerfile`):**
    ```bash
    docker-compose build tunnel-manager
    ```
    E poi riavvia:
    ```bash
    docker-compose up -d --force-recreate tunnel-manager
    ```
    Oppure, più semplicemente:
    ```bash
    docker-compose up --build -d
    ```

## Configurazione Persistente

L'applicazione salva le informazioni sui tunnel attivi (URL, porta selezionata, ora di avvio, ora di scadenza) nel file `/app/data/tunnel_config.json` all'interno del container. Grazie al volume Docker definito in `docker-compose.yml` (`tunnel_manager_app_data_volume`), questa directory `/app/data` è persistente.

Questo significa che se fermi e riavvii il container `tunnel-manager`, l'applicazione ricaricherà la configurazione precedente. I processi `cloudflared` non verranno riavviati automaticamente (essendo "quick tunnels"), ma l'interfaccia ricorderà gli URL e le scadenze precedenti.

## Risoluzione dei Problemi

*   **L'URL di Cloudflare non appare:**
    1.  Controlla i log del container `tunnel-manager` (`docker-compose logs -f tunnel-manager`). Cerca messaggi relativi a `cloudflared`, errori di connessione, o fallimenti nella cattura dell'URL.
    2.  Verifica la console del browser per eventuali errori JavaScript.
    3.  Assicurati che la macchina host abbia connettività Internet e possa raggiungere i server di Cloudflare.
    4.  Verifica che `cloudflared` sia installato correttamente nel container (il Dockerfile dovrebbe gestirlo).
*   **Nessun servizio Docker elencato:**
    1.  Assicurati che il socket Docker (`/var/run/docker.sock`) sia correttamente montato nel container (come definito nel `docker-compose.yml`).
    2.  Verifica che ci siano container Docker effettivamente in esecuzione (`docker ps` sull'host).
    3.  Controlla i log del container `tunnel-manager` per errori relativi alla comunicazione con il demone Docker.
*   **Problemi di Permesso con `docker.sock`:**
    Se l'utente Docker non ha i permessi corretti, potresti vedere errori. Assicurati che l'utente host che esegue i comandi `docker-compose` possa accedere al demone Docker, o che il demone Docker sia configurato per accettare connessioni dal socket come previsto.

## Struttura del Progetto

our-project-root/
├── app.py # Script principale Flask
├── Dockerfile # Istruzioni per costruire l'immagine Docker
├── docker-compose.yml # Definizione del servizio Docker Compose
├── requirements.txt # Dipendenze Python
├── templates/
│ └── universal.html # Template HTML per l'interfaccia
└── static/
└── style.css # Fogli di stile CSS

      
## Licenza

Gpl3

    
