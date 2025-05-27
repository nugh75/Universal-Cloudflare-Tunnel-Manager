#!/usr/bin/env python3
"""
Interfaccia Web Universale per gestire tunnel Cloudflare per tutti i servizi Docker
"""

import subprocess
import psutil
import re
import time
import json
import os
from flask import Flask, render_template, jsonify, request
import threading
import socket
from datetime import datetime, timedelta # Aggiunto per la scadenza

app = Flask(__name__)

DEFAULT_TUNNEL_DURATION_HOURS = 48 # Ore

class UniversalTunnelManager:
    def __init__(self):
        self.active_tunnels = {}  # {service_name: {'process': process, 'url': url, 'port': port, 'expiration_time': timestamp}}
        self.local_ip = self.get_local_ip()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(script_dir, "data")
        self.config_file = os.path.join(self.data_dir, "tunnel_config.json")
        
        os.makedirs(self.data_dir, exist_ok=True)
        self.load_config_and_restore_expirations() # Modificato per ripristinare le scadenze
        self.clean_invalid_urls_from_config_file()

        # Thread per il controllo delle scadenze
        self.shutdown_event = threading.Event()
        self.expiration_checker_thread = threading.Thread(target=self.check_expired_tunnels_periodically, daemon=True)
        self.expiration_checker_thread.start()
        
    def save_config(self):
        config_to_save = {
            'timestamp': time.time(),
            'tunnels': {
                name: {
                    'url': info.get('url'),
                    'port': info.get('port'),
                    'local_url': info.get('local_url'), # Salva anche local_url
                    'start_time': info.get('start_time'), # Salva start_time
                    'expiration_time': info.get('expiration_time') # Salva expiration_time
                } for name, info in self.active_tunnels.items() if info.get('process') and info.get('url') # Salva solo se processo e URL esistono
            }
        }
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config_to_save, f, indent=2)
            print(f"Configurazione salvata in: {self.config_file}")
        except Exception as e:
            print(f"Errore nel salvataggio della configurazione: {e}")
            
    def load_config_and_restore_expirations(self):
        if not os.path.exists(self.config_file):
            print(f"File di configurazione non trovato: {self.config_file}")
            return
            
        try:
            with open(self.config_file, 'r') as f:
                config_loaded = json.load(f)
                
            print(f"Configurazione caricata da: {self.config_file}")
            # Ripristina le informazioni sui tunnel, incluse le scadenze, ma senza riavviare i processi
            # I tunnel non verranno riavviati automaticamente, ma le loro info (inclusa scadenza)
            # saranno disponibili se l'utente decide di riattivarli.
            # Oppure, se un tunnel fosse ancora attivo da una sessione precedente (improbabile con quick tunnels),
            # la sua scadenza verrebbe comunque monitorata.
            
            loaded_tunnels_info = config_loaded.get('tunnels', {})
            print(f"Tunnel precedentemente configurati: {len(loaded_tunnels_info)}")

            for name, data in loaded_tunnels_info.items():
                # Non sovrascriviamo tunnel già attivi (es. riavvio script veloce)
                # ma riempiamo le info di scadenza se un tunnel fosse in qualche modo già attivo
                # e non gestito da questa istanza (più teorico per i quick tunnels).
                # Principalmente, questo serve a mostrare le info se l'utente riattiva un tunnel.
                if name not in self.active_tunnels:
                     self.active_tunnels[name] = {
                        'process': None, # Non attivo al caricamento
                        'url': data.get('url'),
                        'port': data.get('port'),
                        'local_url': data.get('local_url'),
                        'start_time': data.get('start_time'),
                        'expiration_time': data.get('expiration_time')
                    }
                elif self.active_tunnels[name].get('process') is None: # Se esiste ma non ha processo
                    # Aggiorna le info se il tunnel è in memoria ma non attivo
                    self.active_tunnels[name].update({
                        'url': data.get('url', self.active_tunnels[name].get('url')),
                        'port': data.get('port', self.active_tunnels[name].get('port')),
                        'local_url': data.get('local_url', self.active_tunnels[name].get('local_url')),
                        'start_time': data.get('start_time', self.active_tunnels[name].get('start_time')),
                        'expiration_time': data.get('expiration_time', self.active_tunnels[name].get('expiration_time'))
                    })

        except Exception as e:
            print(f"Errore nel caricamento della configurazione: {e}")

    # ... (clean_invalid_urls_from_config_file, clean_active_invalid_urls, get_local_ip, get_docker_services, extract_ports sono invariati) ...
    def clean_invalid_urls_from_config_file(self): # Rinominata per chiarezza
        """Pulisce URL non validi dal file di configurazione"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f) # Rinomina variabile
                
                cleaned = False
                tunnels = config_data.get('tunnels', {})
                for service_name, tunnel_info in list(tunnels.items()): # Usa list() per iterare su una copia
                    url = tunnel_info.get('url', '')
                    # Aggiungi controllo per URL None o vuoti e altri placeholder comuni
                    if not url or 'website-terms' in url or 'cloudflare.com/website-terms' in url or 'developers.cloudflare.com' in url:
                        print(f"🧹 Rimosso URL non valido/placeholder per {service_name} dal file config: {url}")
                        del tunnels[service_name]
                        cleaned = True
                
                if cleaned:
                    config_data['tunnels'] = tunnels
                    with open(self.config_file, 'w') as f:
                        json.dump(config_data, f, indent=2)
                    print("🧹 Configurazione su file pulita dagli URL non validi")
            except Exception as e:
                print(f"Errore nella pulizia della configurazione su file: {e}")

    def clean_active_invalid_urls(self): # Per pulire i tunnel attivi in memoria
        """Pulisce URL non validi dai tunnel attivi in memoria."""
        cleaned = False
        for service_name, tunnel_info in list(self.active_tunnels.items()): # Usa list() per iterare su una copia
            url = tunnel_info.get('url')
            if url and ('website-terms' in url or 'developers.cloudflare.com' in url or 'connect.cloudflare.com' in url): # Aggiunto connect.cloudflare.com
                print(f"🧹 Rimosso URL non valido per tunnel attivo {service_name}: {url}")
                tunnel_info['url'] = None # Non rimuovere il tunnel, solo l'URL errato
                cleaned = True
        if cleaned:
             print("🧹 Tunnel attivi puliti da URL non validi. Saranno aggiornati al prossimo rilevamento.")


    def get_local_ip(self):
        """Ottiene l'IP locale"""
        try:
            env_ip = os.environ.get('LOCAL_IP')
            if env_ip:
                print(f"🔍 Usando IP da variabile d'ambiente LOCAL_IP: {env_ip}")
                return env_ip
            
            try:
                result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, check=False, timeout=2)
                if result.returncode == 0 and result.stdout.strip():
                    ip = result.stdout.strip().split()[0]
                    print(f"🔍 IP rilevato da hostname -I: {ip}")
                    return ip
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                print(f"ℹ️ 'hostname -I' non disponibile o timeout: {e}")

            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.1) 
                s.connect(("8.8.8.8", 80)) 
                ip = s.getsockname()[0]
                s.close()
                print(f"🔍 IP rilevato da socket connect: {ip}")
                return ip
            except Exception as e:
                print(f"ℹ️ Metodo socket connect fallito: {e}")

            try:
                hostname = socket.gethostname()
                ip = socket.gethostbyname(hostname)
                if ip != "127.0.0.1" and not ip.startswith("127."): 
                    print(f"🔍 IP rilevato da gethostbyname(hostname): {ip}")
                    return ip
            except socket.gaierror as e:
                print(f"ℹ️ Metodo gethostbyname(hostname) fallito: {e}")
            
            print(f"⚠️ Impossibile determinare IP locale affidabile, usando '127.0.0.1'. Potrebbe essere necessario LOCAL_IP.")
            return "127.0.0.1" 
        except Exception as e:
            print(f"⚠️ Errore critico nel rilevamento dell'IP locale: {e}, usando 127.0.0.1")
            return "127.0.0.1"
        
    def get_docker_services(self):
        """Ottiene la lista di tutti i servizi Docker con porte esposte"""
        try:
            # print(f"🔍 Ricerca servizi Docker in corso... IP Locale: {self.local_ip}")
            cmd = ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            services = []
            if result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        name = parts[0]
                        status = parts[1]
                        ports_str = parts[2]
                        image = parts[3] if len(parts) > 3 else "unknown"
                        
                        exposed_ports = self.extract_ports(ports_str)
                        
                        if "Up" in status:
                            tunnel_info = self.active_tunnels.get(name, {})
                            is_tunnel_active_and_running = name in self.active_tunnels and \
                                                           tunnel_info.get('process') is not None and \
                                                           tunnel_info['process'].poll() is None

                            services.append({
                                'name': name,
                                'status': status,
                                'ports': exposed_ports,
                                'image': image,
                                'tunnel_active': is_tunnel_active_and_running,
                                'tunnel_url': tunnel_info.get('url') if is_tunnel_active_and_running else None,
                                'selected_port': tunnel_info.get('port'),
                                'expiration_time': tunnel_info.get('expiration_time') if is_tunnel_active_and_running else None
                            })
            
            # print(f"🔍 Servizi Docker attivi trovati: {len(services)}")
            return services
        except subprocess.CalledProcessError as e:
            print(f"❌ Errore nel recupero servizi Docker (comando fallito): {e}")
            print(f"❌ Stderr: {e.stderr}")
            return []
        except FileNotFoundError:
            print("❌ Comando 'docker' non trovato. Assicurati che Docker sia installato e nel PATH.")
            return []
        except Exception as e:
            print(f"❌ Errore generico nel recupero servizi Docker: {str(e)}")
            return []
    
    def extract_ports(self, ports_string):
        if not ports_string or ports_string == "-":
            return []
        
        extracted_ports = set() 
        port_pattern = r'(?:0\.0\.0\.0:|\[::\]:)(\d+)->\d+/tcp'
        matches = re.findall(port_pattern, ports_string)
        for port in matches:
            extracted_ports.add(int(port))
        
        if not extracted_ports:
            localhost_pattern = r'127\.0\.0\.1:(\d+)->\d+/tcp'
            localhost_matches = re.findall(localhost_pattern, ports_string)
            for port in localhost_matches:
                extracted_ports.add(int(port))
        return sorted(list(extracted_ports))

    def start_tunnel_for_service(self, service_name, port, duration_hours=None): # Aggiunto duration_hours
        """Avvia un tunnel Cloudflare per un servizio specifico con una durata definita."""
        try:
            # Controlla se un tunnel è già attivo e in esecuzione
            if service_name in self.active_tunnels:
                existing_tunnel = self.active_tunnels[service_name]
                if existing_tunnel.get('process') and existing_tunnel['process'].poll() is None:
                    # Se è attivo e la porta è la stessa, potremmo voler solo aggiornare la scadenza
                    if existing_tunnel.get('port') == port:
                        new_expiration_time = time.time() + (duration_hours if duration_hours is not None else DEFAULT_TUNNEL_DURATION_HOURS) * 3600
                        existing_tunnel['expiration_time'] = new_expiration_time
                        self.save_config()
                        print(f"⏱️  Scadenza aggiornata per tunnel attivo {service_name} a {datetime.fromtimestamp(new_expiration_time).strftime('%Y-%m-%d %H:%M:%S')}")
                        return True, f"Scadenza tunnel per {service_name} aggiornata."
                    else:
                        # Se la porta è diversa, bisogna fermare il vecchio e avviarne uno nuovo
                        print(f"⚠️ Tunnel per {service_name} già attivo su porta diversa. Verrà fermato e riavviato.")
                        self.stop_tunnel_for_service(service_name) # Ferma il vecchio
                elif existing_tunnel.get('process') and existing_tunnel['process'].poll() is not None:
                    # Processo terminato, pulisci prima di riavviare
                    print(f"🧹 Pulizia tunnel precedentemente terminato per {service_name} prima del riavvio.")
                    del self.active_tunnels[service_name]


            url_to_tunnel = f"http://{self.local_ip}:{port}"
            print(f"🚀 Avvio tunnel per {service_name} verso {url_to_tunnel}")
            
            cmd = [
                "cloudflared", "tunnel",
                "--url", url_to_tunnel,
                "--no-autoupdate",
                "--edge-ip-version", "auto",
            ]
            
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            start_time = time.time()
            if duration_hours is None:
                duration_hours = DEFAULT_TUNNEL_DURATION_HOURS
            
            expiration_time = start_time + (duration_hours * 3600)
            
            self.active_tunnels[service_name] = {
                'process': process,
                'url': None,
                'port': port,
                'local_url': url_to_tunnel,
                'start_time': start_time,
                'expiration_time': expiration_time # Memorizza il timestamp di scadenza
            }
            
            print(f"⏱️  Tunnel per {service_name} scadrà il: {datetime.fromtimestamp(expiration_time).strftime('%Y-%m-%d %H:%M:%S')}")

            threading.Thread(
                target=self.capture_tunnel_url,
                args=(service_name, process),
                daemon=True
            ).start()
            
            return True, f"Tentativo di avvio tunnel per {service_name} su porta {port} (scade in {duration_hours} ore)..."
        except Exception as e:
            print(f"❌ Errore critico nell'avvio del tunnel per {service_name}: {e}")
            if service_name in self.active_tunnels:
                del self.active_tunnels[service_name]
            return False, f"Errore avvio tunnel: {str(e)}"
            
    # ... (capture_tunnel_url è invariato) ...
    def capture_tunnel_url(self, service_name, process):
        """Cattura l'URL del tunnel dal processo cloudflared, leggendo stderr."""
        print(f"👀 Monitoraggio output stderr per {service_name}...")
        tunnel_url = None
        
        patterns = [
            re.compile(r"url=(https://[a-zA-Z0-9.-]+\.trycloudflare\.com)"),
            re.compile(r"URL:\s*(https://[a-zA-Z0-9.-]+\.trycloudflare\.com)"),
            re.compile(r"established connection.*url=(https://[a-zA-Z0-9.-]+\.trycloudflare\.com)"),
            re.compile(r"Your quick Tunnel has been created! Visit it at:\s*(https://[a-zA-Z0-9.-]+\.trycloudflare\.com)"),
            re.compile(r"(https://[a-zA-Z0-9.-]+\.trycloudflare\.com)"), 
        ]

        timeout_seconds = 30 
        start_capture_time = time.time()

        try:
            for stream_name, stream in [("stderr", process.stderr), ("stdout", process.stdout)]:
                if tunnel_url: break 
                # print(f"👂 In ascolto su {stream_name} per {service_name}") # Meno verboso
                for line in iter(stream.readline, ''):
                    if not line and process.poll() is not None: 
                        print(f"⚠️ Processo cloudflared per {service_name} terminato prematuramente durante la cattura dell'URL.")
                        break
                    
                    # print(f"RAW LOG ({service_name} - {stream_name}): {line.strip()}") # Verboso per debug
                    
                    for pattern_idx, pattern in enumerate(patterns):
                        match = pattern.search(line)
                        if match:
                            potential_url = match.group(1)
                            if ".trycloudflare.com" in potential_url and not any(bad_keyword in potential_url for bad_keyword in ["website-terms", "developers.cloudflare.com"]):
                                tunnel_url = potential_url
                                print(f"✅ URL tunnel trovato per {service_name} (pattern {pattern_idx}): {tunnel_url}")
                                break 
                    
                    if tunnel_url:
                        break 
                    
                    if time.time() - start_capture_time > timeout_seconds:
                        print(f"⏳ Timeout ({timeout_seconds}s) raggiunto durante la ricerca dell'URL per {service_name}.")
                        break
                if tunnel_url or (time.time() - start_capture_time > timeout_seconds):
                    break 


            if service_name in self.active_tunnels:
                if tunnel_url:
                    self.active_tunnels[service_name]['url'] = tunnel_url
                    self.save_config() 
                else:
                    print(f"❌ Impossibile trovare l'URL del tunnel per {service_name} dopo {timeout_seconds}s.")
                    self.active_tunnels[service_name]['url'] = "Ricerca URL fallita"
            else:
                print(f"⚠️ {service_name} non trovato in active_tunnels durante la cattura dell'URL (forse è stato fermato).")

        except Exception as e:
            print(f"❌ Errore critico nel catturare l'URL del tunnel per {service_name}: {e}")
            if service_name in self.active_tunnels:
                self.active_tunnels[service_name]['url'] = f"Errore cattura URL: {e}"
        finally:
            print(f"🏁 Monitoraggio output completato per {service_name}. URL: {tunnel_url}")


    def stop_tunnel_for_service(self, service_name, reason="richiesta utente"): # Aggiunto reason
        """Ferma un tunnel Cloudflare per un servizio specifico."""
        try:
            if service_name not in self.active_tunnels or not self.active_tunnels[service_name].get('process'):
                # Potrebbe esserci un record senza processo se caricato da config, quindi rimuovilo se presente
                if service_name in self.active_tunnels:
                    del self.active_tunnels[service_name]
                    self.save_config()
                return False, "Nessun tunnel attivo o processo associato per questo servizio."
                
            tunnel_info = self.active_tunnels[service_name]
            process = tunnel_info['process']
            
            print(f"🔌 Tentativo di fermare il tunnel per {service_name} (PID: {process.pid if process else 'N/A'}, Motivo: {reason})")
            
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            
            del self.active_tunnels[service_name]
            self.save_config()
            
            print(f"✔️ Tunnel per {service_name} fermato e rimosso (Motivo: {reason}).")
            return True, f"Tunnel fermato con successo (Motivo: {reason})."
        except Exception as e:
            print(f"❌ Errore nel fermare il tunnel per {service_name}: {e}")
            # Non rimuovere il tunnel in caso di errore qui, potrebbe essere ancora parzialmente attivo
            return False, f"Errore: {str(e)}"
    
    def stop_all_tunnels(self, reason="richiesta utente globale"): # Aggiunto reason
        """Ferma tutti i tunnel attivi gestiti da questa istanza."""
        print(f"🔌 Tentativo di fermare tutti i tunnel attivi (Motivo: {reason})...")
        stopped_count = 0
        services_to_stop = list(self.active_tunnels.keys())
        
        for service_name in services_to_stop:
            success, _ = self.stop_tunnel_for_service(service_name, reason=f"globale - {reason}")
            if success:
                stopped_count +=1
        
        message = f"Fermati {stopped_count}/{len(services_to_stop)} tunnel gestiti (Motivo: {reason})."
        print(message)
        return True, message
    
    def get_status(self):
        self.clean_active_invalid_urls()
        active_tunnels_details = []
        current_time = time.time()

        for name, info in list(self.active_tunnels.items()): # list() per iterare su una copia
            is_running = False
            process_status = "Non attivo"
            
            if info.get('process'):
                if info['process'].poll() is None:
                    process_status = "In esecuzione"
                    is_running = True
                else:
                    process_status = f"Terminato (codice: {info['process'].returncode})"
                    # Se il processo è terminato ma il record esiste ancora, consideralo non attivo qui
                    # La pulizia effettiva avverrà tramite check_expired o stop manuale
            
            # Se il tunnel non è in esecuzione, non ha senso parlare di scadenza attiva
            expiration_timestamp = info.get('expiration_time') if is_running else None
            time_remaining_seconds = None
            if expiration_timestamp:
                time_remaining_seconds = expiration_timestamp - current_time
                if time_remaining_seconds < 0: # Se è scaduto ma non ancora pulito dal checker
                    time_remaining_seconds = 0 
                    # Potrebbe essere stato fermato dal checker tra questo calcolo e il prossimo ciclo
                    # La visualizzazione mostrerà "scaduto" o 0s rimanenti.
            
            # Non includere tunnel che non hanno un processo o sono terminati
            # O meglio, includili ma segnala il loro stato.
            # Se un tunnel è in self.active_tunnels ma il processo è None o terminato,
            # è uno stato transitorio o un residuo.
            
            # La logica in get_docker_services già aggiorna 'tunnel_active' e 'expiration_time'
            # basandosi sullo stato corrente, qui arricchiamo per i tunnel *effettivamente gestiti*
            
            # Se il tunnel non è più in esecuzione, non dovrebbe avere un URL attivo o scadenza rilevante
            if not is_running:
                # Potremmo voler rimuovere il tunnel da active_tunnels se il processo è morto
                # ma questo è gestito da check_expired_tunnels_periodically o da stop_tunnel
                # Per ora, mostriamo lo stato come non in esecuzione
                pass


            active_tunnels_details.append({
                'service_name': name,
                'url': info.get('url') if is_running else None,
                'port': info.get('port'),
                'local_url': info.get('local_url'),
                'process_status': process_status,
                'is_running': is_running,
                'start_time': info.get('start_time') if is_running else None,
                'expiration_time': expiration_timestamp, # Timestamp UNIX
                'time_remaining_seconds': time_remaining_seconds if expiration_timestamp else None
            })
        
        return {
            'services': self.get_docker_services(), # Questa ora include info di scadenza parziali
            'active_tunnels': active_tunnels_details,
            'active_tunnels_count': len([t for t in active_tunnels_details if t['is_running']]),
            'local_ip': self.local_ip,
            'default_tunnel_duration_hours': DEFAULT_TUNNEL_DURATION_HOURS
        }

    def check_expired_tunnels_periodically(self):
        """Controlla periodicamente i tunnel scaduti e li ferma."""
        print("⏳ Avvio del controllore di scadenza tunnel...")
        while not self.shutdown_event.is_set():
            current_time = time.time()
            # Iterare su una copia delle chiavi perché il dizionario potrebbe cambiare
            for service_name in list(self.active_tunnels.keys()):
                try:
                    tunnel_info = self.active_tunnels.get(service_name)
                    if not tunnel_info: # Potrebbe essere stato rimosso nel frattempo
                        continue

                    # Controlla solo se il processo esiste ed è in esecuzione
                    process = tunnel_info.get('process')
                    if not process or process.poll() is not None: # Se non c'è processo o è terminato
                        if service_name in self.active_tunnels: # Verifica se esiste ancora prima di cancellare
                            print(f"🧹 Pulizia record tunnel non attivo o terminato: {service_name}")
                            del self.active_tunnels[service_name]
                            self.save_config() # Salva dopo la pulizia
                        continue # Passa al prossimo

                    expiration_time = tunnel_info.get('expiration_time')
                    if expiration_time and current_time >= expiration_time:
                        print(f"⌛ Tunnel per {service_name} è scaduto. Tentativo di arresto...")
                        self.stop_tunnel_for_service(service_name, reason="scaduto automaticamente")
                except KeyError:
                    # Il tunnel potrebbe essere stato rimosso da un'altra operazione
                    print(f"ℹ️ Tunnel {service_name} non trovato durante il controllo scadenza (già rimosso?).")
                except Exception as e:
                    print(f"❌ Errore durante il controllo di scadenza per {service_name}: {e}")
            
            # Aspetta un po' prima del prossimo controllo (es. ogni 60 secondi)
            self.shutdown_event.wait(60) 
        print("🛑 Controllore di scadenza tunnel fermato.")

    def shutdown(self): # Metodo per fermare il thread del checker
        print("🚦 Richiesta di arresto per UniversalTunnelManager...")
        self.shutdown_event.set()
        self.stop_all_tunnels(reason="arresto applicazione")
        if self.expiration_checker_thread.is_alive():
            self.expiration_checker_thread.join(timeout=5) # Attendi che il thread termini
        print("🏁 UniversalTunnelManager arrestato.")


