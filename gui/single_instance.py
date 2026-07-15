from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QLockFile, QObject, QStandardPaths, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def default_instance_id() -> str:
    user_key = hashlib.sha256(str(Path.home()).encode("utf-8")).hexdigest()[:12]
    return f"baidu_data_automation_console_{user_key}"


class SingleInstanceGuard(QObject):
    activate_requested = Signal()

    def __init__(self, instance_id: str | None = None, lock_dir: str | Path | None = None):
        super().__init__()
        self.instance_id = instance_id or default_instance_id()
        base = Path(lock_dir or QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation))
        base.mkdir(parents=True, exist_ok=True)
        self._lock = QLockFile(str(base / f"{self.instance_id}.lock"))
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._accept_connections)
        self._primary = False

    def acquire(self) -> bool:
        if not self._lock.tryLock(0):
            return False
        QLocalServer.removeServer(self.instance_id)
        if not self._server.listen(self.instance_id):
            self._lock.unlock()
            return False
        self._primary = True
        return True

    def notify_existing(self) -> bool:
        for _ in range(8):
            socket = QLocalSocket()
            socket.connectToServer(self.instance_id)
            if socket.waitForConnected(150):
                socket.write(b"activate\n")
                socket.flush()
                socket.waitForBytesWritten(300)
                socket.disconnectFromServer()
                return True
        return False

    def _accept_connections(self) -> None:
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue
            self.activate_requested.emit()
            socket.disconnectFromServer()
            socket.deleteLater()

    def close(self) -> None:
        if self._primary:
            self._server.close()
            QLocalServer.removeServer(self.instance_id)
            self._lock.unlock()
            self._primary = False
