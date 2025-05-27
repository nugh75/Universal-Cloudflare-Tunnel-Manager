#!/bin/bash
# cloudflared-logs.sh
# Script per visualizzare i log di cloudflared dal container Docker

echo "📋 Visualizzazione Log Cloudflared"
echo "================================="

# Verifica che il container sia in esecuzione
if ! docker ps | grep -q universal-tunnel-manager; then
    echo "❌ Container universal-tunnel-manager non in esecuzione."
    echo "   Avvia prima il container con docker-compose -f docker-compose.tunnel-manager.yml up -d"
    exit 1
fi

# Verifica se il file di log esiste
LOG_FILE="/app/data/cloudflared.log"

if ! docker exec universal-tunnel-manager test -f "$LOG_FILE" 2>/dev/null; then
    echo "❌ File di log $LOG_FILE non trovato nel container."
    echo "   Avvia prima un tunnel per generare il file di log."
    exit 1
fi

# Visualizza i log con opzioni
case "$1" in
    --tail)
        echo "📡 Visualizzazione log in tempo reale (premi Ctrl+C per uscire)..."
        docker exec universal-tunnel-manager tail -f "$LOG_FILE"
        ;;
    --head)
        echo "📡 Prime 20 righe del log:"
        docker exec universal-tunnel-manager head -n 20 "$LOG_FILE"
        ;;
    --last)
        LINES=${2:-50}
        echo "📡 Ultime $LINES righe del log:"
        docker exec universal-tunnel-manager tail -n "$LINES" "$LOG_FILE"
        ;;
    --grep)
        if [ -z "$2" ]; then
            echo "❌ Specifica un pattern di ricerca: ./cloudflared-logs.sh --grep PATTERN"
            exit 1
        fi
        echo "📡 Righe del log contenenti '$2':"
        docker exec universal-tunnel-manager grep "$2" "$LOG_FILE"
        ;;
    *)
        echo "📡 Visualizzazione completa del log:"
        docker exec universal-tunnel-manager cat "$LOG_FILE"
        ;;
esac

echo "✅ Operazione completata."