# Istanza globale del manager
tunnel_manager = UniversalTunnelManager()

# Gestione dell'arresto pulito
import atexit
atexit.register(tunnel_manager.shutdown)

@app.route('/')
def index():
    return render_template('universal.html')

@app.route('/api/status')
def api_status():
    return jsonify(tunnel_manager.get_status())

@app.route('/api/start-tunnel', methods=['POST'])
def api_start_tunnel():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Richiesta JSON non valida o vuota'}), 400
            
        service_name = data.get('service_name')
        port_str = data.get('port')
        duration_hours_str = data.get('duration_hours') # Nuovo parametro
        
        if not service_name or not port_str:
            return jsonify({'success': False, 'message': 'Parametri mancanti: service_name e port sono richiesti'}), 400
        
        try:
            port = int(port_str)
            if not (0 < port < 65536):
                raise ValueError("Porta non valida")
        except ValueError:
            return jsonify({'success': False, 'message': f"Porta non valida: '{port_str}'."}), 400

        duration_hours = None
        if duration_hours_str:
            try:
                duration_hours = float(duration_hours_str) # Permetti anche frazioni di ora, es. 0.5 per 30 min
                if duration_hours <= 0:
                    return jsonify({'success': False, 'message': 'La durata deve essere un numero positivo.'}), 400
            except ValueError:
                return jsonify({'success': False, 'message': f"Durata non valida: '{duration_hours_str}'. Deve essere un numero."}), 400
        else:
            duration_hours = DEFAULT_TUNNEL_DURATION_HOURS # Usa il default se non specificato
            
        success, message = tunnel_manager.start_tunnel_for_service(service_name, port, duration_hours)
        status_code = 200 if success else 500
        if not success and ("già attivo" in message or "aggiornata" in message):
             status_code = 200 # Se è già attivo e abbiamo aggiornato la scadenza, è un successo
        elif not success:
             status_code = 409 if "già attivo" in message else 500

        return jsonify({'success': success, 'message': message}), status_code
    except Exception as e:
        print(f"Errore imprevisto in api_start_tunnel: {e}")
        return jsonify({'success': False, 'message': f'Errore server: {str(e)}'}), 500

