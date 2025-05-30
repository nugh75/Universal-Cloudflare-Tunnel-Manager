#!/usr/bin/env python3
import requests
import json

try:
    print("Testing API...")
    r = requests.get('http://127.0.0.1:5002/api/status', timeout=5)
    print(f"Status Code: {r.status_code}")
    
    if r.status_code == 200:
        data = r.json()
        print(f"sudo_available: {data.get('sudo_available')}")
        print(f"admin_required: {data.get('admin_required')}")
        print(f"named_tunnel_status: {data.get('named_tunnel_status')}")
        print(f"active_tunnels_count: {data.get('active_tunnels_count')}")
    else:
        print(f"Error: {r.text}")
        
except requests.exceptions.ConnectionError:
    print("Connection refused - server not running")
except Exception as e:
    print(f"Error: {e}")
