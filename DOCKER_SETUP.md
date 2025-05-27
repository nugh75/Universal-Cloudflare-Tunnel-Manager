# 📝 Documentazione Setup Docker: Universal Tunnel Manager

## 📋 Panoramica

Questa documentazione descrive il setup Docker completo per l'Universal Tunnel Manager, un'applicazione che permette di creare tunnel Cloudflare per qualsiasi servizio Docker in esecuzione sul sistema.

## 🏗️ Architettura

### 🧩 Componenti principali:

1. **Applicazione Python Flask** - Gestisce la logica dell'applicazione e l'interfaccia web
2. **Cloudflared** - Crea tunnel sicuri verso Internet
3. **Docker CLI** - Comunica con il Docker daemon dell'host
4. **Container Docker** - Isola l'applicazione e le sue dipendenze

### 📊 Diagramma

```
┌────────────────────────┐
│     Container Docker   │
│  ┌──────────────────┐  │
│  │ Python Flask App │  │
│  └──────────────────┘  │
│  ┌──────────────────┐  │
│  │   Cloudflared    │  │
│  └──────────────────┘  │
│  ┌──────────────────┐  │
│  │    Docker CLI    │──┼────► /var/run/docker.sock
│  └──────────────────┘  │     (Docker Host)
└────────────────────────┘
           │
           ▼
┌────────────────────────┐
│   Servizi Docker Host  │
│  ┌──────────────────┐  │
│  │   Container 1    │  │
│  └──────────────────┘  │
│  ┌──────────────────┐  │
│  │   Container 2    │  │
│  └──────────────────┘  │
│  ┌──────────────────┐  │
│  │   Container N    │  │
│  └──────────────────┘  │
└────────────────────────┘
```

## 🛠️ Struttura del Progetto

```
interface/
├── Dockerfile                  # Build immagine Docker
├── docker-compose.yml          # Configurazione standalone
├── docker-compose.tunnel-manager.yml  # Config. integrata
├── docker-start.sh             # Script di avvio
├── start-container.sh          # Script interno container
├── data-manager.sh             # Gestione dati persistenti
├── tunnel_manager.py           # Applicazione Python Flask
├── requirements.txt            # Dipendenze Python
├── test-docker-setup.sh        # Script di test
├── README.md                   # Documentazione utente
└── data/                       # Directory per dati persistenti
    └── tunnel_config.json      # Configurazione salvata
└── templates/                  # Template HTML
    └── universal.html          # Interfaccia web
```

## 🔄 Flusso di Esecuzione

1. **Build dell'immagine**:
   - Python 3.11 slim
   - Installazione dipendenze di sistema
   - Installazione Docker CLI
   - Installazione cloudflared
   - Copia del codice applicativo
   - Configurazione utente non-root

2. **Avvio del container**:
   - Scelta tra modalità locale o integrata via `docker-start.sh`
   - Montaggio del socket Docker e volume dati
   - Esecuzione del container con le configurazioni scelte

3. **Esecuzione dell'applicazione**:
   - `start-container.sh` inizializza l'ambiente nel container
   - Avvio applicazione Flask su porta 5001
   - Rilevamento servizi Docker attivi
   - Interfaccia web per la gestione dei tunnel

## 🔒 Sicurezza

### Misure implementate:

1. **Container non-root**: Esecuzione con utente `tunneluser` (UID 1000)
2. **Socket Docker in sola lettura**: Accesso limitato al Docker host
3. **Tunnel temporanei**: I tunnel Cloudflare esistono solo durante l'esecuzione
4. **Healthcheck**: Monitoraggio dello stato dell'applicazione
5. **Immagine minimale**: Utilizzo di immagine Python slim per ridurre la superficie d'attacco

### Considerazioni:

- Il montaggio del socket Docker concede privilegi elevati al container
- Tutti i servizi rilevati sono esposti all'applicazione

## 📊 Persistenza Dati

I dati vengono persistiti attraverso:

1. **Volume Docker** montato in `/app/data`
2. **File di configurazione JSON** per salvare dettagli sui tunnel
3. **Script data-manager.sh** per gestire backup e ripristino

## 🌐 Networking

- **Porta esposta**: 5001 (TCP)
- **Rete bridge**: `tunnel-network` (modalità locale) o rete esistente (modalità integrata)
- **Comunicazione con Docker host**: Via socket Docker
- **Tunneling Cloudflare**: Da container verso internet

## 🧪 Test

Lo script `test-docker-setup.sh` verifica:

1. Prerequisiti (Docker, Docker Compose)
2. Presenza di tutti i file necessari
3. Build dell'immagine Docker
4. Creazione e avvio del container
5. Connessione all'API dell'applicazione

## 🔍 Troubleshooting

### Problemi comuni:

1. **Container non si avvia**:
   - Verifica i log: `docker logs universal-tunnel-manager`
   - Controlla permessi del socket Docker

2. **Tunnel non funzionano**:
   - Verifica connessione internet nel container
   - Controlla che cloudflared sia installato correttamente
   - Verifica l'output di cloudflared con `docker exec universal-tunnel-manager cloudflared --version`
   - Controlla i log specifici con `./cloudflared-logs.sh --tail`

3. **I tunnel non generano URL esterni**:
   - Verifica che l'IP locale sia corretto con `docker exec universal-tunnel-manager env | grep LOCAL_IP`
   - Controlla che il traffico in uscita non sia bloccato da firewall
   - Esamina i log di debug con `./cloudflared-logs.sh --grep https`
   - Prova a riavviare il servizio con `docker-compose -f docker-compose.tunnel-manager.yml restart`
   - Prova a specificare manualmente l'IP locale nel docker-compose.yml
   - Controlla che abbiano porte esposte
   - Verifica accesso al socket Docker

4. **Persistenza dati non funziona**:
   - Controlla permessi directory `data/`
   - Verifica configurazione volumi in docker-compose

## 🚀 Miglioramenti Futuri

1. **Docker Compose con multi-servizi**: Integrazione con altri servizi correlati
2. **Autenticazione**: Aggiunta di un layer di sicurezza per l'accesso
3. **Supporto reverse proxy**: Integrazione con Traefik o Nginx
4. **Monitoraggio avanzato**: Metrics per Prometheus
5. **Modalità cluster**: Supporto per ambienti Docker Swarm o Kubernetes

## 📚 Riferimenti

- [Docker Documentation](https://docs.docker.com/)
- [Cloudflare Tunnel Documentation](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [Python Docker Hub](https://hub.docker.com/_/python)
