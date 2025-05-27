#!/bin/bash
# Script di avvio per il container Docker

echo "🚀 Universal Tunnel Manager - Container Startup"
echo "==============================================="

# Verifica l'accesso al socket Docker
if [ ! -S /var/run/docker.sock ]; then
    echo "⚠️ Attenzione: /var/run/docker.sock non accessibile."
    echo "   Verifica che il volume sia montato correttamente."
else
    # Verifica permessi sul socket Docker
    ls -la /var/run/docker.sock
    echo "✅ Socket Docker trovato, verifica dei permessi completata."
    
    # Test comando docker
    echo "🔍 Test comando docker..."
    if docker ps >/dev/null 2>&1; then
        echo "✅ Comando docker funziona correttamente!"
    else
        echo "❌ Errore nell'esecuzione del comando docker. Controlla i permessi."
    fi
fi

# Crea directory per i dati persistenti se non esiste
mkdir -p /app/data
chmod 777 /app/data  # Assicura che la directory sia scrivibile

# Ottieni l'IP dell'host Docker
if [ -z "$LOCAL_IP" ]; then
    # Tenta di ottenere l'IP dell'host Docker
    echo "🔍 Rilevamento IP locale..."
    
    # Prova diversi metodi per ottenere l'IP
    # 1. Usando il gateway predefinito
    GATEWAY_IP=$(ip route | grep default | awk '{print $3}')
    echo "📡 IP Gateway: $GATEWAY_IP"
    
    # 2. Usando hostname -I
    HOSTNAME_IP=$(hostname -I | awk '{print $1}')
    echo "📡 IP Hostname: $HOSTNAME_IP"
    
    # 3. IP fisso per Docker bridge network
    BRIDGE_IP="172.17.0.1"
    echo "📡 IP Bridge predefinito: $BRIDGE_IP"
    
    # Usa l'IP del gateway come default
    export LOCAL_IP=$GATEWAY_IP
    echo "📡 IP finale selezionato: $LOCAL_IP"
fi

# Verifica che cloudflared sia installato
if ! command -v cloudflared &> /dev/null; then
    echo "❌ cloudflared non trovato. Questo è un errore nell'immagine Docker."
    exit 1
fi

echo "✅ Ambiente verificato, avvio dell'applicazione..."
echo "📱 Tunnel Manager in esecuzione su: http://0.0.0.0:5001"

# Avvia l'applicazione
exec python /app/tunnel_manager.py
