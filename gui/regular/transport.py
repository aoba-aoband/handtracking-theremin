"""Loopback OSC, acknowledged UI transactions, and real SC telemetry."""
from collections import deque
import subprocess
import threading
import time
import uuid
import socket
import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

from .catalog import ROOT


class Bridge(QObject):
    state = Signal(str, dict)
    telemetry = Signal(str, dict)
    acknowledgement = Signal(str)
    error = Signal(str)

    def __init__(self, host="127.0.0.1", port=57121):
        super().__init__()
        if host != "127.0.0.1":
            raise ValueError("Regular UI bridge supports loopback only")
        self.host, self.port = host, port
        self.client = SimpleUDPClient(host, port)
        self.session = uuid.uuid4().hex
        self.next_id = 0
        self.queue = deque()
        self.sent_at = 0
        self.received_at = 0
        self.process = None
        self.closed = False
        self.log = None
        dispatcher = Dispatcher()
        dispatcher.map("/regular/state", self._state)
        dispatcher.map("/regular/monitor", self._monitor)
        dispatcher.map("/regular/ack", self._ack)
        self.server = ThreadingOSCUDPServer((host, 0), dispatcher)
        self.server.daemon_threads = True
        self.reply_port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        # Cross-thread packets are handled by slots on the GUI thread.
        self.acknowledgement.connect(self.accept_ack)

    @property
    def connected(self):
        return time.monotonic() - self.received_at < 2

    @property
    def busy(self):
        return any(item[1] != "hello" for item in self.queue)

    def _state(self, address, probe, *args):
        self.received_at = time.monotonic()
        self.state.emit(probe, dict(zip(args[::2], args[1::2])))

    def _monitor(self, address, probe, *args):
        self.telemetry.emit(probe, dict(zip(args[::2], args[1::2])))

    def _ack(self, address, request_id):
        self.received_at = time.monotonic()
        self.acknowledgement.emit(str(request_id))

    def accept_ack(self, request_id):
        if self.queue and self.queue[0][0] == request_id:
            self.queue.popleft()
            self.sent_at = 0

    def request(self, operation, *args):
        self.next_id += 1
        request_id = f"{self.session}:{self.next_id}"
        # Coalesce unsent slider changes without changing transaction order.
        if operation == "set":
            for item in list(self.queue)[1:]:
                if item[1] == "set" and item[2][:2] == args[:2]:
                    self.queue.remove(item)
        self.queue.append((request_id, operation, args))

    def tick(self):
        if not self.queue:
            self.request("hello")
        now = time.monotonic()
        if now - self.sent_at >= .2:
            req, op, args = self.queue[0]
            self.client.send_message("/regular/request", [self.reply_port, req, op, *args])
            self.sent_at = now

    def send_many(self, events):
        for event in events:
            self.client.send_message(event.address, event.value)

    def panic(self):
        self.queue.clear()
        self.sent_at = 0
        self.client.send_message("/sample/panic", 1)
        self.client.send_message("/regular/panic", self.reply_port)
        self.request("panic")

    def launch(self):
        if self.process and self.process.poll() is None:
            return
        candidates = list(Path("C:/Program Files").glob("SuperCollider*/sclang.exe"))
        if not candidates:
            raise RuntimeError("SuperCollider sclang.exe was not found; evaluate sc/regular_bridge.scd in SuperCollider")
        log_dir = ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        stem = "regular-sc" if self.port == 57121 else f"regular-sc-{self.port}"
        self.log = (log_dir / (stem + ".log")).open("w", encoding="utf-8")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
            reservation.bind((self.host, 0))
            server_port = reservation.getsockname()[1]
        archive = log_dir / (stem + "-archive")
        archive.mkdir(exist_ok=True)
        bootstrap = log_dir / (stem + "-session.scd")
        bootstrap.write_text(
            '(\nArchive.global = Archive.new;\nArchive.archiveDir = ' + json.dumps(archive.as_posix()) + ';\n'
            + f's = Server(\\regularUIServer, NetAddr("127.0.0.1", {server_port}));\n'
            + 'Server.default = s;\ns.options.numInputBusChannels = 0;\n'
            + json.dumps((ROOT / "sc/regular_bridge.scd").as_posix()) + '.load;\n)\n', encoding="utf-8")
        self.process = subprocess.Popen(
            [str(sorted(candidates)[-1]), "-u", str(self.port), str(bootstrap)],
            cwd=str(ROOT), stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.panic()
        if self.process and self.process.poll() is None:
            self.client.send_message("/regular/shutdown", 1)
            try:
                self.process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=4)
        self.server.shutdown()
        self.server.server_close()
        if self.log:
            self.log.close()
