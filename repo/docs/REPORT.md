# Technical Report: Multi-Client File Transfer

**Author:** Jazl Anwar

## 1. Introduction

A multi-threaded client–server system supporting real-time text messaging, global broadcast, and file transfers (both server storage and peer-to-peer routing). The goal was to manage concurrent connections without any high-level web framework, using only raw TCP sockets to demonstrate fundamentals of network communication.

## 2. Design and Architecture

The system follows a classic client–server architecture. The server is a central hub that maintains state (active users, passwords) and routes messages.

### 2.1 System Architecture

The server uses a **thread-per-connection** model. The main loop accepts a TCP connection and immediately spawns a dedicated thread to handle all blocking socket calls for that client. If client 1 is slowly uploading a large file, client 2 can still chat without lag.

The client is also threaded: the main thread runs a blocking input loop for user commands, while a daemon thread listens for incoming chats and file transfers from the server.

## 3. Implementation Details

Implemented in Python with the built-in `socket` and `threading` modules.

### 3.1 Socket Programming Techniques

- **TCP streams:** reliable, in-order delivery for both text commands and binary file chunks.
- **Accept loop:** a `while True` around the blocking `server.accept()`; the server idles until a client connects, then hands the socket to a worker thread.
- **TCP byte framing:** TCP is a byte stream, so multiple `send()` calls can coalesce into one `recv()`. The protocol uses `\n` delimiters for text commands and explicit byte counts for binary transfers.
- **Graceful degradation:** network calls are wrapped in `try/except` to handle abrupt disconnects and `KeyboardInterrupt`.

### 3.2 Thread Synchronization

Handler threads share the dictionary of active client sockets, so a `threading.Lock` guards it. A thread acquires the lock before logging in, logging out, or broadcasting, preventing race conditions and "dictionary changed size during iteration" errors.

### 3.3 File Transfer Framing

The main challenge was separating control commands from binary file data on one byte stream. Sending a text command followed immediately by raw bytes can corrupt parsing. The protocol therefore requires the file size in the command header: the receiver parses the size, reads exactly that many bytes in a bounded loop, then returns to reading text commands.

## 4. Evaluation

`tests/benchmark.py` measures single-client RTT, average broadcast latency across 5 clients, and aggregate server throughput with 10 concurrent clients downloading 1 MB, 100 MB, and 1 GB files. See the [README](../README.md) for how to run it.
