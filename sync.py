"""Sinkronisasi database SQLite lokal dengan snapshot di repo GitHub private.

Alur:
  - restore_from_repo(): tarik kas.db dari repo data saat app start.
  - push_to_repo(): kirim snapshot kas.db terbaru setelah ada perubahan data.
  - local_is_newer_than_sync(): deteksi perubahan lokal yang belum terkirim.

Snapshot disimpan sebagai file biner apa adanya. Karena itu dua penulis bersamaan
tidak bisa digabung (GitHub tidak bisa merge biner); yang terakhir menang.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass
from datetime import datetime

import db
from github_store import GitHubDataRepo, GitHubError

DB_FILE = "kas.db"


@dataclass
class SyncState:
    enabled: bool
    branch: str | None = None
    repo: str | None = None
    sha: str | None = None
    last_sync: str | None = None
    dirty: bool = False
    error: str | None = None

    @property
    def status(self) -> str:
        if not self.enabled:
            return "Sync nonaktif"
        if self.error:
            return "Error"
        if self.dirty:
            return "Ada perubahan belum terkirim"
        return "Tersinkron"


def remember_sidecar() -> None:
    """Catat waktu sync terakhir di samping DB (tidak ikut di-commit).

    File ini jadi pembanding mtime: kalau kas.db lebih baru dari penanda ini,
    berarti ada perubahan yang belum terkirim ke repo.
    """
    marker = os.path.join(os.path.dirname(db.DB_PATH), ".last_sync")
    folder = os.path.dirname(marker)
    try:
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(marker, "w") as fh:
            fh.write(datetime.now().isoformat(timespec="seconds"))
        # Samakan mtime penanda dengan waktu sekarang supaya perbandingan mtime akurat.
        now = datetime.now().timestamp()
        os.utime(marker, (now, now))
    except OSError:
        pass


def read_sidecar() -> str | None:
    try:
        with open(os.path.join(os.path.dirname(db.DB_PATH), ".last_sync")) as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def snapshot_bytes() -> bytes:
    """Salin DB secara konsisten memakai backup API SQLite (aman walau sedang dipakai)."""
    fd, tmp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with db.get_conn() as conn:
            dest = sqlite3.connect(tmp_path)
            try:
                conn.backup(dest)
            finally:
                dest.close()
        with open(tmp_path, "rb") as fh:
            return fh.read()
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _validate_sqlite(data: bytes) -> None:
    if not data.startswith(b"SQLite format 3"):
        raise GitHubError("File dari repo bukan database SQLite yang valid.")


def restore_from_repo(repo: GitHubDataRepo) -> str | None:
    """Tarik kas.db dari repo dan pasang sebagai DB aktif. Return sha, atau None kalau belum ada."""
    found = repo.get_file(DB_FILE)
    if found is None:
        return None
    data, sha = found
    _validate_sqlite(data)

    target_dir = os.path.dirname(db.DB_PATH)
    os.makedirs(target_dir, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(suffix=".db", dir=target_dir)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        # pastikan file yang baru diunduh memang bisa dibuka
        probe = sqlite3.connect(tmp_path)
        try:
            probe.execute("SELECT count(*) FROM sqlite_master")
        finally:
            probe.close()
        shutil.move(tmp_path, db.DB_PATH)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    remember_sidecar()
    return sha


def push_to_repo(repo: GitHubDataRepo, sha: str | None, message: str) -> str:
    data = snapshot_bytes()
    new_sha = repo.put_file(DB_FILE, data, sha, message)
    remember_sidecar()
    return new_sha


def local_db_exists() -> bool:
    return os.path.exists(db.DB_PATH) and os.path.getsize(db.DB_PATH) > 0


def local_is_newer_than_sync() -> bool:
    """True kalau DB lokal berubah setelah sync terakhir (artinya ada data belum terkirim).

    Dipakai untuk mencegah restore menimpa perubahan lokal yang belum sempat di-push
    (misal push gagal karena jaringan).
    """
    marker = os.path.join(os.path.dirname(db.DB_PATH), ".last_sync")
    if not os.path.exists(db.DB_PATH):
        return False
    if not os.path.exists(marker):
        return True
    return os.path.getmtime(db.DB_PATH) > os.path.getmtime(marker) + 1
