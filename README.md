# Rekap Bayar Kas

Pencatat pengeluaran pribadi. Streamlit + SQLite, dengan snapshot otomatis ke repo
GitHub **private** terpisah supaya data tidak hilang saat app di-redeploy.

Satu pemilik, satu password. Tidak ada sistem multi-user, tidak ada registrasi akun.

## Fitur

- Satu password untuk membuka aplikasi (PBKDF2-SHA256, 260k iterasi, disimpan di database)
- Input transaksi: tanggal, kategori, keterangan, nominal
- Tabel transaksi: filter bulan & kategori, ubah, hapus
- Dashboard: total bulanan, rata-rata harian, transaksi terbesar, pie & bar per kategori, tren harian
- Budget per kategori per bulan, progress bar, peringatan 80% dan lewat budget, salin budget dari bulan sebelumnya
- Kelola kategori: gabung/rename kategori salah ketik, hapus kategori tambahan
- Export Excel (2 sheet), PDF siap cetak, CSV
- Sync otomatis ke repo data private + tombol kirim/tarik manual + unduh `kas.db`

## Arsitektur sync

```
repo rekap-kas-app   (public)  → kode aplikasi
repo rekap-kas-data  (private) → kas.db, satu file
```

Alurnya:

1. Saat app start, `kas.db` ditarik dari repo data lewat GitHub Contents API.
2. Semua baca/tulis terjadi ke SQLite **lokal** — tidak ada latensi network saat dipakai.
3. Setiap ada perubahan (tambah/ubah/hapus transaksi, budget, password), snapshot
   `kas.db` dikirim balik ke repo sebagai satu commit.

**Batasannya:** file SQLite itu biner, jadi tidak bisa di-merge. Kalau dipakai dari dua
perangkat bersamaan, yang menyimpan terakhir menang dan perubahan perangkat lain hilang.
Kalau ini terjadi, app menampilkan status 🟡 dan Pengaturan menyediakan pilihan
"Timpa repo dengan data lokal" atau "Tarik ulang dari repo".

## Struktur file

```
app.py                        UI Streamlit (Input, Dashboard, Budget, Kategori, Export, Pengaturan)
db.py                         Akses SQLite + migrasi skema lama
sync.py                       Restore/push snapshot kas.db
github_store.py               Klien GitHub Contents API
exporter.py                   Laporan PDF (ReportLab)
requirements.txt              Dependensi
.streamlit/config.toml        Tema
.streamlit/secrets.toml.example  Contoh kredensial
data/                         kas.db (dibuat otomatis, tidak di-commit)
```

## Jalankan lokal

Butuh Python 3.10+.

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Buka `http://localhost:8501`, buat password saat pertama dijalankan.

Sync opsional. Tanpa kredensial, app tetap jalan normal dengan database lokal saja.
Untuk mengaktifkan:

```powershell
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
```

lalu isi `token`, `data_repo`, `data_branch`.

Alternatif tanpa file secrets:

```powershell
$env:GITHUB_TOKEN="github_pat_xxx"
$env:GITHUB_DATA_REPO="username/rekap-kas-data"
streamlit run app.py
```

## Menyiapkan repo data + token

1. Buat repo **private** baru, misal `rekap-kas-data`. Boleh kosong, tanpa README.
2. GitHub → Settings → Developer settings → **Personal access tokens → Fine-grained tokens**
   → Generate new token.
3. Repository access: **Only select repositories** → pilih `rekap-kas-data` saja.
4. Permissions → Repository permissions → **Contents: Read and write**. Sisanya biarkan
   No access.
5. Copy token, tempel di `.streamlit/secrets.toml`.

Token hanya bisa mengakses repo data itu. Kalau token bocor, kerugiannya terbatas pada
satu repo tersebut — bukan seluruh akun GitHub.

## Push app ke GitHub

```powershell
git init
git add .
git commit -m "Aplikasi pencatat pengeluaran pribadi"
git branch -M main
git remote add origin https://github.com/USERNAME/rekap-kas-app.git
git push -u origin main
```

`.gitignore` sudah mengecualikan `data/`, `*.db`, dan `.streamlit/secrets.toml`.

## Deploy ke Streamlit Community Cloud

1. https://share.streamlit.io → **New app** → pilih repo app, branch `main`, main file `app.py`
2. Sebelum deploy (atau lewat **Settings → Secrets** setelahnya), isi:

```toml
[github]
token = "github_pat_xxx"
data_repo = "username/rekap-kas-data"
data_branch = "main"
```

3. Deploy.

Dengan sync aktif, filesystem sementara Streamlit Cloud tidak jadi masalah — setiap
restart akan menarik ulang `kas.db` dari repo data.

## Catatan keamanan

- Jangan pernah commit `.streamlit/secrets.toml`. Kalau token terlanjur ter-commit,
  langsung **revoke** token itu di GitHub dan buat baru.
- Repo data harus private. Kalau public, siapa pun bisa membaca seluruh catatan keuanganmu,
  termasuk hash password.
- Password aplikasi melindungi UI, bukan file `kas.db`. Siapa pun yang punya akses ke repo
  data bisa membaca isinya. Aktifkan 2FA di akun GitHub.
- Backup tetap disarankan: Pengaturan → **Unduh kas.db** sesekali.
