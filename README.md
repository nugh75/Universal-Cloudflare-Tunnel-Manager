# 🚇 Universal Tunnel Manager per Docker

Interfaccia web moderna per gestire tunnel Cloudflare per **tutti i servizi Docker** in esecuzione nel sistema.

![Docker](https://img.shields.io/badge/Docker-Ready-blue)
![Cloudflare](https://img.shields.io/badge/Cloudflare-Tunnel-orange)
![Python](https://img.shields.io/badge/Python-3.11-green)

## 🐳 Utilizzo con Docker

Universal Tunnel Manager è completamente dockerizzato e può essere eseguito in due modalità:

### 🏠 Modalità Locale

Esegue solo il Tunnel Manager come container standalone.

```bash
# Avvio rapido con lo script
./docker-start.sh
# Seleziona opzione 1) Locale
```

### 🌐 Modalità Integrata

Integra il Tunnel Manager con i servizi Docker esistenti in `/home/nugh75/docker`.

```bash
# Avvio rapido con lo script
./docker-start.sh
# Seleziona opzione 2) Integrata
```

### 🛠️ Costruzione manuale dell'immagine

```bash
# Build dell'immagine
docker build -t universal-tunnel-manager:latest .

# Esecuzione del container
docker run -d -p 5001:5001 -v /var/run/docker.sock:/var/run/docker.sock:ro universal-tunnel-manager:latest
```

## 📋 Prerequisiti

1. **Docker** - Installato e in esecuzione
2. **Docker Compose** - Per la gestione multi-container
3. **Accesso alla rete** - Per i tunnel Cloudflare

## 🔧 Struttura dei file

- **Dockerfile**: Configurazione per la build dell'immagine Docker
- **docker-compose.yml**: Definisce il servizio per la modalità locale
- **docker-compose.tunnel-manager.yml**: Definisce il servizio per la modalità integrata
- **docker-start.sh**: Script di avvio per scegliere la modalità
- **start-container.sh**: Script di avvio interno al container
- **data-manager.sh**: Script per gestire i dati persistenti
- **tunnel_manager.py**: Applicazione principale

## 📊 Persistenza dei dati

I dati persistenti vengono salvati nella directory `data/` che è montata come volume nel container:

```bash
# Gestione dei dati
./data-manager.sh status   # Visualizza lo stato dei dati
./data-manager.sh backup   # Esegue un backup della configurazione
./data-manager.sh restore  # Ripristina da un backup
./data-manager.sh clean    # Pulisce i dati (con conferma)
```

## 🔧 Script di Test e Debug

Il progetto include diversi script utili per testare e debuggare l'applicazione:

### 📋 Test del Setup Docker

```bash
./test-docker-setup.sh
```

Verifica che il container Docker sia correttamente configurato per accedere ai servizi.

### 🔍 Test dei Tunnel Cloudflare

```bash
./test-cloudflare-tunnel.sh
```

Esegue un test diretto di Cloudflare Tunnel per verificare che funzioni correttamente sul sistema.

### 🚀 Test Completo Docker + Cloudflare

```bash
./test-docker-cloudflare.sh
```

Esegue un test completo che verifica sia la configurazione Docker che la funzionalità dei tunnel Cloudflare.

### 📊 Visualizzazione Log Cloudflared

```bash
./cloudflared-logs.sh [opzioni]
```

Opzioni disponibili:
- `--tail`: Visualizza il log in tempo reale
- `--head`: Mostra le prime 20 righe del log
- `--last N`: Mostra le ultime N righe (default 50)
- `--grep PATTERN`: Cerca un pattern nel log

## 🎯 Funzionalità

- ✅ Avvia/ferma tunnel Cloudflare per qualsiasi servizio Docker
- ✅ Rileva automaticamente tutti i servizi Docker in esecuzione
- ✅ Genera URL pubblici per i servizi locali
- ✅ Interfaccia web moderna e responsive
- ✅ Aggiornamento stato in tempo reale
- ✅ Persistenza delle configurazioni

## 🌐 Come Usare

1. **Avvia il container**: `./docker-start.sh`
2. **Apri il browser**: http://localhost:5001
3. **Seleziona un servizio** dalla lista
4. **Clicca su "Avvia Tunnel"** per creare un tunnel
5. **Usa l'URL generato** per accedere al servizio da internet

## 🔒 Sicurezza

- Il container usa un utente non-root (eccetto in modalità integrata)
- Il socket Docker è montato in sola lettura
- I tunnel Cloudflare sono temporanei
- Configurazioni di rete isolate

## 🔍 Debug e Troubleshooting

- API di debug: http://localhost:5001/api/debug
- Logs del container: `docker logs universal-tunnel-manager`
- Stato dei servizi: http://localhost:5001/api/status

### Problema: I tunnel non generano URL esterni

Se i tunnel Cloudflare vengono avviati ma non generano URL esterni, prova queste soluzioni:

1. Verifica che il container sia in esecuzione come root:
   ```bash
   docker-compose -f docker-compose.tunnel-manager.yml ps
   ```

2. Controlla i log di cloudflared:
   ```bash
   ./cloudflared-logs.sh --tail
   ```

3. Verifica che l'IP locale sia corretto nei log:
   ```bash
   docker-compose -f docker-compose.tunnel-manager.yml logs | grep "IP locale"
   ```

4. Prova a specificare esplicitamente l'IP nella configurazione:
   ```yaml
   environment:
     - LOCAL_IP=172.17.0.1  # Modifica con l'IP corretto
   ```

5. Riavvia il container dopo le modifiche:
   ```bash
   docker-compose -f docker-compose.tunnel-manager.yml down
   docker-compose -f docker-compose.tunnel-manager.yml up -d
   ```

## 🔄 Aggiornamenti

Per aggiornare Universal Tunnel Manager:

```bash
# Pull delle ultime modifiche
git pull

# Ricostruzione e avvio
./docker-start.sh
```

## 🛠️ Personalizzazione

Puoi personalizzare il comportamento modificando le variabili d'ambiente nel docker-compose.yml:

```yaml
environment:
  - FLASK_ENV=production
  - PYTHONUNBUFFERED=1
  - LOCAL_IP=192.168.1.100  # Imposta manualmente l'IP locale
```

## 📝 Note

- L'URL del tunnel cambia ad ogni avvio
- L'interfaccia è accessibile solo dall'host locale per default
- Per accedere all'interfaccia dall'esterno, modifica le porte esposte nel docker-compose.yml

## 📚 Documentazione Docker Dettagliata

Per una guida completa sulla configurazione Docker, consulta [DOCKER_SETUP.md](DOCKER_SETUP.md).
