#!/usr/bin/env python
import sys
import os

# Add A&A directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'A&A'))

from app import create_app

if __name__ == '__main__':
    app = create_app()
    import socket
    hostname = socket.gethostname()
    ip_addr = socket.gethostbyname(hostname)
    print("\n" + "="*60)
    print("🎮 Arcade Application Starting...")
    print("="*60)
    print("\n✨ Local Access:  http://127.0.0.1:5000")
    print(f"🌐 Network Access: http://{ip_addr}:5000")
    print("📱 Press Ctrl+C to stop the server\n")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
