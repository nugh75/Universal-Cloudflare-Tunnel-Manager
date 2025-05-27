#!/bin/bash
# Script per gestire i dati del tunnel manager

# Cartella dati
DATA_DIR="/app/data"
CONFIG_FILE="$DATA_DIR/tunnel_config.json"

# Crea la directory dei dati se non esiste
mkdir -p "$DATA_DIR"

case "$1" in
    backup)
        echo "📦 Backup della configurazione in corso..."
        # Crea backup della configurazione corrente
        if [ -f "$CONFIG_FILE" ]; then
            cp "$CONFIG_FILE" "$CONFIG_FILE.bak"
            echo "✅ Backup completato: $CONFIG_FILE.bak"
        else
            echo "⚠️ Nessun file di configurazione da eseguire il backup."
        fi
        ;;
    restore)
        echo "🔄 Ripristino della configurazione in corso..."
        # Ripristina da backup se esiste
        if [ -f "$CONFIG_FILE.bak" ]; then
            cp "$CONFIG_FILE.bak" "$CONFIG_FILE"
            echo "✅ Ripristino completato da: $CONFIG_FILE.bak"
        else
            echo "⚠️ Nessun backup trovato da ripristinare."
        fi
        ;;
    clean)
        echo "🧹 Pulizia dati in corso..."
        # Elimina tutti i dati (con conferma)
        read -p "⚠️ Sei sicuro di voler eliminare tutti i dati? [s/N] " confirm
        if [[ "$confirm" == [sS] ]]; then
            rm -rf "$DATA_DIR"/*
            mkdir -p "$DATA_DIR"
            echo "✅ Dati eliminati."
        else
            echo "❌ Operazione annullata."
        fi
        ;;
    status)
        echo "📊 Stato dati:"
        if [ -f "$CONFIG_FILE" ]; then
            echo "✅ File configurazione: $(du -h "$CONFIG_FILE" | cut -f1)"
            echo "🔄 Ultimo aggiornamento: $(date -r "$CONFIG_FILE")"
        else
            echo "⚠️ Nessun file di configurazione trovato."
        fi
        
        echo "💾 Spazio totale utilizzato: $(du -sh "$DATA_DIR" | cut -f1)"
        ;;
    *)
        echo "📋 Utilizzo: $0 [backup|restore|clean|status]"
        echo "  backup  - Crea backup della configurazione"
        echo "  restore - Ripristina da backup"
        echo "  clean   - Elimina tutti i dati"
        echo "  status  - Mostra stato dei dati"
        ;;
esac
