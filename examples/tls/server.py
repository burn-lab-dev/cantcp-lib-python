r"""TLS 1.3 cantcp server example with mutual TLS.

The server accepts one client at a time, prints the frames it receives and
answers each of them with a frame carrying the same identifier. Only clients
presenting a certificate signed by the configured CA may connect.

Generate the certificates first, for example with the OpenSSL commands from
the cantcp documentation (``docs/TLS-KEYS.md``):

.. code-block:: console

    $ openssl ecparam -name prime256v1 -genkey -noout -out ca-key.pem
    $ openssl req -new -x509 -days 3650 -key ca-key.pem -out ca.pem \
        -subj "/CN=cantcp local CA" \
        -addext "basicConstraints=critical,CA:TRUE" \
        -addext "keyUsage=critical,keyCertSign,cRLSign"
    $ openssl ecparam -name prime256v1 -genkey -noout -out server-key.pem
    $ openssl req -new -key server-key.pem -out server.csr -subj "/CN=localhost"
    $ printf 'subjectAltName = DNS:localhost, IP:127.0.0.1\n' > server-ext.cnf
    $ printf 'extendedKeyUsage = serverAuth\n' >> server-ext.cnf
    $ openssl x509 -req -in server.csr -CA ca.pem -CAkey ca-key.pem \
        -CAcreateserial -days 825 -out server.pem -extfile server-ext.cnf
    $ openssl ecparam -name prime256v1 -genkey -noout -out client-key.pem
    $ openssl req -new -key client-key.pem -out client.csr -subj "/CN=cantcp-client"
    $ printf 'extendedKeyUsage = clientAuth\n' > client-ext.cnf
    $ openssl x509 -req -in client.csr -CA ca.pem -CAkey ca-key.pem \
        -CAcreateserial -days 825 -out client.pem -extfile client-ext.cnf

Run:

.. code-block:: console

    $ python examples/tls/server.py --cert server.pem --key server-key.pem --ca ca.pem
"""

from __future__ import annotations

import argparse
import socket
import ssl

import cantcp


def parse_args() -> argparse.Namespace:
    """Parse the command line arguments."""
    parser = argparse.ArgumentParser(description="cantcp TLS 1.3 server example (mutual TLS)")
    parser.add_argument("--host", default="", help="listen host")
    parser.add_argument("--port", type=int, default=29536, help="listen port")
    parser.add_argument("--cert", default="server.pem", help="server certificate")
    parser.add_argument("--key", default="server-key.pem", help="server key")
    parser.add_argument("--ca", default="ca.pem", help="CA used to verify client certificates")
    return parser.parse_args()


def build_context(cert: str, key: str, ca: str) -> ssl.SSLContext:
    """Build the TLS 1.3 server context: client certificates are required."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.load_cert_chain(cert, key)
    context.load_verify_locations(ca)
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def serve(conn: ssl.SSLSocket, addr: tuple[str, int]) -> None:
    """Serve one client: print the frames and answer each of them."""
    peer = conn.getpeercert()
    subject = dict(item[0] for item in peer["subject"]) if peer else None
    print(f"client {addr}: TLS {conn.version()}, subject {subject}")
    encoder = cantcp.Encoder(conn)
    for frame in cantcp.Decoder(conn):
        print(f"frame {frame}")
        reply = cantcp.Frame(type=frame.type, id=frame.id, data=b"\x01\x02")
        encoder.encode_frame(reply)


def main() -> None:
    """Run the example server."""
    args = parse_args()
    context = build_context(args.cert, args.key, args.ca)
    with socket.create_server((args.host, args.port)) as listener:
        print(f"listening on {listener.getsockname()}: TLS 1.3, client certificates required")
        while True:
            raw, addr = listener.accept()
            with context.wrap_socket(raw, server_side=True) as conn:
                serve(conn, addr)


if __name__ == "__main__":
    main()
