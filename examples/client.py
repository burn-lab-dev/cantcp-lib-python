r"""A cantcp client example: listen to frames, send one, read the statistics.

The client talks to a cantcp server (the ``cantcpd`` daemon, see
https://github.com/burn-lab-dev/cantcp): it opens a plain TCP or TLS 1.3
connection, wraps the socket into binary streams and drives the cantcp
codec.

Run against a local plain daemon:

.. code-block:: console

    $ python examples/client.py listen --count 5
    $ python examples/client.py send --id 123 --data 11223344

With TLS and a client certificate (see the cantcp documentation,
``docs/TLS-KEYS.md``):

.. code-block:: console

    $ python examples/client.py listen --tls --tls-ca ca.pem \
        --tls-cert client.pem --tls-key client-key.pem --count 5
    $ python examples/client.py send --id 123 --data 01 --tls \
        --tls-ca ca.pem --tls-cert client.pem --tls-key client-key.pem

The examples/tls directory contains a matching TLS server example.
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys

import cantcp

# The connection and the exchange must not hang forever.
TIMEOUT_SECONDS = 10


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line arguments."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("command", choices=["listen", "send"])
    parser.add_argument("--host", default="127.0.0.1", help="server host")
    parser.add_argument("--port", type=int, default=29536, help="server port")
    parser.add_argument(
        "--id", type=lambda value: int(value, 16), default=0, help="identifier, hex"
    )
    parser.add_argument("--data", default="", help="payload bytes, hex")
    parser.add_argument("--fd", action="store_true", help="send a CAN FD frame")
    parser.add_argument("--brs", action="store_true", help="set the CAN FD BRS flag")
    parser.add_argument("--count", type=int, default=0, help="listen: stop after n frames")
    parser.add_argument("--tls", action="store_true", help="connect over TLS 1.3")
    parser.add_argument("--tls-ca", default="", help="CA file for the server certificate")
    parser.add_argument("--tls-cert", default="", help="client certificate (mutual TLS)")
    parser.add_argument("--tls-key", default="", help="client key")
    parser.add_argument(
        "--server-name", default="localhost", help="name verified in the certificate"
    )
    return parser.parse_args(argv)


def open_connection(args: argparse.Namespace) -> socket.socket:
    """Connect to the server, over TLS 1.3 when requested."""
    raw = socket.create_connection((args.host, args.port), timeout=TIMEOUT_SECONDS)
    # The timeout guards the connect only: reading frames must block.
    raw.settimeout(None)
    if not args.tls:
        return raw
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.maximum_version = ssl.TLSVersion.TLSv1_3
    context.load_verify_locations(args.tls_ca)
    if args.tls_cert:
        context.load_cert_chain(args.tls_cert, args.tls_key)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    conn = context.wrap_socket(raw, server_hostname=args.server_name)
    conn.settimeout(None)
    return conn


def run_listen(args: argparse.Namespace) -> int:
    """Print the frames received from the server as JSON lines."""
    conn = open_connection(args)
    # buffering=0: a raw reader returns as soon as bytes are available;
    # a buffered reader blocks until the full buffer is filled.
    reader = conn.makefile("rb", buffering=0)
    for count, frame in enumerate(cantcp.Decoder(reader), start=1):
        obj = {
            "id": frame.id,
            "fd": frame.type is cantcp.Type.FD,
            "eff": frame.eff,
            "rtr": frame.rtr,
            "err": frame.err,
            "data": frame.data.hex(),
        }
        print(json.dumps(obj), flush=True)
        if args.count and count >= args.count:
            break
    reader.close()
    conn.close()
    return 0


def run_send(args: argparse.Namespace) -> int:
    """Send one frame and report it."""
    conn = open_connection(args)
    writer = conn.makefile("wb")
    frame = cantcp.Frame(type=cantcp.Type.CLASSIC, id=args.id, data=bytes.fromhex(args.data))
    if args.fd:
        frame.type = cantcp.Type.FD
        frame.brs = args.brs
    cantcp.Encoder(writer).encode_frame(frame)
    writer.flush()
    print(f"sent: {frame}")
    writer.close()
    conn.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the example client."""
    args = parse_args(argv)
    if args.command == "listen":
        return run_listen(args)
    return run_send(args)


if __name__ == "__main__":
    sys.exit(main())
