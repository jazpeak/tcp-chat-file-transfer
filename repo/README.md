# Multi-Client Chat & File Transfer over Raw TCP

A multi-threaded client–server application in pure Python (standard library only) supporting private messaging, broadcast, server-side file storage, and relayed peer-to-peer file transfer — built on raw TCP sockets with a custom text-based application-layer protocol.

## Features

- **Concurrent clients** via a thread-per-connection server
- **Authentication** (`LOGIN`) with duplicate-session detection
- **Private messages** and **broadcast** to all connected users
- **File upload / download** to a server-side store
- **Peer-to-peer file send** relayed through the server (`SEND`)
- **Custom protocol** with newline-terminated text commands and explicit byte-length framing for binary data ([spec](docs/PROTOCOL.md))
- **Benchmark suite** measuring RTT, broadcast latency, and multi-client download throughput

## Tech

Python 3 · `socket` · `threading` · no third-party dependencies

## Project Structure

```
.
├── src/
│   ├── server.py        # Threaded TCP server
│   └── client.py        # Interactive client with background listener thread
├── tests/
│   └── benchmark.py     # RTT / broadcast / throughput benchmarks
└── docs/
    ├── PROTOCOL.md      # Application-layer protocol specification
    └── REPORT.md        # Design & implementation write-up
```

## Quick Start

Run everything from the repository root.

```bash
# Terminal 1 – server (listens on 127.0.0.1:5000)
python3 src/server.py

# Terminal 2 and 3 – clients
python3 src/client.py
```

Enter any username/password when prompted (new usernames are registered on first login, e.g. `alice` / `123`).

### Client commands

| Command | Description |
|---|---|
| `MSG <user> <text>` | Private message |
| `BROADCAST <text>` | Message everyone else |
| `LIST` | Show online users |
| `UPLOAD <file>` | Upload a file to the server |
| `DOWNLOAD <file>` | Download a file from the server |
| `SEND <user> <file>` | Send a file to another user via the server |
| `LOGOUT` | Disconnect |

Each client gets a private folder (e.g. `alice_data/`) created on login. Place files there before using `UPLOAD`/`SEND`; downloads and received files land there too. The folder is deleted on exit.

### Benchmarks

With the server running:

```bash
python3 tests/benchmark.py
```

Runs: (1) single-client round-trip time, (2) broadcast latency across 5 clients, (3) throughput with 10 concurrent clients downloading 1 MB, 100 MB, and 1 GB files. The 1 GB test needs ~1 GB free disk space in `server_data/`.

### Sample results (localhost loopback, my machine)

| Test | Result |
|---|---|
| Single-client RTT | ~0.03 ms |
| Broadcast to 5 clients (avg) | ~0.3 ms |
| 10 clients × 100 MB download | ~580 MB/s aggregate |

Loopback numbers reflect server/threading overhead, not real network conditions; your figures will vary.

## How It Works

TCP is a byte stream with no message boundaries, so the protocol frames data in two ways:

1. **Control messages** are UTF-8 text lines terminated by `\n`.
2. **File data** is preceded by a header carrying the exact byte count; the receiver reads exactly that many bytes, then resumes parsing text.

Shared server state (the active-user table) is guarded by a `threading.Lock`. See [`docs/REPORT.md`](docs/REPORT.md) for the full design discussion and [`docs/PROTOCOL.md`](docs/PROTOCOL.md) for message formats and sequence diagrams.

## Known Limitations / Future Work

This was built as a networking exercise, so it deliberately favors clarity over production hardening. Things I'd improve next:

- **Security:** passwords are sent and stored in plaintext in memory and there is no TLS; filenames are not sanitized (path traversal risk on upload/download). Next step: TLS via `ssl`, salted password hashing, filename validation.
- **Framing robustness:** commands are read with a single `recv()`, so two commands arriving in one segment, or a command arriving together with file bytes, can be mishandled. Next step: a buffered line reader shared by all code paths.
- **Persistence:** users are registered in memory on first login and are lost on server restart.
- **Concurrency model:** thread-per-connection is simple but won't scale to thousands of clients; `asyncio` or `selectors` would.
- **Client UX:** uploads use a short `sleep` instead of waiting for the server's `OK UPLOAD_READY`; the `LIST` reply is plain lines rather than `LIST_RESULT <count>` as the spec describes.

## Author

Jazl Anwar

## License

[MIT](LICENSE)
