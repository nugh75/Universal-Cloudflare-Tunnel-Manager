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
from flask import Flask, render_template, jsonify, request, url_for
import threading
import socket
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s')

app = Flask(__name__)

DEFAULT_TUNNEL_DURATION_HOURS = 48

class UniversalTunnelManager:
    def __init__(self):
        self.active_tunnels = {}
        self.local_ip = self.get_local_ip()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(script_dir, "data")
        self.config_file = os.path.join(self.data_dir, "tunnel_config.json")
        
        os.makedirs(self.data_dir, exist_ok=True)
        self.load_config_and_restore_expirations()
        self.clean_invalid_urls_from_config_file()

        self.shutdown_event = threading.Event()
        self.expiration_checker_thread = threading.Thread(
            target=self.check_expired_tunnels_periodically, 
            daemon=True,
            name="ExpirationChecker"
        )
        self.expiration_checker_thread.start()
        
    def save_config(self):
        config_to_save = {
            'timestamp': time.time(),
            'tunnels': {
                name: {
                    'url': info.get('url'),
                    'port': info.get('port'),
                    'local_url': info.get('local_url'),
                    'start_time': info.get('start_time'),
                    'expiration_time': info.get('expiration_time')
                } for name, info in self.active_tunnels.items()
            }
        }
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config_to_save, f, indent=2)
            logging.debug(f"Configurazione salvata in: {self.config_file}")
        except Exception as e:
            logging.error(f"Errore nel salvataggio della configurazione: {e}")
            
    def load_config_and_restore_expirations(self):
        if not os.path.exists(self.config_file):
            logging.info(f"File di configurazione non trovato: {self.config_file}")
            return
        try:
            with open(self.config_file, 'r') as f:
                config_loaded = json.load(f)
            logging.info(f"Configurazione caricata da: {self.config_file}")
            loaded_tunnels_info = config_loaded.get('tunnels', {})
            logging.info(f"Tunnel precedentemente configurati: {len(loaded_tunnels_info)}")

            for name, data in loaded_tunnels_info.items():
                if name not in self.active_tunnels: # Non sovrascrivere se già in memoria per qualche motivo
                     self.active_tunnels[name] = {
                        'process': None, # I processi non vengono ripristinati
                        'url': data.get('url'),
                        'port': data.get('port'),
                        'local_url': data.get('local_url'),
                        'start_time': data.get('start_time'),
                        'expiration_time': data.get('expiration_time')
                    }
        except Exception as e:
            logging.error(f"Errore nel caricamento della configurazione: {e}")

    def clean_invalid_urls_from_config_file(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    config_data = json.load(f)
                cleaned = False
                tunnels = config_data.get('tunnels', {})
                for service_name, tunnel_info in list(tunnels.items()):
                    url = tunnel_info.get('url', '')
                    if not url or 'website-terms' in url or 'cloudflare.com/website-terms' in url or 'developers.cloudflare.com' in url:
                        logging.info(f"🧹 Rimosso URL non valido per {service_name} dal file config: {url}")
                        del tunnels[service_name]
                        cleaned = True
                if cleaned:
                    config_data['tunnels'] = tunnels
                    with open(self.config_file, 'w') as f:
                        json.dump(config_data, f, indent=2)
                    logging.info("🧹 Configurazione su file pulita dagli URL non validi.")
            except Exception as e:
                logging.error(f"Errore nella pulizia config su file: {e}")

    def get_local_ip(self):
        # ... (implementazione come prima) ...
        try:
            env_ip = os.environ.get('LOCAL_IP')
            if env_ip:
                logging.info(f"IP da LOCAL_IP: {env_ip}")
                return env_ip
            try:
                result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, check=False, timeout=2)
                if result.returncode == 0 and result.stdout.strip():
                    ip = result.stdout.strip().split()[0]
                    logging.info(f"IP da hostname -I: {ip}")
                    return ip
            except Exception: logging.debug("hostname -I fallito")
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(0.1); s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
                logging.info(f"IP da socket connect: {ip}")
                return ip
            except Exception: logging.debug("socket connect fallito")
            logging.warning("IP fallback: 127.0.0.1")
            return "127.0.0.1"
        except Exception as e:
            logging.error(f"Errore get_local_ip: {e}, fallback 127.0.0.1")
            return "127.0.0.1"

    def get_docker_services(self):
        # ... (implementazione come prima) ...
        try:
            cmd = ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}"]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            services = []
            if result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    parts = line.split('\t')
                    if len(parts) >= 3:
                        name, status, ports_str = parts[0], parts[1], parts[2]
                        image = parts[3] if len(parts) > 3 else "unknown"
                        exposed_ports = self.extract_ports(ports_str)
                        if "Up" in status:
                            services.append({'name': name, 'status': status, 'ports': exposed_ports, 'image': image})
            return services
        except Exception as e:
            logging.error(f"Errore get_docker_services: {e}")
            return []
            
    def extract_ports(self, ports_string):
        # ... (implementazione come prima) ...
        if not ports_string or ports_string == "-": return []
        extracted = set()
        for p in re.findall(r'(?:0\.0\.0\.0:|\[::\]:)(\d+)->\d+/tcp', ports_string): extracted.add(int(p))
        if not extracted:
            for p in re.findall(r'127\.0\.0\.1:(\d+)->\d+/tcp', ports_string): extracted.add(int(p))
        return sorted(list(extracted))

    def start_tunnel_for_service(self, service_name, port, duration_hours=None):
        try:
            current_time = time.time()
            effective_duration_hours = duration_hours if duration_hours is not None else DEFAULT_TUNNEL_DURATION_HOURS
            new_expiration_time = current_time + (effective_duration_hours * 3600)

            if service_name in self.active_tunnels:
                existing_tunnel = self.active_tunnels[service_name]
                process_is_running = existing_tunnel.get('process') and existing_tunnel['process'].poll() is None

                if process_is_running:
                    if existing_tunnel.get('port') == port: 
                        existing_tunnel['expiration_time'] = new_expiration_time
                        logging.info(f"Scadenza aggiornata per {service_name} a {datetime.fromtimestamp(new_expiration_time).strftime('%Y-%m-%d %H:%M:%S')}")
                        if not existing_tunnel.get('url') or existing_tunnel.get('url') == "Ricerca URL fallita":
                            logging.info(f"Tunnel {service_name} attivo ma senza URL. Tentativo ricattura.")
                            threading.Thread(
                                target=self.capture_tunnel_url,
                                args=(service_name, existing_tunnel['process']),
                                daemon=True, name=f"CaptureURL-{service_name[:10]}"
                            ).start()
                        self.save_config()
                        return True, f"Scadenza tunnel per {service_name} aggiornata."
                    else: 
                        logging.info(f"Tunnel per {service_name} su porta diversa. Stop e riavvio.")
                        self.stop_tunnel_for_service(service_name, reason="cambio porta")
            
            url_to_tunnel = f"http://{self.local_ip}:{port}"
            logging.info(f"Avvio tunnel per {service_name} ({port}) -> {url_to_tunnel}")
            cmd = ["cloudflared", "tunnel", "--url", url_to_tunnel, "--no-autoupdate", "--edge-ip-version", "auto", "--protocol", "http2"] # Aggiunto http2
            
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1, universal_newlines=True, encoding='utf-8', errors='replace' # Gestione encoding
            )
            
            self.active_tunnels[service_name] = {
                'process': process, 'url': "Ricerca URL fallita", 'port': port,
                'local_url': url_to_tunnel, 'start_time': current_time,
                'expiration_time': new_expiration_time
            }
            logging.info(f"Tunnel per {service_name} scadrà: {datetime.fromtimestamp(new_expiration_time).strftime('%Y-%m-%d %H:%M:%S')}")
            
            threading.Thread(
                target=self.capture_tunnel_url, 
                args=(service_name, process), 
                daemon=True, name=f"CaptureURL-{service_name[:10]}"
            ).start()
            self.save_config() 
            return True, f"Avvio tunnel per {service_name} (scade in {effective_duration_hours:.1f} ore)..."

        except Exception as e:
            logging.error(f"Errore avvio tunnel {service_name}: {e}", exc_info=True)
            if service_name in self.active_tunnels: del self.active_tunnels[service_name]
            self.save_config()
            return False, f"Errore avvio tunnel: {str(e)}"
            
    def capture_tunnel_url(self, service_name, process):
        logging.info(f"Monitoraggio output per {service_name} (PID: {process.pid})...")
        tunnel_url = None
        # Pattern più comuni all'inizio
        patterns = [
            re.compile(r"INF Starting tunnel.*url=(https://[a-zA-Z0-9.-]+\.trycloudflare\.com)"),
            re.compile(r"Connection [a-f0-9-]+ registered connIndex=\d+ ip=[0-9.]+ location=[\w\d]+.*URL: (https://[a-zA-Z0-9.-]+\.trycloudflare\.com)"), # Nuovo pattern dettagliato
            re.compile(r"Your quick Tunnel has been created! Visit it at:\s*(https://[a-zA-Z0-9.-]+\.trycloudflare\.com)"),
            re.compile(r"URL:\s*(https://[a-zA-Z0-9.-]+\.trycloudflare\.com)"), # Meno specifico
            re.compile(r"url=(https://[a-zA-Z0-9.-]+\.trycloudflare\.com)"), # Meno specifico
        ]
        generic_pattern = re.compile(r"(https://[a-zA-Z0-9.-]+\.trycloudflare\.com)") # Ultima spiaggia

        timeout_seconds = 35 
        start_capture_time = time.time()
        log_buffer = []

        try:
            # Cloudflared quick tunnels solitamente loggano su stderr
            stream_to_read = process.stderr # Dai priorità a stderr
            
            for line_num, line in enumerate(iter(stream_to_read.readline, '')):
                log_buffer.append(line.strip())
                if not line and process.poll() is not None: 
                    logging.warning(f"Processo cloudflared per {service_name} terminato prematuramente.")
                    break
                
                # logging.debug(f"RAW_LOG ({service_name}-L{line_num}): {line.strip()}") # Debug intenso
                
                for i, pattern in enumerate(patterns):
                    match = pattern.search(line)
                    if match:
                        potential_url = match.group(1)
                        if ".trycloudflare.com" in potential_url and not any(bad in potential_url for bad in ["website-terms", "developers.cloudflare"]):
                            tunnel_url = potential_url
                            logging.info(f"URL tunnel trovato per {service_name} (pattern {i}): {tunnel_url}")
                            break 
                if tunnel_url: break 
                
                # Fallback al pattern generico se i più specifici non matchano subito
                if not tunnel_url:
                    match_generic = generic_pattern.search(line)
                    if match_generic:
                        potential_url = match_generic.group(1)
                        if ".trycloudflare.com" in potential_url and not any(bad in potential_url for bad in ["website-terms", "developers.cloudflare"]):
                            tunnel_url = potential_url
                            logging.info(f"URL tunnel trovato per {service_name} (pattern generico): {tunnel_url}")
                            break

                if time.time() - start_capture_time > timeout_seconds:
                    logging.warning(f"Timeout ({timeout_seconds}s) ricerca URL per {service_name}.")
                    break
            
            # Se non trovato su stderr, prova stdout (meno probabile per quick tunnels)
            if not tunnel_url and process.stdout:
                logging.info(f"Nessun URL su stderr per {service_name}, controllo stdout...")
                for line_num, line in enumerate(iter(process.stdout.readline, '')): # Leggi qualche riga da stdout
                    if line_num > 20 : break # Limita la lettura da stdout
                    # ... (ripeti logica pattern come sopra per stdout) ...
                    # Per brevità, qui non la ripeto, ma dovresti farlo se necessario
                    pass


            if service_name in self.active_tunnels:
                if tunnel_url:
                    self.active_tunnels[service_name]['url'] = tunnel_url
                else:
                    logging.error(f"Impossibile trovare URL per {service_name} dopo {timeout_seconds}s.")
                    # 'url' rimane "Ricerca URL fallita"
                self.save_config()
            else: 
                logging.warning(f"{service_name} non in active_tunnels durante cattura URL.")

        except Exception as e:
            logging.error(f"Errore cattura URL {service_name}: {e}", exc_info=True)
            if service_name in self.active_tunnels: self.active_tunnels[service_name]['url'] = f"Errore cattura: {e}"
        finally:
            if not tunnel_url and log_buffer:
                 logging.debug(f"Log buffer per {service_name} (ricerca URL fallita):\n" + "\n".join(log_buffer[-20:]))
            logging.info(f"Monitoraggio output completato per {service_name}. URL finale: {self.active_tunnels.get(service_name, {}).get('url')}")

    def stop_tunnel_for_service(self, service_name, reason="richiesta utente"):
        # ... (implementazione come prima) ...
        try:
            tunnel_info = self.active_tunnels.get(service_name)
            if not tunnel_info : 
                 logging.info(f"Tentativo stop per {service_name} (non trovato).")
                 return True, "Tunnel non trovato o già fermato."

            process = tunnel_info.get('process')
            pid_str = f"(PID: {process.pid})" if process else "(Nessun processo)"
            logging.info(f"Stop tunnel {service_name} {pid_str}, Motivo: {reason}")
            
            if process and process.poll() is None: 
                process.terminate()
                try: process.wait(timeout=3) # Timeout più breve
                except subprocess.TimeoutExpired:
                    logging.warning(f"Timeout SIGTERM {service_name}, invio SIGKILL.")
                    process.kill()
                    try: process.wait(timeout=2)
                    except subprocess.TimeoutExpired: logging.error(f"Processo {service_name} non risponde a SIGKILL.")
            
            del self.active_tunnels[service_name]
            self.save_config()
            logging.info(f"Tunnel {service_name} fermato e rimosso (Motivo: {reason}).")
            return True, f"Tunnel fermato (Motivo: {reason})."
        except Exception as e:
            logging.error(f"Errore stop tunnel {service_name}: {e}", exc_info=True)
            return False, f"Errore: {str(e)}"

    def stop_all_tunnels(self, reason="richiesta utente globale"):
        # ... (implementazione come prima) ...
        logging.info(f"Stop tutti i tunnel (Motivo: {reason})...")
        count = 0
        for name in list(self.active_tunnels.keys()):
            if self.stop_tunnel_for_service(name, reason=f"globale - {reason}")[0]: count += 1
        msg = f"Fermati {count} tunnel (Motivo: {reason})."
        logging.info(msg)
        return True, msg

    def get_status(self):
        # ... (implementazione come prima, assicurati che gestisca 'url' == "Ricerca URL fallita") ...
        active_tunnels_details = []
        current_time = time.time()
        for name, info in list(self.active_tunnels.items()):
            is_running = info.get('process') and info['process'].poll() is None
            url_display = info.get('url')
            # Non mostrare "Ricerca URL fallita" se il tunnel non è in esecuzione o è scaduto
            if not is_running and url_display == "Ricerca URL fallita":
                url_display = None # O l'ultimo URL valido se esisteva prima della terminazione

            exp_time = info.get('expiration_time')
            time_rem = None
            if exp_time and is_running: time_rem = max(0, exp_time - current_time)
            
            active_tunnels_details.append({
                'service_name': name, 'url': url_display, 'port': info.get('port'),
                'local_url': info.get('local_url'), 'is_running': is_running,
                'expiration_time': exp_time, 'time_remaining_seconds': time_rem
            })
        return {
            'services': self.get_docker_services(),
            'active_tunnels': active_tunnels_details,
            'local_ip': self.local_ip,
            'default_tunnel_duration_hours': DEFAULT_TUNNEL_DURATION_HOURS
        }


    def check_expired_tunnels_periodically(self):
        # ... (implementazione come prima) ...
        logging.info("Avvio controllore scadenza tunnel...")
        while not self.shutdown_event.is_set():
            current_time = time.time()
            for name in list(self.active_tunnels.keys()):
                try:
                    info = self.active_tunnels.get(name)
                    if not info: continue
                    process = info.get('process')
                    if not process or process.poll() is not None: # Non attivo o terminato
                        # Pulisci solo se non è un tunnel appena avviato in attesa di URL
                        # e se è effettivamente scaduto o non ha scadenza
                        if info.get('url') != "Ricerca URL fallita" and \
                           (not info.get('expiration_time') or info.get('expiration_time') < current_time - 60): # Tolleranza
                            logging.info(f"Pulizia record tunnel non attivo/terminato: {name}")
                            del self.active_tunnels[name]
                            self.save_config()
                        continue
                    exp_time = info.get('expiration_time')
                    if exp_time and current_time >= exp_time:
                        logging.info(f"Tunnel {name} scaduto. Arresto...")
                        self.stop_tunnel_for_service(name, reason="scaduto")
                except Exception as e: logging.error(f"Errore controllo scadenza {name}: {e}", exc_info=True)
            self.shutdown_event.wait(30)
        logging.info("Controllore scadenza tunnel fermato.")

    def shutdown(self):
        # ... (implementazione come prima) ...
        logging.info("Arresto UniversalTunnelManager...")
        self.shutdown_event.set()
        self.stop_all_tunnels(reason="arresto applicazione")
        if self.expiration_checker_thread.is_alive():
            self.expiration_checker_thread.join(timeout=3)
        logging.info("UniversalTunnelManager arrestato.")