# ... (api_stop_tunnel, api_stop_all, api_debug sono per lo più invariati, ma passano 'reason') ...

@app.route('/api/stop-tunnel', methods=['POST'])
def api_stop_tunnel():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Richiesta JSON non valida o vuota'}), 400

        service_name = data.get('service_name')
        
        if not service_name:
            return jsonify({'success': False, 'message': 'Nome servizio (service_name) mancante'}), 400
        
        success, message = tunnel_manager.stop_tunnel_for_service(service_name, reason="richiesta API utente")
        status_code = 200 if success else (404 if "Nessun tunnel attivo" in message else 500)
        return jsonify({'success': success, 'message': message}), status_code
    except Exception as e:
        print(f"Errore imprevisto in api_stop_tunnel: {e}")
        return jsonify({'success': False, 'message': f'Errore server: {str(e)}'}), 500

@app.route('/api/stop-all', methods=['POST'])
def api_stop_all():
    try:
        success, message = tunnel_manager.stop_all_tunnels(reason="richiesta API utente globale")
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        print(f"Errore imprevisto in api_stop_all: {e}")
        return jsonify({'success': False, 'message': f'Errore server: {str(e)}'}), 500

@app.route('/api/debug', methods=['GET'])
def api_debug():
    """API per debug - mostra info sui processi e configurazione"""
    try:
        debug_info = {
            'timestamp': time.time(),
            'local_ip': tunnel_manager.local_ip,
            'config_file_path': tunnel_manager.config_file,
            'default_tunnel_duration_hours': DEFAULT_TUNNEL_DURATION_HOURS,
            'active_tunnels_manager_state': [],
            'docker_services_detected': tunnel_manager.get_docker_services(), 
            'cloudflared_processes_psutil': []
        }
        
        current_time_debug = time.time()
        for name, info in tunnel_manager.active_tunnels.items():
            proc_info = info.get('process')
            is_running_debug = proc_info.poll() is None if proc_info else False
            exp_time = info.get('expiration_time')
            time_rem_sec_debug = None
            if exp_time and is_running_debug:
                time_rem_sec_debug = exp_time - current_time_debug

            debug_info['active_tunnels_manager_state'].append({
                'service_name': name,
                'port': info.get('port'),
                'url': info.get('url'),
                'local_url': info.get('local_url'),
                'start_time': info.get('start_time'),
                'expiration_time': exp_time,
                'expiration_time_readable': datetime.fromtimestamp(exp_time).strftime('%Y-%m-%d %H:%M:%S') if exp_time else None,
                'time_remaining_seconds': time_rem_sec_debug,
                'process_pid': proc_info.pid if proc_info else None,
                'process_running': is_running_debug,
                'process_return_code': proc_info.returncode if proc_info and proc_info.poll() is not None else None
            })
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'status', 'create_time']):
            try:
                if 'cloudflared' in proc.info['name'].lower():
                    debug_info['cloudflared_processes_psutil'].append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cmdline': ' '.join(proc.info['cmdline'] if proc.info['cmdline'] else []),
                        'status': proc.info['status'],
                        'create_time': proc.info['create_time']
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        
        try:
            if os.path.exists(tunnel_manager.config_file):
                with open(tunnel_manager.config_file, 'r') as f:
                    debug_info['config_file_content'] = json.load(f)
            else:
                debug_info['config_file_content'] = "File non esistente."
        except Exception as e:
            debug_info['config_file_content_error'] = str(e)
        
        return jsonify(debug_info)
    except Exception as e:
        print(f"Errore in api_debug: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    print("🚀 Avvio Universal Cloudflare Tunnel Manager con Scadenza")
    host_ip_for_display = tunnel_manager.local_ip if tunnel_manager.local_ip != "127.0.0.1" else "localhost"
    print(f"🐍 Versione Python: {socket.sys.version}")
    print(f"📦 Percorso script: {os.path.dirname(os.path.abspath(__file__))}")
    print(f"🏠 Directory dati: {tunnel_manager.data_dir}")
    print(f"⚙️ File configurazione: {tunnel_manager.config_file}")
    print(f"⏱️ Durata tunnel default: {DEFAULT_TUNNEL_DURATION_HOURS} ore")
    print(f"🖥️  Interfaccia Web disponibile su: http://{host_ip_for_display}:5001")
    
    # In sviluppo con thread, use_reloader=False può essere più stabile.
    # Per produzione, debug=False.
    try:
        app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False) # use_reloader=False è importante con thread e atexit
    except KeyboardInterrupt:
        print("\n⌨️ Interruzione da tastiera ricevuta. Arresto in corso...")
    finally:
        tunnel_manager.shutdown() # Assicura che il cleanup avvenga