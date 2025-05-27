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

app = Flask(__name__)

class UniversalTunnelManager:
    def __init__(self):
        self.active_tunnels = {}  # {service_name: {'process': process, 'url': url, 'port': port}}
        self.local_ip = self.get_local_ip()
        self.config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tunnel_config.json")
        
        # Crea la directory data se non esiste
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        
        # Carica la configurazione salvata se esiste
        self.load_config()
        
    def save_config(self):
        """Salva la configurazione su file"""
        config = {
            'timestamp': time.time(),
            'tunnels': {
                name: {
                    'url': info.get('url'),
                    'port': info.get('port')
                } for name, info in self.active_tunnels.items() if 'process' in info
            }
        }
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"Configurazione salvata in: {self.config_file}")
        except Exception as e:
            print(f"Errore nel salvataggio della configurazione: {e}")
            
    def load_config(self):
        """Carica la configurazione da file"""
        if not os.path.exists(self.config_file):
            print(f"File di configurazione non trovato: {self.config_file}")
            return
            
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                
            # Nota: non ripristiniamo i processi, solo le informazioni sui tunnel
            print(f"Configurazione caricata da: {self.config_file}")
            print(f"Tunnel precedentemente configurati: {len(config.get('tunnels', {}))}")
        except Exception as e:
            print(f"Errore nel caricamento della configurazione: {e}")
        
    def get_local_ip(self):
        """Ottiene l'IP locale"""
        try:
            # Prova prima la variabile di ambiente (per Docker)
            env_ip = os.environ.get('LOCAL_IP')
            if env_ip:
                print(f"🔍 Usando IP da variabile d'ambiente: {env_ip}")
                return env_ip
            
            # Metodo per container Docker
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                ip = result.stdout.strip().split()[0]
                print(f"🔍 IP rilevato da hostname -I: {ip}")
                return ip
            
            # Fallback per host locale
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            print(f"🔍 IP rilevato da socket: {ip}")
            return ip
        except Exception as e:
            print(f"⚠️ Errore nel rilevamento dell'IP locale: {e}, usando localhost")
            return "localhost"
        
    def get_docker_services(self):
        """Ottiene la lista di tutti i servizi Docker con porte esposte"""
        try:
            # Stampa debug informazioni prima di eseguire il comando
            print(f"🔍 Ricerca servizi Docker in corso... IP Locale: {self.local_ip}")
            
            # Comando più verboso per il debug
            cmd = ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}\t{{.Ports}}\t{{.Image}}"]
            print(f"🔍 Esecuzione comando: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Debug output completo
            print(f"🔍 Output completo del comando: \n{result.stdout}")
            
            services = []
            if result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                print(f"🔍 Servizi trovati (totale): {len(lines)}")
                
                for line in lines:
                    parts = line.split('\t')
                    print(f"🔍 Analisi servizio: {line}")
                    
                    if len(parts) >= 3:
                        name = parts[0]
                        status = parts[1]
                        ports = parts[2]
                        image = parts[3] if len(parts) > 3 else "unknown"
                        
                        # Estrae le porte esposte
                        exposed_ports = self.extract_ports(ports)
                        
                        # Debug porte esposte
                        print(f"🔍 Servizio {name}: Stato={status}, Porte={exposed_ports}")
                        
                        # Includi anche i container senza porte esposte ma attivi
                        # if exposed_ports and "Up" in status:
                        if "Up" in status:  # Includi tutti i container attivi
                            services.append({
                                'name': name,
                                'status': status,
                                'ports': exposed_ports,
                                'image': image,
                                'tunnel_active': name in self.active_tunnels,
                                'tunnel_url': self.active_tunnels.get(name, {}).get('url')
                            })
            
            print(f"🔍 Servizi validi trovati: {len(services)}")
            return services
        except subprocess.CalledProcessError as e:
            print(f"❌ Errore nel recupero servizi Docker: {e}")
            print(f"❌ Stderr: {e.stderr}")
            return []
        except Exception as e:
            print(f"❌ Errore generico: {str(e)}")
            return []
    
    def extract_ports(self, ports_string):
        """Estrae le porte pubbliche dalla stringa delle porte Docker"""
        if not ports_string or ports_string == "-":
            return []
        
        # Debug porte
        print(f"🔍 Analisi porte: {ports_string}")
        
        extracted_ports = []
        # Pattern per porte tipo "0.0.0.0:8080->80/tcp"
        port_pattern = r'(?:0\.0\.0\.0|::|\d+\.\d+\.\d+\.\d+):(\d+)->'
        matches = re.findall(port_pattern, ports_string)
        
        # Se non troviamo porte pubbliche, proviamo a cercare anche porte interne
        if not matches:
            internal_pattern = r'(\d+)/tcp'
            internal_matches = re.findall(internal_pattern, ports_string)
            if internal_matches:
                print(f"🔍 Trovate porte interne: {internal_matches}")
                for port in internal_matches:
                    extracted_ports.append(int(port))
        else:
            for port in matches:
                extracted_ports.append(int(port))
        
        print(f"🔍 Porte estratte: {extracted_ports}")
        return sorted(extracted_ports)
    
    def start_tunnel_for_service(self, service_name, port):
        """Avvia un tunnel Cloudflare per un servizio specifico"""
        try:
            if service_name in self.active_tunnels:
                return False, "Tunnel già attivo per questo servizio"
                
            # Avvia il processo cloudflared
            url = f"http://{self.local_ip}:{port}"
            print(f"🔍 Avvio tunnel per {service_name} verso {url}")
            
            cmd = [
                "cloudflared", "tunnel", 
                "--url", url,
                "--metrics", "localhost:9090",
                "--logfile", "/app/data/cloudflared.log",  # Aggiunge un file di log
                "--loglevel", "info"                      # Imposta un livello di log adeguato
            ]
            
            print(f"🔍 Comando cloudflared: {' '.join(cmd)}")
            
            process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Inizializza il record del tunnel
            self.active_tunnels[service_name] = {
                'process': process,
                'url': None,
                'port': port,
                'local_url': url
            }
            
            print(f"🔍 Avviato cloudflared per {service_name} su {url}")
            
            # Cattura l'URL del tunnel in un thread separato
            def capture_tunnel_url():
                try:
                    print(f"🔍 Thread di monitoraggio avviato per {service_name}")
                    output_lines = []
                    
                    # Monitora stdout per l'URL del tunnel
                    for line in iter(process.stdout.readline, ''):
                        if not line:
                            continue
                            
                        line = line.strip()
                        print(f"🔍 Cloudflared [{service_name}]: {line}")
                        output_lines.append(line)
                        
                        # Cerca URL del tunnel con vari pattern
                        if "https://" in line:
                            # Pattern specifici per l'URL
                            patterns = [
                                r'(https://[a-zA-Z0-9\-]+\.trycloudflare\.com)',
                                r'(https://[^\s]+\.cloudflare\.com)',
                                r'\|\s+(https://[^\s]+)\s+\|',
                                r'Visit it at\s+(https://[^\s]+)',
                                r'tunnel.+?(https://[^\s]+)',
                                r'(https://[^\s]+)'  # Pattern generico come fallback
                            ]
                            
                            for pattern in patterns:
                                url_match = re.search(pattern, line)
                                if url_match:
                                    # Ottieni l'URL dal gruppo di match corretto
                                    tunnel_url = url_match.group(1) if len(url_match.groups()) >= 1 else url_match.group(0)
                                    tunnel_url = tunnel_url.strip()
                                    # Rimuovi eventuali caratteri non desiderati alla fine dell'URL
                                    tunnel_url = re.sub(r'[,\.]$', '', tunnel_url)
                                    
                                    if service_name in self.active_tunnels:
                                        self.active_tunnels[service_name]['url'] = tunnel_url
                                        print(f"✅ URL tunnel per {service_name}: {tunnel_url}")
                                        # Salva la configurazione dopo aver ottenuto l'URL
                                        self.save_config()
                                        return
                    
                    # Se non troviamo l'URL in stdout, proviamo con stderr
                    for line in iter(process.stderr.readline, ''):
                        if not line:
                            continue
                            
                        line = line.strip()
                        print(f"🔍 Cloudflared stderr [{service_name}]: {line}")
                        
                        # Controlla se c'è un URL anche qui
                        if "https://" in line:
                            url_match = re.search(r'(https://[^\s]+)', line)
                            if url_match:
                                tunnel_url = url_match.group(1)
                                if service_name in self.active_tunnels:
                                    self.active_tunnels[service_name]['url'] = tunnel_url
                                    print(f"✅ URL tunnel per {service_name} (da stderr): {tunnel_url}")
                                    self.save_config()
                                    return
                    
                    # Se dopo tutte le righe ancora non abbiamo un URL, controlliamo l'output accumulato
                    if not self.active_tunnels.get(service_name, {}).get('url'):
                        print(f"⚠️ Non è stato trovato un URL per {service_name} nell'output di cloudflared")
                        
                        # Fallback: controlla se ci sono altre righe con "https://"
                        for line in output_lines:
                            if "https://" in line:
                                url_match = re.search(r'(https://[^\s]+)', line)
                                if url_match:
                                    tunnel_url = url_match.group(1).strip()
                                    if service_name in self.active_tunnels:
                                        self.active_tunnels[service_name]['url'] = tunnel_url
                                        print(f"✅ URL tunnel per {service_name} (fallback): {tunnel_url}")
                                        self.save_config()
                                        return
                        
                        print(f"❌ Impossibile trovare l'URL del tunnel per {service_name}")
                except Exception as e:
                    print(f"❌ Errore nel thread di monitoraggio per {service_name}: {e}")
            
            # Avvia il thread di monitoraggio
            capture_thread = threading.Thread(target=capture_tunnel_url, daemon=True)
            capture_thread.start()
            
            return True, "Tunnel avviato, recupero URL in corso..."
        except Exception as e:
            print(f"❌ Errore nell'avvio del tunnel per {service_name}: {e}")
            return False, f"Errore nell'avvio del tunnel: {str(e)}"
    
    def stop_tunnel_for_service(self, service_name):
        """Ferma il tunnel per un servizio specifico"""
        try:
            if service_name not in self.active_tunnels:
                return False, "Nessun tunnel attivo per questo servizio"
            
            tunnel_info = self.active_tunnels[service_name]
            process = tunnel_info['process']
            
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            
            # Rimuove il tunnel dalla lista attiva
            del self.active_tunnels[service_name]
            print(f"🔌 Tunnel per {service_name} fermato")
            
            return True, "Tunnel fermato con successo"
        except Exception as e:
            print(f"Errore nel fermare il tunnel per {service_name}: {e}")
            return False, str(e)
    
    def stop_all_tunnels(self):
        """Ferma tutti i tunnel attivi"""
        try:
            services_to_stop = list(self.active_tunnels.keys())
            for service_name in services_to_stop:
                self.stop_tunnel_for_service(service_name)
            
            # Cleanup di eventuali processi cloudflared rimasti
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if 'cloudflared' in proc.info['name']:
                        proc.kill()
                        print(f"🔌 Processo cloudflared {proc.info['pid']} terminato")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            return True, "Tutti i tunnel fermati con successo"
        except Exception as e:
            print(f"Errore nel fermare tutti i tunnel: {e}")
            return False, str(e)
    
    def get_status(self):
        """Restituisce lo stato di tutti i servizi e tunnel"""
        return {
            'services': self.get_docker_services(),
            'active_tunnels_count': len(self.active_tunnels),
            'local_ip': self.local_ip
        }

# Istanza globale del manager
tunnel_manager = UniversalTunnelManager()

@app.route('/')
def index():
    """Pagina principale"""
    return render_template('universal.html')

@app.route('/api/status')
def api_status():
    """API per ottenere lo stato di tutti i servizi"""
    return jsonify(tunnel_manager.get_status())

@app.route('/api/start-tunnel', methods=['POST'])
def api_start_tunnel():
    """API per avviare un tunnel per un servizio specifico"""
    try:
        data = request.get_json()
        service_name = data.get('service_name')
        port = data.get('port')
        
        if not service_name or not port:
            return jsonify({'success': False, 'message': 'Parametri mancanti'})
        
        success, message = tunnel_manager.start_tunnel_for_service(service_name, port)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/stop-tunnel', methods=['POST'])
def api_stop_tunnel():
    """API per fermare un tunnel per un servizio specifico"""
    try:
        data = request.get_json()
        service_name = data.get('service_name')
        
        if not service_name:
            return jsonify({'success': False, 'message': 'Nome servizio mancante'})
        
        success, message = tunnel_manager.stop_tunnel_for_service(service_name)
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/stop-all', methods=['POST'])
def api_stop_all():
    """API per fermare tutti i tunnel"""
    try:
        success, message = tunnel_manager.stop_all_tunnels()
        return jsonify({'success': success, 'message': message})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/debug', methods=['GET'])
def api_debug():
    """API per debug - mostra info sui processi"""
    try:
        debug_info = {
            'active_tunnels': len(tunnel_manager.active_tunnels),
            'tunnel_details': {}
        }
        
        # Dettagli sui tunnel attivi
        for service_name, tunnel_info in tunnel_manager.active_tunnels.items():
            debug_info['tunnel_details'][service_name] = {
                'port': tunnel_info['port'],
                'url': tunnel_info['url'],
                'local_url': tunnel_info['local_url'],
                'process_running': tunnel_info['process'] and tunnel_info['process'].poll() is None
            }
        
        # Controlla processi cloudflared attivi
        cloudflared_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if 'cloudflared' in proc.info['name']:
                    cloudflared_processes.append({
                        'pid': proc.info['pid'],
                        'cmdline': ' '.join(proc.info['cmdline'])
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        debug_info['cloudflared_processes'] = cloudflared_processes
        
        # Controlla container Docker
        try:
            docker_result = subprocess.run(
                ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
                capture_output=True, text=True, check=True
            )
            debug_info['docker_containers'] = docker_result.stdout
        except Exception as e:
            debug_info['docker_error'] = str(e)
        
        return jsonify(debug_info)
    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    print("🚀 Avvio Tunnel Manager per Open WebUI")
    print("📱 Interfaccia disponibile su: http://localhost:5001")
    app.run(host='0.0.0.0', port=5002, debug=True)
