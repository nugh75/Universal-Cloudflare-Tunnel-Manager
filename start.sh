#!/bin/bash

echo "🚀 Tunnel Manager per Open WebUI"
echo "================================"

# Controlla se siamo nella directory corretta
if [[ ! -d "venv" ]]; then
    echo "❌ Ambiente virtuale non trovato. Assicurati di essere nella directory corretta."
    exit 1
fi

# Attiva l'ambiente virtuale
echo "📦 Attivazione ambiente virtuale..."
source venv/bin/activate

# Controlla se cloudflared è installato
if ! command -v cloudflared &> /dev/null; then
    echo "⚠️  cloudflared non trovato. Per installarlo:"
    echo "   - Vai su: https://github.com/cloudflare/cloudflared/releases"
    echo "   - Oppure usa: sudo apt install cloudflared (Ubuntu/Debian)"
    echo ""
    echo "🔄 Continuo comunque con l'avvio dell'interfaccia..."
fi

echo "🌐 Avvio interfaccia web universale..."
echo "📱 Aprirà su: http://localhost:5001"
echo ""
echo "💡 Per fermare: Ctrl+C"
echo ""

python tunnel_manager.py