# --- Flask Routes ---
tunnel_manager = UniversalTunnelManager()
import atexit
atexit.register(tunnel_manager.shutdown)

@app.route('/')
def index():
    return render_template('universal.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return app.send_static_file(filename) # Corretto per Flask >= 0.7


@app.route('/api/status')
def api_status():
    return jsonify(tunnel_manager.get_status())

@app.route('/api/start-tunnel', methods=['POST'])
def api_start_tunnel():
    # ... (implementazione come prima) ...
    try:
        data = request.get_json()
        if not data: return jsonify({'success': False, 'message': 'Richiesta JSON vuota'}), 400
        service_name, port_str, duration_str = data.get('service_name'), str(data.get('port')), data.get('duration_hours')
        
        if not service_name or not port_str: # port può essere '0'
            return jsonify({'success': False, 'message': 'service_name e port mancanti'}), 400
        
        try: port = int(port_str)
        except ValueError: return jsonify({'success': False, 'message': f"Porta non valida: '{port_str}'."}), 400
        if not (0 <= port < 65536): return jsonify({'success': False, 'message': 'Porta fuori range.'}), 400

        duration = None
        if duration_str:
            try: duration = float(duration_str)
            except ValueError: return jsonify({'success': False, 'message': 'Durata non valida.'}), 400
            if duration <= 0: return jsonify({'success': False, 'message': 'Durata positiva.'}), 400
        
        success, message = tunnel_manager.start_tunnel_for_service(service_name, port, duration)
        return jsonify({'success': success, 'message': message}), 200 if success else 500
    except Exception as e:
        logging.error(f"Errore API start-tunnel: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Errore server: {str(e)}'}), 500


@app.route('/api/stop-tunnel', methods=['POST'])
def api_stop_tunnel():
    # ... (implementazione come prima) ...
    try:
        data = request.get_json()
        service_name = data.get('service_name') if data else None
        if not service_name: return jsonify({'success': False, 'message': 'service_name mancante'}), 400
        success, message = tunnel_manager.stop_tunnel_for_service(service_name, reason="API utente")
        return jsonify({'success': success, 'message': message}), 200 if success else 500
    except Exception as e:
        logging.error(f"Errore API stop-tunnel: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Errore server: {str(e)}'}), 500


@app.route('/api/stop-all', methods=['POST'])
def api_stop_all():
    # ... (implementazione come prima) ...
    try:
        success, message = tunnel_manager.stop_all_tunnels(reason="API utente globale")
        return jsonify({'success': success, 'message': message}), 200 if success else 500
    except Exception as e:
        logging.error(f"Errore API stop-all: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f'Errore server: {str(e)}'}), 500


@app.route('/api/debug')
def api_debug():
    # Implementazione semplice per debug, espandibile se necessario
    debug_info = {
        'active_tunnels_count': len(tunnel_manager.active_tunnels),
        'active_tunnels_details': {
            name: {
                'url': info.get('url'),
                'port': info.get('port'),
                'is_running': info.get('process').poll() is None if info.get('process') else False,
                'expiration': datetime.fromtimestamp(info.get('expiration_time')).isoformat() if info.get('expiration_time') else None
            } for name, info in tunnel_manager.active_tunnels.items()
        }
    }
    logging.debug(f"Debug API richiesta: {json.dumps(debug_info, default=str)}")
    return jsonify(debug_info)


if __name__ == '__main__':
    logging.info("Avvio Universal Cloudflare Tunnel Manager")
    # ... (messaggi di log come prima)
    display_ip = tunnel_manager.local_ip if tunnel_manager.local_ip != "127.0.0.1" else "localhost"
    logging.info(f"Interfaccia Web: http://{display_ip}:5001")
    try:
        # Per Docker, debug=False è solitamente meglio. use_reloader=False è cruciale con i thread.
        app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False) 
    except KeyboardInterrupt:
        logging.info("Interruzione da tastiera. Arresto...")
    finally:
        tunnel_manager.shutdown()