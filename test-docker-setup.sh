#!/bin/bash
# Script per testare il setup Docker del Universal Tunnel Manager

echo "🧪 Test Setup Docker Universal Tunnel Manager"
echo "============================================="

# Colori per l'output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Funzione per stampare il risultato di un test
test_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ SUCCESSO${NC}: $2"
    else
        echo -e "${RED}✗ FALLITO${NC}: $2"
        echo -e "${YELLOW}Suggerimento${NC}: $3"
    fi
    echo ""
}

echo "🔍 Verificando prerequisiti..."

# Verifica Docker
docker --version >/dev/null 2>&1
test_result $? "Docker è installato" "Installa Docker: https://docs.docker.com/get-docker/"

# Verifica Docker Compose
docker-compose --version >/dev/null 2>&1
test_result $? "Docker Compose è installato" "Installa Docker Compose: https://docs.docker.com/compose/install/"

# Verifica esistenza dei file necessari
echo "🔍 Verificando file di configurazione..."

files_to_check=(
    "Dockerfile"
    "docker-compose.yml"
    "docker-compose.tunnel-manager.yml"
    "docker-start.sh"
    "start-container.sh"
    "data-manager.sh"
    "tunnel_manager.py"
    "requirements.txt"
)

all_files_exist=0
for file in "${files_to_check[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file"
        all_files_exist=1
    fi
done

test_result $all_files_exist "Tutti i file di configurazione esistono" "Controlla di essere nella directory corretta o di aver creato tutti i file"

# Test di build dell'immagine
echo "🔨 Test build immagine Docker..."
docker build -t universal-tunnel-manager:test . >/dev/null 2>&1
test_result $? "Build dell'immagine Docker" "Controlla il Dockerfile per errori di sintassi o comandi non validi"

# Test creazione container
echo "📦 Test creazione container..."
docker run --name test-tunnel-manager -d --rm -p 5001:5001 universal-tunnel-manager:test >/dev/null 2>&1
container_test=$?
test_result $container_test "Creazione container" "Controlla i log con: docker logs test-tunnel-manager"

# Se il container è stato creato, esegui altri test
if [ $container_test -eq 0 ]; then
    # Aspetta che il container sia pronto
    echo "⏳ Attesa avvio container (5 secondi)..."
    sleep 5
    
    # Test connessione
    echo "🔌 Test connessione al container..."
    curl -s http://localhost:5001/api/status >/dev/null 2>&1
    test_result $? "Connessione all'API del container" "Controlla che l'applicazione sia in ascolto sulla porta 5001"
    
    # Ferma e rimuovi il container di test
    echo "🧹 Pulizia container di test..."
    docker stop test-tunnel-manager >/dev/null 2>&1
fi

# Pulizia immagine di test
docker rmi universal-tunnel-manager:test >/dev/null 2>&1

echo "============================================="
echo "🏁 Test completati. Ora puoi avviare l'applicazione con:"
echo "./docker-start.sh"
