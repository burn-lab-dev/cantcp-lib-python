r"""TLS 1.3 cantcp client example with mutual TLS.

The client verifies the server certificate against the CA, presents its own
certificate, sends one frame and prints the reply. Generate the certificates
first: see the header of ``examples/tls/server.py`` or the cantcp
documentation (``docs/TLS-KEYS.md``).

Run (the example server must be listening):

.. code-block:: console

    $ python examples/tls/client.py --host localhost --port 29536 \
        --cert client.pem --key client-key.pem --ca ca.pem
"""

from __future__ import annotations

import argparse
import socket
import ssl

import cantcp

# The handshake and the exchange must not hang forever.
TIMEOUT_SECONDS = 10


def parse_args() -> argparse.Namespace:
    """Parse the command line arguments."""
    parser = argparse.ArgumentParser(description="cantcp TLS 1.3 client example (mutual TLS)")
    parser.add_argument("--host", default="localhost", help="server host")
    parser.add_argument("--port", type=int, default=29536, help="server port")
    parser.add_argument(
        "--server-name", default="localhost", help="name verified against the server certificate"
    )
    parser.add_argument("--cert", default="client.pem", help="client certificate")
    parser.add_argument("--key", default="client-key.pem", help="client key")
    parser.add_argument("--ca", default="ca.pem", help="CA used to verify the server certificate")
    return parser.parse_args()


def build_context(cert: str, key: str, ca: str) -> ssl.SSLContext:
    """Build the TLS 1.3 client context: verify the server and present a certificate."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.load_verify_locations(ca)
    context.load_cert_chain(cert, key)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def main() -> None:
    """Run the example client."""
    args = parse_args()
    context = build_context(args.cert, args.key, args.ca)
    with (
        socket.create_connection((args.host, args.port), timeout=TIMEOUT_SECONDS) as raw,
        context.wrap_socket(raw, server_hostname=args.server_name) as conn,
    ):
        peer = conn.getpeercert()
        subject = dict(item[0] for item in peer["subject"]) if peer else None
        print(f"connected: TLS {conn.version()}, subject {subject}")
        frame = cantcp.Frame(type=cantcp.Type.CLASSIC, id=0x123, data=b"\x11\x22\x33")
        cantcp.Encoder(conn).encode_frame(frame)
        print(f"sent: {frame}")
        reply = next(iter(cantcp.Decoder(conn)))
        print(f"reply: {reply}")


if __name__ == "__main__":
    main()
