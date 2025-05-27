#!/bin/bash
# test-docker-cloudflare.sh
# Script per testare il setup Docker e la funzionalità di tunnel Cloudflare

echo "🧪 Test Docker e Tunnel Cloudflare"
echo "=================================="

# Definisci colori per l'output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Funzione per i messaggi di successo
success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# Funzione per i messaggi di errore
error() {
    echo -e "${RED}❌ $1${NC}"
}

# Funzione per i messaggi di avviso
warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

# Verifica la presenza di Docker
if ! command -v docker &> /dev/null; then
    error "Docker non è installato. Installa Docker prima di procedere."
    exit 1
fi
success "Docker è installato"

# Verifica che docker-compose sia installato
if ! command -v docker-compose &> /dev/null; then
    error "docker-compose non è installato. Installalo prima di procedere."
    exit 1
fi
success "docker-compose è installato"

# Verifica accesso a socket Docker
if [ ! -S /var/run/docker.sock ]; then
    error "Socket Docker non accessibile: /var/run/docker.sock"
    exit 1
fi
success "Socket Docker accessibile"

# Verifica permessi sul socket Docker
if [ ! -r /var/run/docker.sock ]; then
    error "L'utente corrente non ha permessi di lettura sul socket Docker"
    exit 1
fi
success "Permessi di lettura sul socket Docker: OK"

# Ottieni l'IP dell'host Docker
echo -e "\n🔍 Rilevamento IP locale..."
HOSTNAME_IP=$(hostname -I | awk '{print $1}')
BRIDGE_IP="172.17.0.1"
echo "📡 IP Hostname: $HOSTNAME_IP"
echo "📡 IP Bridge predefinito: $BRIDGE_IP"

# Verifica cloudflared
if ! command -v cloudflared &> /dev/null; then
    warning "cloudflared non è installato localmente, ma verrà usato nel container Docker"
else
    success "cloudflared è installato localmente: $(cloudflared --version | head -n 1)"
fi

# Costruisci l'immagine Docker
echo -e "\n🔨 Costruzione immagine Docker..."
docker-compose -f docker-compose.tunnel-manager.yml build
if [ $? -ne 0 ]; then
    error "Errore nella costruzione dell'immagine Docker"
    exit 1
fi
success "Immagine Docker costruita con successo"

# Esegui il container in modalità detached
echo -e "\n🚀 Avvio container..."
docker-compose -f docker-compose.tunnel-manager.yml up -d
if [ $? -ne 0 ]; then
    error "Errore nell'avvio del container"
    exit 1
fi
success "Container avviato con successo"

# Aspetta che il servizio sia pronto
echo -e "\n⏳ Attesa avvio servizio..."
sleep 5

# Verifica che il servizio sia in esecuzione
if ! curl -s http://localhost:5001 > /dev/null; then
    error "Il servizio non risponde su http://localhost:5001"
    docker-compose -f docker-compose.tunnel-manager.yml down
    exit 1
fi
success "Servizio Universal Tunnel Manager raggiungibile su http://localhost:5001"

# Test dell'API per verificare che sia operativa
echo -e "\n🔍 Test API di stato..."
STATUS=$(curl -s http://localhost:5001/api/status)
if [ $? -ne 0 ]; then
    error "Errore nella chiamata API di stato"
else
    success "API di stato funzionante"
    echo "$STATUS" | grep -q "services"
    if [ $? -eq 0 ]; then
        success "API restituisce dati corretti sui servizi"
    else
        warning "L'API non contiene dati sui servizi. Verifica che Docker sia correttamente configurato."
    fi
fi

# Test dell'API di debug
echo -e "\n🔍 Test API di debug..."
DEBUG=$(curl -s http://localhost:5001/api/debug)
if [ $? -ne 0 ]; then
    error "Errore nella chiamata API di debug"
else
    success "API di debug funzionante"
    echo "$DEBUG" | grep -q "docker_containers"
    if [ $? -eq 0 ]; then
        success "API restituisce dati corretti sui container Docker"
    else
        warning "L'API non contiene dati sui container Docker. Verifica la configurazione."
    fi
fi

# Mostra i log del container per diagnosi
echo -e "\n📋 Log del container:"
docker-compose -f docker-compose.tunnel-manager.yml logs

echo -e "\n✨ Test completato. Servizio in esecuzione su http://localhost:5001"
echo "Per fermare il servizio, esegui: docker-compose -f docker-compose.tunnel-manager.yml down"
