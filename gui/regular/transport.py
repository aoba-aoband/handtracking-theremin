"""Loopback OSC, acknowledged UI transactions, and real SC telemetry."""
from collections import deque
import subprocess
import threading
import time
import uuid
import socket
import json
import os
import platform
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient

from .catalog import ROOT
from .process_scope import ProcessScope


def port_available(port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        if os.name == "nt": probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try: probe.bind(("0.0.0.0", port))
        except OSError: return False
    return True


def verification_port(preferred=57122):
    for port in range(preferred, preferred + 50):
        if port_available(port): return port
    raise RuntimeError("No unused verification OSC port found")


class Bridge(QObject):
    state = Signal(str, dict)
    telemetry = Signal(str, dict)
    acknowledgement = Signal(str)
    error = Signal(str)
    devices_changed = Signal()
    audio_changed = Signal(dict)
    fx_state = Signal(dict)
    order_changed = Signal(list)
    inspection = Signal(dict)

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
        self.process_scope = None
        self.process_error_reported = False
        self.process_epoch = 0
        self.restart_pending = False
        self.closed = False
        self.log = None
        self.audio_ready = False
        self.audio_requested = False
        self.pending_audio = None
        self.last_audio_config = None
        self.audio_status = {"state": "disconnected"}
        self.devices = {"input": [], "output": []}
        self.device_kinds_received = set()
        dispatcher = Dispatcher()
        dispatcher.map("/regular/state", self._state)
        dispatcher.map("/regular/monitor", self._monitor)
        dispatcher.map("/regular/ack", self._ack)
        dispatcher.map("/regular/devices", self._devices)
        dispatcher.map("/regular/audio", self._audio)
        dispatcher.map("/regular/fx_state", self._fx_state)
        dispatcher.map("/regular/order", self._order)
        dispatcher.map("/regular/inspect", self._inspect)
        self.dispatcher = dispatcher
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
        return self.restart_pending or any(item[1] != "hello" for item in self.queue)

    @property
    def devices_received(self): return self.device_kinds_received == {"input", "output"}

    @property
    def log_path(self):
        stem = "regular-sc" if self.port == 57121 else f"regular-sc-{self.port}"
        return ROOT / "logs" / (stem + ".log")

    def _devices(self, address, kind, *names):
        if kind not in self.devices: return
        self.devices[kind] = list(names)
        self.device_kinds_received.add(kind)
        self.devices_changed.emit()

    def _audio(self, address, state, error, generation, cpu, peak, inputs, outputs, rate):
        if self.restart_pending: return
        self.received_at = time.monotonic()
        self.audio_ready = state == "ready"
        self.audio_status = dict(state=state, error=error, generation=generation, cpu=cpu,
                                 peak_cpu=peak, input_channels=inputs, output_channels=outputs, sample_rate=rate)
        self.audio_changed.emit(dict(self.audio_status))

    def _fx_state(self, address, *args): self.fx_state.emit(dict(zip(args[::2], args[1::2])))

    def _order(self, address, *items): self.order_changed.emit(list(items))

    def _inspect(self, address, *args): self.inspection.emit(dict(zip(args[::2], args[1::2])))

    def configure_audio(self, config):
        from .audio_setup import validate_audio
        config = validate_audio(config)
        restart_owned = self.process is not None and self.audio_status.get("state") not in ("disconnected", "unconfigured")
        self.last_audio_config = dict(config)
        self.audio_requested = True
        self.audio_ready = False
        self.pending_audio = config
        if restart_owned and not self.restart_pending:
            # A full owned-session restart also invalidates language callbacks.
            # An externally opened language session is never terminated here.
            self.panic()
            self.restart_pending = True
            self.audio_status = dict(self.audio_status, state="booting", error="")
            self.audio_changed.emit(dict(self.audio_status))
            QTimer.singleShot(180, self._restart_owned)

    def _restart_owned(self):
        if self.closed: return
        try:
            if self.process_scope: self.process_scope.close()
            if self.process: self.process.wait(timeout=4)
            self.server.shutdown(); self.server.server_close()
            self.server = ThreadingOSCUDPServer((self.host, 0), self.dispatcher)
            self.server.daemon_threads = True
            self.reply_port = self.server.server_address[1]
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
            self.queue.clear(); self.sent_at = 0; self.received_at = 0
            self.audio_ready = False
            self.session = uuid.uuid4().hex; self.next_id = 0
            self.audio_status = {"state": "disconnected"}
            self.device_kinds_received.clear()
            self.launch()
        except Exception as exc:
            self.error.emit("Owned SC restart failed: " + str(exc))
            self.audio_status = dict(state="failed", error=str(exc), generation=self.process_epoch * 1000)
            self.audio_changed.emit(dict(self.audio_status))
        finally: self.restart_pending = False

    def send_modulation(self, effect, target, value, presence):
        self.client.send_message("/regular/mod", [effect, target, float(value), float(presence)])

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
        if operation in ("set", "fx"):
            for item in list(self.queue)[1:]:
                if item[1] == operation and item[2][:2] == args[:2]:
                    self.queue.remove(item)
        self.queue.append((request_id, operation, args))

    def tick(self):
        if self.restart_pending: return
        if self.process is not None and self.process.poll() is not None and not self.process_error_reported and not self.closed:
            self.process_error_reported = True
            self.received_at = 0
            self.audio_ready = False
            self.audio_status = dict(self.audio_status, state="failed", error=f"SC language exited ({self.process.returncode}). Open SC Log in Audio Setup.")
            self.error.emit(self.audio_status["error"])
            self.audio_changed.emit(dict(self.audio_status, generation=self.audio_status.get("generation", 0)))
        if self.pending_audio is not None and self.connected:
            config, self.pending_audio = self.pending_audio, None
            self.request("audio", "__NONE__" if config["input"] == "none" else config["input"] or "__DEFAULT__",
                         config["output"] or "__DEFAULT__", config["sample_rate"] or 0)
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
        # Keep an explicit pre-boot device choice. Dropping its transaction
        # leaves audio_requested=True but the server forever unconfigured.
        # Performance/settings commands are cancelled; boot cannot open Gate.
        audio_requests = [item for item in self.queue if item[1] == "audio"]
        self.queue.clear()
        if audio_requests: self.queue.append(audio_requests[-1])
        self.sent_at = 0
        self.client.send_message("/sample/panic", 1)
        self.client.send_message("/regular/panic", self.reply_port)
        self.request("panic")

    def launch(self):
        if self.process and self.process.poll() is None:
            return
        if not port_available(self.port):
            raise RuntimeError(f"OSC language port {self.port} is already in use. Connect the existing Regular session or choose --ui-sc-port; SC will not silently switch ports.")
        if self.process_scope: self.process_scope.close()
        self.process_error_reported = False
        self.process_epoch += 1
        if self.last_audio_config is not None: self.pending_audio = dict(self.last_audio_config)
        candidates = []
        if os.environ.get("HANDTRACK_SCLANG"): candidates.append(Path(os.environ["HANDTRACK_SCLANG"]))
        if platform.system() == "Windows": candidates.extend(sorted(Path("C:/Program Files").glob("SuperCollider*/sclang.exe"), reverse=True))
        elif platform.system() == "Darwin":
            candidates.extend([Path("/Applications/SuperCollider.app/Contents/MacOS/sclang"), Path.home() / "Applications/SuperCollider.app/Contents/MacOS/sclang"])
        if shutil.which("sclang"): candidates.append(Path(shutil.which("sclang")))
        candidates = [path for path in candidates if path.is_file()]
        if not candidates:
            raise RuntimeError("SuperCollider sclang was not found. Install SC, set HANDTRACK_SCLANG, or evaluate sc/regular_bridge.scd in an external session.")
        log_dir = ROOT / "logs"
        log_dir.mkdir(exist_ok=True)
        stem = "regular-sc" if self.port == 57121 else f"regular-sc-{self.port}"
        if self.log: self.log.close()
        self.log = (log_dir / (stem + ".log")).open("a", encoding="utf-8")
        self.log.write("\n--- SC session " + time.strftime("%Y-%m-%d %H:%M:%S") + " ---\n"); self.log.flush()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
            if os.name == "nt": reservation.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            reservation.bind((self.host, 0))
            server_port = reservation.getsockname()[1]
        archive = log_dir / (stem + "-archive")
        archive.mkdir(exist_ok=True)
        bootstrap = log_dir / (stem + "-session.scd")
        bootstrap.write_text(
            '(\nArchive.global = Archive.new;\nArchive.archiveDir = ' + json.dumps(archive.as_posix()) + ';\n'
            + f'~regularGeneration = {self.process_epoch * 1000};\n'
            + f'(NetAddr.langPort != {self.port}).if({{ "Requested OSC port is occupied".postln; 2.exit; }});\n'
            + f's = Server(\\regularUIServer, NetAddr("127.0.0.1", {server_port}));\n'
            + 'Server.default = s;\ns.options.numInputBusChannels = 0;\n'
            + json.dumps((ROOT / "sc/regular_bridge.scd").as_posix()) + '.load;\n)\n', encoding="utf-8")
        self.process_scope = ProcessScope()
        self.process = self.process_scope.launch(
            [str(candidates[0]), "-u", str(self.port), str(bootstrap)],
            cwd=str(ROOT), stdout=self.log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.panic()
            if self.process and self.process.poll() is None:
                self.client.send_message("/regular/shutdown", 1)
                try: self.process.wait(timeout=4)
                except subprocess.TimeoutExpired: pass
        finally:
            if self.process_scope: self.process_scope.close()
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try: self.process.wait(timeout=4)
                except subprocess.TimeoutExpired: pass
            self.server.shutdown(); self.server.server_close()
            if self.log: self.log.close()
