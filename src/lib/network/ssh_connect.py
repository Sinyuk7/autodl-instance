"""OpenSSH ProxyCommand: forward Git SSH over the managed HTTP CONNECT proxy."""
import argparse
import os
import select
import socket
import sys
from pathlib import Path

from src.lib.network.policy import proxy_port, read_mode


def connect(host: str, port: int, config_file: Path) -> socket.socket:
    if not 0 < port < 65536 or not host or any(c.isspace() for c in host):
        raise ValueError("Invalid SSH destination")
    if read_mode(config_file) != "on":
        return socket.create_connection((host, port), timeout=15)
    # GitHub provides SSH on 443 specifically for networks blocking port 22.
    if host.lower() == "github.com" and port == 22:
        host, port = "ssh.github.com", 443
    sock = socket.create_connection(("127.0.0.1", proxy_port()), timeout=15)
    try:
        authority = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
        sock.sendall(f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode("ascii"))
        header = bytearray()
        while not header.endswith(b"\r\n\r\n"):
            byte = sock.recv(1)
            if not byte or len(header) >= 16384:
                raise OSError("Invalid proxy CONNECT response")
            header.extend(byte)
        if bytes(header).split(b"\r\n", 1)[0].split()[1:2] != [b"200"]:
            raise OSError("Proxy refused SSH CONNECT")
        return sock
    except BaseException:
        sock.close()
        raise


def relay(sock: socket.socket) -> None:
    sock.settimeout(None)
    inputs = [sock, sys.stdin.buffer]
    while sock in inputs:
        ready, _, _ = select.select(inputs, [], [])
        for source in ready:
            data = sock.recv(65536) if source is sock else os.read(sys.stdin.fileno(), 65536)
            if not data:
                inputs.remove(source)
                if source is not sock:
                    sock.shutdown(socket.SHUT_WR)
                continue
            if source is sock:
                sys.stdout.buffer.write(data)
                sys.stdout.buffer.flush()
            else:
                sock.sendall(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-file", type=Path, required=True)
    parser.add_argument("host")
    parser.add_argument("port", type=int)
    args = parser.parse_args()
    try:
        with connect(args.host, args.port, args.config_file) as sock:
            relay(sock)
    except (OSError, ValueError) as error:
        print(f"Git SSH proxy connection failed: {error}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
