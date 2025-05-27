#!/bin/bash
# test-cloudflare-tunnel.sh
# Script per testare specificamente la funzionalità dei tunnel Cloudflare

echo "🧪 Test Tunnel Cloudflare"
echo "========================"

# Verifica che cloudflared sia installato
if ! command -v cloudflared &> /dev/null; then
    echo "❌ cloudflared non è installato. Installa prima di procedere."
    echo "   Visita: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation"
    exit 1
fi

echo "✅ cloudflared è installato correttamente"

# Verifica versione di cloudflared
CLOUDFLARED_VERSION=$(cloudflared --version | head -n 1 | awk '{print $3}')
echo "📌 Versione cloudflared: $CLOUDFLARED_VERSION"

# Test tunnel diretto (interattivo)
echo "🔄 Avvio di un tunnel di test..."
echo "   (Questo aprirà un tunnel temporaneo verso localhost:8000)"
echo "   Premi Ctrl+C dopo aver verificato che il tunnel funzioni."

# Crea un semplice server HTTP Python sulla porta 8000
python3 -m http.server 8000 > /dev/null 2>&1 &
PYTHON_SERVER_PID=$!

# Ferma il server Python quando lo script termina
trap "kill $PYTHON_SERVER_PID" EXIT

# Mostra info IP locale
echo "📡 IP Locale:"
hostname -I

# Esegui cloudflared per verificare che funzioni
echo "🚀 Avvio tunnel di test..."
echo "   Attendi che compaia l'URL pubblico del tunnel..."
cloudflared tunnel --url http://localhost:8000

# Lo script non dovrebbe arrivare qui perché l'utente dovrebbe interrompere cloudflared
echo "✅ Test completato."
