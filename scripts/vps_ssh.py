#!/usr/bin/env python3
"""SSH al VPS Oracle Cloud y ejecuta comandos."""
import paramiko
import sys

HOST = "136.248.64.170"
USER = "opc"
KEY_PATH = "/tmp/leadx_vps.key"

def run(cmd, timeout=30):
    """Ejecuta comando via SSH."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(HOST, username=USER, key_filename=KEY_PATH, timeout=15)
    except Exception as e:
        print(f"❌ SSH connect failed: {e}", file=sys.stderr)
        return None
    
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        exit_code = stdout.channel.recv_exit_status()
        if out:
            print(out, end="")
        if err:
            print(err, end="", file=sys.stderr)
        return exit_code
    finally:
        client.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 vps_ssh.py 'comando'")
        sys.exit(1)
    cmd = sys.argv[1]
    rc = run(cmd)
    sys.exit(rc if rc is not None else 1)
