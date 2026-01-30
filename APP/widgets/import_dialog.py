import os
import time
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton, QTextEdit, QHBoxLayout
from PySide6.QtCore import QObject, Signal, Slot, QThread
import qtawesome as qta

from APP.helpers.image_support import get_supported_extensions

SUPPORTED_EXTENSIONS = get_supported_extensions()


class ImportWorker(QObject):
    progress = Signal(int, str)
    finished = Signal(list, dict)  # files, stats
    error = Signal(str)

    def __init__(self, paths, parent=None, sleep_between=0.0):
        super().__init__(parent)
        self.paths = paths
        self._abort = False
        self.sleep_between = float(sleep_between)

    @Slot()
    def run(self):
        try:
            start_time = time.time()
            total_candidates = 0
            # First pass: count candidates quickly
            for p in self.paths:
                if self._abort:
                    self.finished.emit([], {'aborted': True})
                    return
                if os.path.isfile(p):
                    if os.path.splitext(p)[1].lower() in SUPPORTED_EXTENSIONS:
                        total_candidates += 1
                elif os.path.isdir(p):
                    for root, dirs, files in os.walk(p):
                        if os.path.basename(root).upper() == 'PNG':
                            continue
                        for f in files:
                            if self._abort:
                                self.finished.emit([], {'aborted': True})
                                return
                            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS:
                                total_candidates += 1
            # Second pass: collect
            found = []
            scanned_dirs = 0
            invalid_files = 0
            processed = 0
            for p in self.paths:
                if self._abort:
                    self.finished.emit([], {'aborted': True})
                    return
                if os.path.isfile(p):
                    ext = os.path.splitext(p)[1].lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        found.append(p)
                        processed += 1
                        percent = int(processed / max(1, total_candidates) * 100)
                        self.progress.emit(percent, f"Found {processed} / {total_candidates} files")
                        if self.sleep_between:
                            time.sleep(self.sleep_between)
                    else:
                        invalid_files += 1
                elif os.path.isdir(p):
                    for root, dirs, files in os.walk(p):
                        if self._abort:
                            self.finished.emit([], {'aborted': True})
                            return
                        if os.path.basename(root).upper() == 'PNG':
                            continue
                        scanned_dirs += 1
                        for f in files:
                            if self._abort:
                                self.finished.emit([], {'aborted': True})
                                return
                            if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS:
                                found.append(os.path.join(root, f))
                                processed += 1
                                percent = int(processed / max(1, total_candidates) * 100)
                                self.progress.emit(percent, f"Found {processed} / {total_candidates} files")
                                if self.sleep_between:
                                    time.sleep(self.sleep_between)
                            else:
                                invalid_files += 1
            elapsed = time.time() - start_time
            stats = {
                'total_candidates': total_candidates,
                'found': len(found),
                'invalid': invalid_files,
                'dirs_scanned': scanned_dirs,
                'time': elapsed,
                'aborted': False
            }
            self.finished.emit(found, stats)
        except Exception as e:
            self.error.emit(str(e))

    def abort(self):
        self._abort = True


class ImportDialog(QDialog):
    """Dialog to import files/folders non-blocking with progress and stats."""

    def __init__(self, parent=None, paths=None, sleep_between=0.0):
        super().__init__(parent)
        self.setWindowTitle("Import Files")
        self.resize(500, 200)
        self.paths = paths or []
        self._files = None

        layout = QVBoxLayout(self)
        self.label = QLabel("Memindai file...")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.stats = QTextEdit()
        self.stats.setReadOnly(True)
        self.btn_confirm = QPushButton("Mulai Proses")
        self.btn_confirm.setEnabled(False)
        try:
            self.btn_confirm.setIcon(qta.icon('fa5s.play'))
        except Exception:
            pass

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_confirm)

        layout.addWidget(self.label)
        layout.addWidget(self.progress)
        layout.addWidget(self.stats)
        layout.addLayout(btn_layout)

        self.worker = None
        self.thread = None
        self.sleep_between = float(sleep_between)

        self.btn_confirm.clicked.connect(self._on_confirm_clicked)

        self._start_worker()

    def _start_worker(self):
        self.worker = ImportWorker(self.paths, sleep_between=self.sleep_between)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def _on_progress(self, percent, message):
        self.progress.setValue(percent)
        self.label.setText(message)

    def _on_finished(self, files, stats):
        if stats.get('aborted'):
            self.stats.setPlainText("Dibatalkan oleh pengguna")
            self._files = None
            self.btn_confirm.setEnabled(False)
        else:
            text = (
                f"Selesai memindai.\nFound: {stats.get('found')} / {stats.get('total_candidates')}\n"
                f"Invalid files: {stats.get('invalid')}\nDirs scanned: {stats.get('dirs_scanned')}\nTime: {stats.get('time'):.1f}s"
            )
            self.stats.setPlainText(text)
            self._files = files
            # Enable confirm only if we found at least one supported file
            self.btn_confirm.setEnabled(bool(files))
            self.label.setText("Selesai")
        # Stop thread
        try:
            self.thread.quit()
            self.thread.wait(1000)
        except Exception:
            pass

    def _on_error(self, msg):
        self.stats.setPlainText(f"Error: {msg}")
        self._files = None
        self.btn_confirm.setEnabled(False)
        try:
            self.thread.quit()
            self.thread.wait(1000)
        except Exception:
            pass

    def closeEvent(self, event):
        # If user closes the dialog manually, abort worker to avoid dangling threads
        try:
            if self.worker:
                self.worker.abort()
        except Exception:
            pass
        # Ensure thread is stopped
        try:
            if self.thread:
                self.thread.quit()
                self.thread.wait(1000)
        except Exception:
            pass
        # Accept close
        super().closeEvent(event)

    def _on_confirm_clicked(self):
        # User confirmed to start processing the found files
        self.accept()

    def exec_get_files(self):
        res = self.exec()
        if res == 1 and self._files:
            return self._files
        return None
