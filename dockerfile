# Dockerfile

# Usa un'immagine Python slim come base
FROM python:3.10-slim

# Imposta la directory di lavoro nell'immagine
WORKDIR /app

# Variabili d'ambiente per installazioni non interattive e buffering Python
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Installa dipendenze di sistema necessarie
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    lsb-release \
    ca-certificates \
    apt-transport-https && \
    rm -rf /var/lib/apt/lists/*

# Installa cloudflared (scarica l'ultima versione per linux amd64)
RUN curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared && \
    chmod +x /usr/local/bin/cloudflared && \
    cloudflared --version

# Installa Docker CLI
# Puoi aggiornare questa versione se necessario (controlla https://download.docker.com/linux/static/stable/x86_64/)
ENV DOCKER_VERSION=26.1.4
RUN curl -fsSL "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_VERSION}.tgz" -o docker.tgz && \
    tar --extract --file docker.tgz --strip-components 1 --directory /usr/local/bin docker/docker && \
    rm docker.tgz && \
    docker --version

# Copia il file delle dipendenze Python
COPY requirements.txt .

# Installa le dipendenze Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia il resto dell'applicazione nella directory /app dell'immagine
COPY . .

# Crea la directory dei dati
RUN mkdir -p /app/data

# Esponi la porta su cui Flask è in ascolto all'interno del container
EXPOSE 5001

# Comando per avviare l'applicazione quando il container parte
CMD ["python3", "app.py"]