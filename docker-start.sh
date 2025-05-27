#!/bin/bash

echo "🐳 Universal Tunnel Manager - Docker Setup"
echo "=========================================="

# Controlli preliminari
echo "🔍 Controlli preliminari..."

# Controlla se Docker è in esecuzione
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker non è in esecuzione. Avvia Docker e riprova."
    exit 1
fi

# Controlla se docker-compose è installato
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose non trovato. Installalo con:"
    echo "   sudo apt install docker-compose"
    exit 1
fi

echo "✅ Docker e docker-compose pronti"

# Chiede quale modalità usare
echo ""
echo "Seleziona modalità di avvio:"
echo "1) 🏠 Locale (solo Universal Tunnel Manager)"
echo "2) 🌐 Integrato (con servizi esistenti in /home/nugh75/docker)"
echo ""
read -p "Scegli (1 o 2): " choice

case $choice in
    1)
        echo "🏠 Modalità Locale selezionata"
        COMPOSE_FILE="docker-compose.yml"
        LOCATION="/home/nugh75/Git/interface"
        ;;
    2)
        echo "🌐 Modalità Integrata selezionata"
        COMPOSE_FILE="docker-compose.tunnel-manager.yml"
        LOCATION="/home/nugh75/docker"
        ;;
    *)
        echo "❌ Selezione non valida"
        exit 1
        ;;
esac

echo ""
echo "📂 Cambiando directory in: $LOCATION"
cd "$LOCATION" || exit 1

echo "🔨 Building e avvio dei container..."
docker-compose -f "$COMPOSE_FILE" up -d --build

echo ""
echo "🎉 Universal Tunnel Manager avviato!"
echo ""
echo "📱 Interfaccia web: http://localhost:5001"
echo "🔧 API Status: http://localhost:5001/api/status"
echo "🐛 Debug: http://localhost:5001/api/debug"
echo ""
echo "📋 Comandi utili:"
echo "   🔍 Logs: docker-compose -f $COMPOSE_FILE logs -f universal-tunnel-manager"
echo "   ⏹️  Stop: docker-compose -f $COMPOSE_FILE down"
echo "   🔄 Restart: docker-compose -f $COMPOSE_FILE restart universal-tunnel-manager"
echo ""

# Attende che il servizio sia pronto
echo "⏳ Attendendo che il servizio sia pronto..."
for i in {1..30}; do
    if curl -s http://localhost:5001/api/status >/dev/null 2>&1; then
        echo "✅ Servizio pronto!"
        break
    fi
    sleep 2
    echo -n "."
done

echo ""
echo "🚀 Setup completato! Buon uso del Universal Tunnel Manager!"
