"""One Regular UI per user/OSC port, with activation of an existing window."""
import getpass
import hashlib
import tempfile
from pathlib import Path
from PySide6.QtCore import QLockFile
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance:
    def __init__(self, port):
        identity = hashlib.sha256(getpass.getuser().encode()).hexdigest()[:12]
        self.name = f"handtracking-regular-{identity}-{port}"
        self.lock = QLockFile(str(Path(tempfile.gettempdir()) / (self.name + ".lock")))
        self.server = None

    def acquire(self):
        if not self.lock.tryLock(0):
            socket = QLocalSocket(); socket.connectToServer(self.name)
            if socket.waitForConnected(1000):
                socket.write(b"activate"); socket.waitForBytesWritten(1000); socket.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        self.server = QLocalServer()
        if not self.server.listen(self.name):
            self.lock.unlock(); raise RuntimeError("Could not create the Regular UI activation socket")
        return True

    def attach(self, window):
        def activate():
            socket = self.server.nextPendingConnection()
            if socket: socket.close(); socket.deleteLater()
            window.showNormal(); window.raise_(); window.activateWindow()
        self.server.newConnection.connect(activate)

    def close(self):
        if self.server: self.server.close()
        self.lock.unlock()
