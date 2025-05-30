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
import yaml
import shutil
from flask import Flask, render_template, jsonify, request
import threading
import socket
from datetime import datetime, timedelta # Aggiunto per la scadenza
from pathlib import Path

app = Flask(__name__)

# Gestione password sudo
sudo_password = None

def set_sudo_password(password):
    """Imposta la password sudo per le operazioni successive"""
    global sudo_password
    sudo_password = password

def run_sudo_command(cmd, password=None):
    """Esegue un comando sudo con password"""
    global sudo_password
    if password:
        sudo_password = password
    
    if not sudo_password:
        return None, "Password sudo richiesta"
    
    try:
        # Usa echo per passare la password a sudo
        echo_cmd = f"echo '{sudo_password}' | sudo -S {' '.join(cmd[1:])}"
        result = subprocess.run(echo_cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result, None
    except subprocess.TimeoutExpired:
        return None, "Timeout comando sudo"
    except Exception as e:
        return None, f"Errore esecuzione comando: {str(e)}"

DEFAULT_TUNNEL_DURATION_HOURS = 48 # Ore

# Configurazioni per Named Tunnels
CLOUDFLARED_CONFIG_PATH = "/etc/cloudflared/config.yml"
CLOUDFLARED_CREDENTIALS_DIR = "/home/nugh75/.cloudflared"
NAMED_TUNNEL_BACKUP_DIR = "/home/nugh75/Git/interface/tunnel-manager-data/named-tunnel-backups"

class UniversalTunnelManager:
    def __init__(self):
        self.active_tunnels = {}  # {service_name: {'process': process, 'url': url, 'port': port, 'expiration_time': timestamp, 'tunnel_type': 'quick'|'named'}}
        self.local_ip = self.get_local_ip()
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(script_dir, "data")
        self.config_file = os.path.join(self.data_dir, "tunnel_config.json")
        
        # Inizializzazione Named Tunnels - prima inizializza le variabili
        self.named_tunnel_domains = {}  # Cache per domini personalizzati {service_name: domain}
        os.makedirs(NAMED_TUNNEL_BACKUP_DIR, exist_ok=True)
        # Poi carica la configurazione
        self.named_tunnel_config = self.load_named_tunnel_config()
        
        os.makedirs(self.data_dir, exist_ok=True)
        self.load_config_and_restore_expirations() # Modificato per ripristinare le scadenze
        self.clean_invalid_urls_from_config_file()
        
        # Rilevamento automatico Named Tunnels attivi
        self.detect_active_named_tunnels()

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

    def load_named_tunnel_config(self):
        """Carica la configurazione dei Named Tunnels da config.yml"""
        try:
            if os.path.exists(CLOUDFLARED_CONFIG_PATH):
                with open(CLOUDFLARED_CONFIG_PATH, 'r') as f:
                    config = yaml.safe_load(f)
                print(f"✅ Configurazione Named Tunnel caricata da {CLOUDFLARED_CONFIG_PATH}")
                
                # Estrai informazioni sui domini configurati
                if 'ingress' in config:
                    for rule in config['ingress']:
                        if 'hostname' in rule and 'service' in rule:
                            hostname = rule['hostname']
                            service_url = rule['service']
                            # Estrai porta dal service URL (es: http://192.168.129.14:7860 -> 7860)
                            port_match = re.search(r':(\d+)$', service_url)
                            if port_match:
                                port = int(port_match.group(1))
                                # Cerca di mappare alla porta dei servizi Docker
                                self.named_tunnel_domains[hostname] = {
                                    'hostname': hostname,
                                    'service_url': service_url,
                                    'port': port
                                }
                                print(f"🌐 Dominio configurato: {hostname} -> {service_url}")
                
                return config
            else:
                print(f"⚠️ File configurazione Named Tunnel non trovato: {CLOUDFLARED_CONFIG_PATH}")
                return None
        except Exception as e:
            print(f"❌ Errore nel caricamento configurazione Named Tunnel: {e}")
            return None

    def save_named_tunnel_config(self, config):
        """Salva la configurazione dei Named Tunnels con backup"""
        global sudo_password
        try:
            if not sudo_password:
                print("❌ Password sudo richiesta per salvare la configurazione")
                return False
            
            # Crea backup della configurazione esistente
            if os.path.exists(CLOUDFLARED_CONFIG_PATH):
                backup_filename = f"config_backup_{int(time.time())}.yml"
                backup_path = os.path.join(NAMED_TUNNEL_BACKUP_DIR, backup_filename)
                
                # Usa sudo per copiare il file di configurazione nel backup
                copy_result, error = run_sudo_command(["sudo", "cp", CLOUDFLARED_CONFIG_PATH, backup_path])
                if error:
                    print(f"⚠️ Errore nel backup: {error}")
                    if "password" in error.lower():
                        sudo_password = None
                        return False
                else:
                    print(f"💾 Backup configurazione salvato: {backup_path}")
            
            # Crea un file temporaneo con la nuova configurazione
            temp_file = "/tmp/cloudflared_config_temp.yml"
            with open(temp_file, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
            # Usa sudo per spostare il file temporaneo nella posizione finale
            move_result, error = run_sudo_command(["sudo", "mv", temp_file, CLOUDFLARED_CONFIG_PATH])
            if error:
                print(f"❌ Errore nel salvataggio: {error}")
                if "password" in error.lower():
                    sudo_password = None
                    return False
                # Pulisci il file temporaneo se il move fallisce
                try:
                    os.remove(temp_file)
                except:
                    pass
                return False
            
            print(f"✅ Configurazione Named Tunnel salvata: {CLOUDFLARED_CONFIG_PATH}")
            
            # Aggiorna la cache locale
            self.named_tunnel_config = config
            return True
        except Exception as e:
            print(f"❌ Errore nel salvataggio configurazione Named Tunnel: {e}")
            return False

    def get_available_named_domains(self):
        """Restituisce i domini disponibili per Named Tunnels"""
        domains = []
        if self.named_tunnel_config and 'ingress' in self.named_tunnel_config:
            for rule in self.named_tunnel_config['ingress']:
                if 'hostname' in rule:
                    hostname = rule['hostname']
                    service_url = rule.get('service', '')
                    # Estrai porta dal service URL
                    port_match = re.search(r':(\d+)$', service_url)
                    current_port = int(port_match.group(1)) if port_match else None
                    
                    domains.append({
                        'hostname': hostname,
                        'current_service_url': service_url,
                        'current_port': current_port,
                        'available': True
                    })
        return domains

    def update_named_tunnel_ingress(self, hostname, new_port):
        """Aggiorna la configurazione ingress per un hostname specifico"""
        try:
            if not self.named_tunnel_config:
                print("❌ Nessuna configurazione Named Tunnel disponibile")
                return False
            
            new_service_url = f"http://{self.local_ip}:{new_port}"
            updated = False
            
            if 'ingress' in self.named_tunnel_config:
                for rule in self.named_tunnel_config['ingress']:
                    if rule.get('hostname') == hostname:
                        old_service_url = rule.get('service', '')
                        rule['service'] = new_service_url
                        print(f"🔄 Aggiornato {hostname}: {old_service_url} -> {new_service_url}")
                        updated = True
                        break
            
            if updated:
                return self.save_named_tunnel_config(self.named_tunnel_config)
            else:
                print(f"❌ Hostname {hostname} non trovato nella configurazione")
                return False
                
        except Exception as e:
            print(f"❌ Errore nell'aggiornamento configurazione ingress: {e}")
            return False

    def restart_named_tunnel(self):
        """Riavvia il Named Tunnel per applicare le modifiche alla configurazione"""
        global sudo_password
        try:
            if not sudo_password:
                return False, "Password sudo richiesta"
                
            print("🔄 Riavvio Named Tunnel per applicare le modifiche...")
            
            # Ferma il tunnel esistente
            stop_result, error = run_sudo_command(["sudo", "systemctl", "stop", "cloudflared"])
            if error:
                print(f"⚠️ Errore nel fermare cloudflared: {error}")
                if "password" in error.lower():
                    sudo_password = None  # Reset password se non valida
                    return False, "Password sudo non valida"
            
            time.sleep(2)  # Aspetta che il servizio si fermi
            
            # Riavvia il tunnel
            start_result, error = run_sudo_command(["sudo", "systemctl", "start", "cloudflared"])
            if error:
                print(f"❌ Errore nel riavviare cloudflared: {error}")
                if "password" in error.lower():
                    sudo_password = None  # Reset password se non valida
                    return False, "Password sudo non valida"
                return False, f"Errore riavvio: {error}"
            
            if start_result and start_result.returncode == 0:
                print("✅ Named Tunnel riavviato con successo")
                return True, "Named Tunnel riavviato con successo"
            else:
                error_msg = start_result.stderr if start_result else "Errore sconosciuto"
                print(f"❌ Errore nel riavviare cloudflared: {error_msg}")
                return False, f"Errore riavvio: {error_msg}"
                
        except Exception as e:
            print(f"❌ Errore nel riavvio Named Tunnel: {e}")
            return False, f"Errore: {str(e)}"

    def get_named_tunnel_status(self):
        """Verifica lo stato del Named Tunnel"""
        global sudo_password
        try:
            if not sudo_password:
                return {
                    'is_active': False,
                    'status': 'auth_required',
                    'details': 'Password sudo richiesta per verificare lo stato'
                }
            
            # Prima verifica se cloudflared è installato
            check_result, check_error = run_sudo_command(["which", "cloudflared"])
            if check_error or not check_result or check_result.returncode != 0:
                return {
                    'is_active': False,
                    'status': 'not_installed',
                    'details': 'cloudflared non è installato nel sistema'
                }
            
            # Controlla se il servizio systemd esiste
            exists_result, exists_error = run_sudo_command(["sudo", "systemctl", "list-unit-files", "cloudflared.service"])
            if exists_error or not exists_result or "cloudflared.service" not in exists_result.stdout:
                return {
                    'is_active': False,
                    'status': 'service_not_configured',
                    'details': 'Servizio cloudflared non configurato in systemd'
                }
            
            # Controlla lo stato del servizio systemd
            status_result, error = run_sudo_command(["sudo", "systemctl", "is-active", "cloudflared"])
            if error:
                if "password" in error.lower():
                    sudo_password = None  # Reset password se non valida
                    return {
                        'is_active': False,
                        'status': 'auth_required',
                        'details': 'Password sudo non valida'
                    }
                return {
                    'is_active': False,
                    'status': 'error',
                    'details': error
                }
            
            is_active = status_result.stdout.strip() == "active" if status_result else False
            
            # Ottieni informazioni dettagliate
            detail_result, detail_error = run_sudo_command(["sudo", "systemctl", "status", "cloudflared", "--no-pager"])
            
            return {
                'is_active': is_active,
                'status': status_result.stdout.strip() if status_result else 'unknown',
                'details': detail_result.stdout if detail_result and detail_result.returncode == 0 else (detail_result.stderr if detail_result else detail_error)
            }
        except Exception as e:
            print(f"❌ Errore nel controllo stato Named Tunnel: {e}")
            return {
                'is_active': False,
                'status': 'error',
                'details': str(e)
            }

    def detect_active_named_tunnels(self):
        """Rileva automaticamente i Named Tunnels attivi e li aggiunge ai tunnel attivi"""
        try:
            named_status = self.get_named_tunnel_status()
            
            # Verifica se il servizio è disponibile e configurato
            if named_status.get('status') in ['not_installed', 'service_not_configured', 'auth_required']:
                print(f"ℹ️ Named Tunnel non disponibile: {named_status.get('details')}")
                return
            
            if named_status.get('is_active', False):
                print("🔍 Named Tunnel attivo rilevato, mappatura servizi...")
                
                # Mappa i domini ai servizi attivi in base alle porte
                if self.named_tunnel_config and 'ingress' in self.named_tunnel_config:
                    for rule in self.named_tunnel_config['ingress']:
                        if 'hostname' in rule and 'service' in rule:
                            hostname = rule['hostname']
                            service_url = rule['service']
                            
                            # Estrai porta dal service URL
                            port_match = re.search(r':(\d+)$', service_url)
                            if port_match:
                                port = int(port_match.group(1))
                                
                                # Cerca un servizio Docker che usa questa porta
                                docker_services = self.get_docker_services()
                                matching_service = None
                                for service in docker_services:
                                    if port in service.get('ports', []):
                                        matching_service = service['name']
                                        break
                                
                                # Se trovato un servizio corrispondente, aggiungilo ai tunnel attivi
                                if matching_service:
                                    self.active_tunnels[matching_service] = {
                                        'process': None,  # Named tunnel gestito da systemd
                                        'url': f"https://{hostname}",
                                        'port': port,
                                        'local_url': service_url,
                                        'start_time': time.time(),
                                        'expiration_time': None,  # Named Tunnels non scadono
                                        'tunnel_type': 'named',
                                        'custom_domain': hostname
                                    }
                                    print(f"✅ Named Tunnel mappato: {matching_service} -> {hostname} (porta {port})")
                                else:
                                    print(f"⚠️ Nessun servizio Docker trovato per porta {port} ({hostname})")
                            
                print(f"🎯 Named Tunnels rilevati: {len([t for t in self.active_tunnels.values() if t.get('tunnel_type') == 'named'])}")
            else:
                print("ℹ️ Nessun Named Tunnel attivo rilevato")
                
        except Exception as e:
            print(f"⚠️ Errore nel rilevamento Named Tunnels attivi: {e}")

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

    def start_tunnel_for_service(self, service_name, port, duration_hours=None, tunnel_type='quick', custom_domain=None): # Aggiunto tunnel_type e custom_domain
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

            # Gestione Named Tunnel
            if tunnel_type == 'named':
                if custom_domain:
                    # Aggiorna configurazione ingress per il dominio personalizzato
                    if self.update_named_tunnel_ingress(custom_domain, port):
                        # Riavvia il Named Tunnel per applicare le modifiche
                        if self.restart_named_tunnel():
                            # I Named Tunnels non scadono come i Quick Tunnels
                            self.active_tunnels[service_name] = {
                                'process': None,  # Named tunnel gestito da systemd
                                'url': f"https://{custom_domain}",
                                'port': port,
                                'local_url': f"http://{self.local_ip}:{port}",
                                'start_time': time.time(),
                                'expiration_time': None,  # Named Tunnels non scadono
                                'tunnel_type': 'named',
                                'custom_domain': custom_domain
                            }
                            self.save_config()
                            return True, f"Named Tunnel configurato per {service_name} su {custom_domain}"
                        else:
                            return False, "Errore nel riavvio del Named Tunnel"
                    else:
                        return False, f"Errore nell'aggiornamento configurazione per {custom_domain}"
                else:
                    return False, "Dominio personalizzato richiesto per Named Tunnel"

            # Gestione Quick Tunnel (comportamento esistente)
            url_to_tunnel = f"http://{self.local_ip}:{port}"
            print(f"🚀 Avvio Quick Tunnel per {service_name} verso {url_to_tunnel}")
            
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
                'expiration_time': expiration_time, # Memorizza il timestamp di scadenza
                'tunnel_type': 'quick'  # Indica che è un Quick Tunnel
            }
            
            print(f"⏱️  Quick Tunnel per {service_name} scadrà il: {datetime.fromtimestamp(expiration_time).strftime('%Y-%m-%d %H:%M:%S')}")

            threading.Thread(
                target=self.capture_tunnel_url,
                args=(service_name, process),
                daemon=True
            ).start()
            
            return True, f"Tentativo di avvio Quick Tunnel per {service_name} su porta {port} (scade in {duration_hours} ore)..."
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
            tunnel_type = info.get('tunnel_type', 'quick')
            
            # Gestione stato per Named Tunnels
            if tunnel_type == 'named':
                # Per Named Tunnels, verifichiamo lo stato del servizio systemd
                named_status = self.get_named_tunnel_status()
                is_running = named_status['is_active']
                process_status = "Named Tunnel attivo" if is_running else "Named Tunnel inattivo"
            else:
                # Gestione stato per Quick Tunnels (comportamento esistente)
                if info.get('process'):
                    if info['process'].poll() is None:
                        process_status = "Quick Tunnel in esecuzione"
                        is_running = True
                    else:
                        process_status = f"Quick Tunnel terminato (codice: {info['process'].returncode})"
            
            # Se il tunnel non è in esecuzione, non ha senso parlare di scadenza attiva
            expiration_timestamp = info.get('expiration_time') if is_running else None
            time_remaining_seconds = None
            if expiration_timestamp:
                time_remaining_seconds = expiration_timestamp - current_time
                if time_remaining_seconds < 0: # Se è scaduto ma non ancora pulito dal checker
                    time_remaining_seconds = 0 

            active_tunnels_details.append({
                'service_name': name,
                'url': info.get('url') if is_running else None,
                'port': info.get('port'),
                'local_url': info.get('local_url'),
                'process_status': process_status,
                'is_running': is_running,
                'start_time': info.get('start_time') if is_running else None,
                'expiration_time': expiration_timestamp, # Timestamp UNIX
                'time_remaining_seconds': time_remaining_seconds if expiration_timestamp else None,
                'tunnel_type': tunnel_type,
                'custom_domain': info.get('custom_domain')
            })
        
        global sudo_password
        return {
            'services': self.get_docker_services(), # Questa ora include info di scadenza parziali
            'active_tunnels': active_tunnels_details,
            'active_tunnels_count': len([t for t in active_tunnels_details if t['is_running']]),
            'local_ip': self.local_ip,
            'default_tunnel_duration_hours': DEFAULT_TUNNEL_DURATION_HOURS,
            'named_tunnel_config': self.named_tunnel_config,
            'available_domains': self.get_available_named_domains(),
            'named_tunnel_status': self.get_named_tunnel_status(),
            'sudo_available': sudo_password is not None,
            'admin_required': True  # Named Tunnels richiedono sempre privilegi admin
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
        tunnel_type = data.get('tunnel_type', 'quick')  # 'quick' o 'named'
        custom_domain = data.get('custom_domain')  # Per Named Tunnels
        
        if not service_name or not port_str:
            return jsonify({'success': False, 'message': 'Parametri mancanti: service_name e port sono richiesti'}), 400
        
        try:
            port = int(port_str)
            if not (0 < port < 65536):
                raise ValueError("Porta non valida")
        except ValueError:
            return jsonify({'success': False, 'message': f"Porta non valida: '{port_str}'."}), 400

        # Validazione per Named Tunnels
        if tunnel_type == 'named' and not custom_domain:
            return jsonify({'success': False, 'message': 'Dominio personalizzato richiesto per Named Tunnel'}), 400

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
            
        success, message = tunnel_manager.start_tunnel_for_service(
            service_name, port, duration_hours, tunnel_type, custom_domain
        )
        status_code = 200 if success else 500
        if not success and ("già attivo" in message or "aggiornata" in message):
             status_code = 200 # Se è già attivo e abbiamo aggiornato la scadenza, è un successo
        elif not success:
             status_code = 409 if "già attivo" in message else 500

        return jsonify({'success': success, 'message': message}), status_code
    except Exception as e:
        print(f"Errore imprevisto in api_start_tunnel: {e}")
        return jsonify({'success': False, 'message': f'Errore server: {str(e)}'}), 500

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

@app.route('/api/named-tunnels/domains', methods=['GET'])
def api_get_named_domains():
    """API per ottenere i domini disponibili per Named Tunnels"""
    try:
        domains = tunnel_manager.get_available_named_domains()
        return jsonify({
            'success': True, 
            'domains': domains,
            'named_tunnel_status': tunnel_manager.get_named_tunnel_status()
        })
    except Exception as e:
        print(f"Errore in api_get_named_domains: {e}")
        return jsonify({'success': False, 'message': f'Errore server: {str(e)}'}), 500

@app.route('/api/named-tunnels/restart', methods=['POST'])
def api_restart_named_tunnel():
    """API per riavviare il Named Tunnel"""
    try:
        success = tunnel_manager.restart_named_tunnel()
        return jsonify({
            'success': success, 
            'message': 'Named Tunnel riavviato con successo' if success else 'Errore nel riavvio Named Tunnel'
        })
    except Exception as e:
        print(f"Errore in api_restart_named_tunnel: {e}")
        return jsonify({'success': False, 'message': f'Errore server: {str(e)}'}), 500

@app.route('/api/named-tunnels/status', methods=['GET'])
def api_named_tunnel_status():
    """API per ottenere lo stato del Named Tunnel"""
    try:
        status = tunnel_manager.get_named_tunnel_status()
        return jsonify({'success': True, 'status': status})
    except Exception as e:
        print(f"Errore in api_named_tunnel_status: {e}")
        return jsonify({'success': False, 'message': f'Errore server: {str(e)}'}), 500

@app.route('/api/named-tunnels/update-ingress', methods=['POST'])
def api_update_named_tunnel_ingress():
    """API per aggiornare la configurazione ingress di un Named Tunnel"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Richiesta JSON non valida'}), 400
            
        hostname = data.get('hostname')
        port = data.get('port')
        
        if not hostname or not port:
            return jsonify({'success': False, 'message': 'Parametri mancanti: hostname e port richiesti'}), 400
        
        try:
            port = int(port)
            if not (0 < port < 65536):
                raise ValueError("Porta non valida")
        except ValueError:
            return jsonify({'success': False, 'message': f"Porta non valida: {port}"}), 400
        
        success = tunnel_manager.update_named_tunnel_ingress(hostname, port)
        return jsonify({
            'success': success,
            'message': f'Configurazione aggiornata per {hostname}' if success else 'Errore nell\'aggiornamento'
        })
    except Exception as e:
        print(f"Errore in api_update_named_tunnel_ingress: {e}")
        return jsonify({'success': False, 'message': f'Errore server: {str(e)}'}), 500
        

@app.route('/api/set-sudo-password', methods=['POST'])
def api_set_sudo_password():
    """API per impostare la password sudo"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'message': 'Richiesta JSON non valida'}), 400
            
        password = data.get('password')
        if not password:
            return jsonify({'success': False, 'message': 'Password richiesta'}), 400
        
        # Test della password con un comando semplice
        test_result, error = run_sudo_command(["sudo", "echo", "test"], password)
        if error:
            return jsonify({'success': False, 'message': 'Password sudo non valida'}), 401
        
        set_sudo_password(password)
        return jsonify({'success': True, 'message': 'Password sudo impostata con successo'})
    except Exception as e:
        print(f"Errore in api_set_sudo_password: {e}")
        return jsonify({'success': False, 'message': f'Errore server: {str(e)}'}), 500

@app.route('/api/sudo-status', methods=['GET'])
def api_sudo_status():
    """API per verificare se la password sudo è impostata"""
    global sudo_password
    return jsonify({
        'sudo_available': sudo_password is not None,
        'message': 'Password sudo configurata' if sudo_password else 'Password sudo richiesta'
    })

if __name__ == '__main__':
    print("🚀 Avvio Universal Cloudflare Tunnel Manager con Scadenza")
    host_ip_for_display = tunnel_manager.local_ip if tunnel_manager.local_ip != "127.0.0.1" else "localhost"
    print(f"🐍 Versione Python: {socket.sys.version}")
    print(f"📦 Percorso script: {os.path.dirname(os.path.abspath(__file__))}")
    print(f"🏠 Directory dati: {tunnel_manager.data_dir}")
    print(f"⚙️ File configurazione: {tunnel_manager.config_file}")
    print(f"⏱️ Durata tunnel default: {DEFAULT_TUNNEL_DURATION_HOURS} ore")
    port = int(os.environ.get('FLASK_PORT', 5001))
    print(f"🖥️  Interfaccia Web disponibile su: http://{host_ip_for_display}:{port}")
    
    # In sviluppo con thread, use_reloader=False può essere più stabile.
    # Per produzione, debug=False.
    try:
        port = int(os.environ.get('FLASK_PORT', 5001))
        app.run(host='0.0.0.0', port=port, debug=True, use_reloader=False) # use_reloader=False è importante con thread e atexit
    except KeyboardInterrupt:
        print("\n⌨️ Interruzione da tastiera ricevuta. Arresto in corso...")
    finally:
        tunnel_manager.shutdown() # Assicura che il cleanup avvenga