# Universal Tunnel Manager Dockerfile
FROM python:3.11-slim

# Metadata
LABEL maintainer="nugh75"
LABEL description="Universal Tunnel Manager per servizi Docker"
LABEL version="1.0"

# Variabili di ambiente
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=tunnel_manager.py
ENV FLASK_ENV=production

# Installa le dipendenze di sistema necessarie
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    lsb-release \
    ca-certificates \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Installa Docker CLI (per comunicare con Docker daemon dell'host)
RUN curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Installa cloudflared
RUN wget https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb \
    && dpkg -i cloudflared-linux-amd64.deb \
    && rm cloudflared-linux-amd64.deb

# Crea directory dell'applicazione
WORKDIR /app

# Copia i file requirements (se esistono) o crea al volo
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice dell'applicazione
COPY tunnel_manager.py .
COPY templates/ ./templates/
COPY start-container.sh .

# Rende start-container.sh eseguibile
RUN chmod +x start-container.sh

# Crea un utente non-root per sicurezza (usato solo quando specificato)
RUN useradd -m -u 1000 tunneluser && chown -R tunneluser:tunneluser /app

# Nota: non impostiamo USER tunneluser qui per permettere l'esecuzione come root quando necessario

# Espone la porta dell'applicazione
EXPOSE 5001

# Comando di avvio
CMD ["./start-container.sh"]
