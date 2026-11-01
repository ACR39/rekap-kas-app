"""Akses GitHub Contents API untuk menyimpan snapshot database di repo terpisah.

Butuh fine-grained PAT dengan permission "Contents: Read and write" pada satu repo data.
Token tidak pernah ditulis ke disk maupun ke kode; dibaca dari secrets/env.
"""

from __future__ import annotations

import base64
import os
from urllib.parse import quote

import requests

API_ROOT = "https://api.github.com"


class GitHubError(RuntimeError):
    """Kesalahan umum saat bicara dengan GitHub."""


class GitHubConflict(GitHubError):
    """sha file sudah berubah di remote (ada penulis lain)."""


def _describe(resp: requests.Response) -> str:
    if resp.status_code == 401:
        return "Token GitHub ditolak (401). Periksa GITHUB_TOKEN."
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining == "0":
            reset = resp.headers.get("X-RateLimit-Reset", "?")
            return f"Rate limit GitHub habis (reset pada epoch {reset}). Coba lagi nanti."
        return "Akses ditolak (403). Pastikan token punya permission Contents: Read and write."
    if resp.status_code == 404:
        return "Repo atau file tidak ditemukan (404). Periksa nama repo dan branch."
    try:
        detail = resp.json().get("message", resp.text[:200])
    except ValueError:
        detail = resp.text[:200]
    return f"GitHub menolak permintaan ({resp.status_code}): {detail}"


class GitHubDataRepo:
    def __init__(
        self,
        token: str,
        repo: str,
        branch: str = "main",
        timeout: int = 25,
    ) -> None:
        if "/" not in repo:
            raise GitHubError('Nama repo harus berbentuk "pemilik/nama-repo".')
        if not token:
            raise GitHubError("GITHUB_TOKEN kosong.")

        self.token = token
        self.repo = repo
        self.branch = branch
        self.timeout = timeout
        self._session = requests.Session()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self, path: str) -> str:
        return f"{API_ROOT}/repos/{self.repo}/contents/{quote(path)}"

    def get_file(self, path: str) -> tuple[bytes, str] | None:
        """Kembalikan (isi file, sha), atau None kalau file belum ada."""
        try:
            resp = self._session.get(
                self._url(path),
                headers=self._headers,
                params={"ref": self.branch},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise GitHubError(f"Tidak bisa menghubungi GitHub: {exc}") from exc

        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise GitHubError(_describe(resp))

        payload = resp.json()
        if isinstance(payload, list):
            raise GitHubError(f"Path `{path}` adalah folder, bukan file.")
        if payload.get("encoding") == "none":
            raise GitHubError(f"File `{path}` terlalu besar untuk Contents API (>{1} MB).")

        content = base64.b64decode(payload["content"])
        return content, payload["sha"]

    def get_sha(self, path: str) -> str | None:
        try:
            resp = self._session.get(
                self._url(path),
                headers=self._headers,
                params={"ref": self.branch},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise GitHubError(f"Tidak bisa menghubungi GitHub: {exc}") from exc
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise GitHubError(_describe(resp))
        payload = resp.json()
        if isinstance(payload, list):
            return None
        return payload.get("sha")

    def put_file(self, path: str, data: bytes, sha: str | None, message: str) -> str:
        """Buat/perbarui file. `sha` harus sha versi terakhir yang kita baca.

        Mengembalikan sha baru. Kalau sha sudah basi, GitHub menolak dengan 409/422
        dan kita lempar GitHubConflict supaya pemanggil bisa mengambil keputusan.
        """
        body: dict[str, str] = {
            "message": message,
            "content": base64.b64encode(data).decode("ascii"),
            "branch": self.branch,
        }
        if sha:
            body["sha"] = sha

        try:
            resp = self._session.put(
                self._url(path), headers=self._headers, json=body, timeout=self.timeout
            )
        except requests.RequestException as exc:
            raise GitHubError(f"Tidak bisa menghubungi GitHub: {exc}") from exc

        if resp.status_code in (409, 422):
            raise GitHubConflict(
                "Data di repo sudah berubah sejak terakhir dibaca (ada penulis lain)."
            )
        if resp.status_code not in (200, 201):
            raise GitHubError(_describe(resp))

        return resp.json()["content"]["sha"]


def repo_from_env() -> GitHubDataRepo | None:
    """Bangun koneksi dari environment variable; None kalau sync tidak dikonfigurasi."""
    token = os.getenv("GITHUB_TOKEN", "").strip()
    repo = os.getenv("GITHUB_DATA_REPO", "").strip()
    if not token or not repo:
        return None
    branch = os.getenv("GITHUB_DATA_BRANCH", "main").strip() or "main"
    return GitHubDataRepo(token, repo, branch)


def repo_from_config(token: str, repo: str, branch: str = "main") -> GitHubDataRepo | None:
    token = (token or "").strip()
    repo = (repo or "").strip()
    if not token or not repo:
        return None
    return GitHubDataRepo(token, repo, branch or "main")
