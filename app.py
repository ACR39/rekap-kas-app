"""Aplikasi pencatat pengeluaran pribadi (Streamlit + SQLite + snapshot GitHub)."""

from __future__ import annotations

import calendar
import hashlib
import hmac
import io
import secrets
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import streamlit as st

import db
import github_store
import sync
from exporter import build_pdf

st.set_page_config(
    page_title="Rekap Bayar Kas",
    page_icon="R",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------- theme CSS

st.markdown(
    """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
    :root {
        --bg: #FAFAFB;
        --surface: #FFFFFF;
        --surface-2: #F4F4F6;
        --text: #111827;
        --muted: #6B7280;
        --muted-2: #9CA3AF;
        --border: #E5E7EB;
        --border-strong: #D1D5DB;
        --accent: #111827;
        --accent-hover: #1F2937;
        --danger: #DC2626;
        --success: #16A34A;
        --warning: #D97706;
        --radius: 10px;
        --shadow-sm: 0 1px 2px rgba(17,24,39,0.04);
        --shadow-md: 0 4px 12px rgba(17,24,39,0.06);
    }
    html, body, [class*="css"] { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
    .stApp { background-color: var(--bg); }
    .block-container { padding-top: 1.75rem; padding-bottom: 3rem; max-width: 1180px; }

    h1 { color: var(--text); font-weight: 700; font-size: 1.6rem; letter-spacing: -0.02em; margin: 0 0 0.25rem; }
    h2 { color: var(--text); font-weight: 600; font-size: 1.15rem; letter-spacing: -0.01em; margin: 1.75rem 0 0.75rem; }
    h3 { color: var(--text); font-weight: 600; font-size: 1rem; margin: 1.25rem 0 0.5rem; }
    p { color: var(--muted); }
    .stCaption, [data-testid="stCaptionContainer"] { color: var(--muted-2); font-size: 0.85rem; }

    /* sidebar */
    section[data-testid="stSidebar"] {
        background-color: var(--surface);
        border-right: 1px solid var(--border);
    }
    section[data-testid="stSidebar"] > div { padding-top: 1.5rem; }
    section[data-testid="stSidebar"] .stRadio label {
        font-size: 0.9rem;
        color: var(--text);
        padding: 0.35rem 0.5rem;
        border-radius: 6px;
    }
    section[data-testid="stSidebar"] .stRadio label:hover { background-color: var(--surface-2); }

    /* inputs */
    .stTextInput input, .stNumberInput input, .stDateInput input, .stSelectbox div[data-baseweb="select"] > div {
        background-color: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        color: var(--text);
        font-size: 0.9rem;
        transition: border-color 0.15s ease, box-shadow 0.15s ease;
    }
    .stTextInput input:focus, .stNumberInput input:focus, .stDateInput input:focus {
        border-color: var(--accent);
        box-shadow: 0 0 0 3px rgba(17,24,39,0.08);
    }

    /* buttons */
    .stButton button, .stDownloadButton button {
        border-radius: 8px;
        font-weight: 500;
        font-size: 0.875rem;
        border: 1px solid var(--border);
        background-color: var(--surface);
        color: var(--text);
        transition: all 0.15s ease;
        box-shadow: var(--shadow-sm);
    }
    .stButton button:hover, .stDownloadButton button:hover {
        border-color: var(--border-strong);
        background-color: var(--surface-2);
    }
    .stButton button[kind="primary"], .stDownloadButton button[kind="primary"] {
        background-color: var(--accent);
        color: #FFFFFF;
        border-color: var(--accent);
        box-shadow: var(--shadow-sm);
    }
    .stButton button[kind="primary"]:hover {
        background-color: var(--accent-hover);
        border-color: var(--accent-hover);
    }

    /* metric cards */
    [data-testid="stMetric"] {
        background-color: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius);
        padding: 1rem 1.1rem;
        box-shadow: var(--shadow-sm);
    }
    [data-testid="stMetricLabel"] { color: var(--muted); font-size: 0.78rem; font-weight: 500; text-transform: uppercase; letter-spacing: 0.04em; }
    [data-testid="stMetricValue"] { color: var(--text); font-size: 1.25rem; font-weight: 600; letter-spacing: -0.01em; }

    /* dataframes */
    .stDataFrame { border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; box-shadow: var(--shadow-sm); }

    /* progress */
    .stProgress > div > div { background-color: var(--accent); border-radius: 999px; }
    .stProgress > div { background-color: var(--surface-2); border-radius: 999px; }

    /* alerts */
    .stSuccess { background-color: #F0FDF4; border-left: 3px solid var(--success); border-radius: 8px; }
    .stError { background-color: #FEF2F2; border-left: 3px solid var(--danger); border-radius: 8px; }
    .stWarning { background-color: #FFFBEB; border-left: 3px solid var(--warning); border-radius: 8px; }
    .stInfo { background-color: var(--surface-2); border-left: 3px solid var(--border-strong); border-radius: 8px; }

    /* divider */
    hr { border-color: var(--border); margin: 1.5rem 0; }

    /* hide streamlit chrome */
    #MainMenu, footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent; }
    </style>
    """,
    unsafe_allow_html=True,
)

ID_MONTHS = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

PBKDF2_ITERATIONS = 260_000
PASSWORD_KEY = "password_hash"
SALT_KEY = "password_salt"


# ---------------------------------------------------------------- helpers


def rupiah(value: float) -> str:
    return "Rp " + f"{int(round(value)):,}".replace(",", ".")


def month_label(month: str) -> str:
    year, mon = month.split("-")
    return f"{ID_MONTHS[int(mon) - 1]} {year}"


def month_bounds(month: str) -> tuple[str, str]:
    year, mon = (int(p) for p in month.split("-"))
    last = calendar.monthrange(year, mon)[1]
    return f"{month}-01", f"{month}-{last:02d}"


def month_options(current: str, include_budgets: bool = False) -> list[str]:
    months = set(db.months_with_data()) | {current}
    if include_budgets:
        months |= set(db.months_with_budgets())
    return sorted(months, reverse=True)


def show_flash() -> None:
    message = st.session_state.pop("flash", None)
    if message:
        st.success(message)


def safe_index(options: list, value) -> int:
    return options.index(value) if value in options else 0


# ---------------------------------------------------------------- password


def password_is_set() -> bool:
    return bool(db.get_setting(PASSWORD_KEY))


def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()


def set_password(password: str) -> None:
    salt = secrets.token_hex(16)
    db.set_setting(SALT_KEY, salt)
    db.set_setting(PASSWORD_KEY, hash_password(password, salt))


def check_password(password: str) -> bool:
    salt = db.get_setting(SALT_KEY)
    stored = db.get_setting(PASSWORD_KEY)
    if not salt or not stored:
        return False
    return hmac.compare_digest(hash_password(password, salt), stored)


# ---------------------------------------------------------------- sync


def get_sync_repo() -> github_store.GitHubDataRepo | None:
    try:
        cfg = st.secrets.get("github", {})
    except Exception:
        cfg = {}
    repo = github_store.repo_from_config(
        cfg.get("token", ""),
        cfg.get("data_repo", ""),
        cfg.get("data_branch", "main"),
    )
    return repo if repo is not None else github_store.repo_from_env()


def sync_state() -> sync.SyncState:
    repo = st.session_state.get("sync_repo")
    if repo is None:
        return sync.SyncState(enabled=False, last_sync=sync.read_sidecar())
    return sync.SyncState(
        enabled=True,
        branch=repo.branch,
        repo=repo.repo,
        sha=st.session_state.get("sync_sha"),
        last_sync=sync.read_sidecar(),
        dirty=st.session_state.get("sync_dirty", False),
        error=st.session_state.get("sync_error"),
    )


def bootstrap() -> None:
    if st.session_state.get("boot_done"):
        return

    repo = get_sync_repo()
    st.session_state["sync_repo"] = repo
    st.session_state.setdefault("sync_sha", None)
    st.session_state.setdefault("sync_dirty", False)
    st.session_state.setdefault("sync_error", None)

    existed_before = sync.local_db_exists()

    if repo is not None:
        unsent = existed_before and sync.local_is_newer_than_sync()

        if unsent:
            db.init_db()
            try:
                remote_sha = repo.get_sha(sync.DB_FILE)
                st.session_state["sync_sha"] = sync.push_to_repo(
                    repo, remote_sha, "Kirim perubahan lokal yang belum tersinkron"
                )
                st.session_state["sync_note"] = (
                    "Perubahan lokal yang belum terkirim sudah diunggah."
                )
            except github_store.GitHubError as exc:
                st.session_state["sync_dirty"] = True
                st.session_state["sync_error"] = str(exc)
        else:
            try:
                sha = sync.restore_from_repo(repo)
            except github_store.GitHubError as exc:
                st.session_state["sync_error"] = str(exc)
            else:
                if sha:
                    st.session_state["sync_sha"] = sha
                    st.session_state["sync_note"] = "Database dipulihkan dari repo GitHub."
                elif existed_before:
                    db.init_db()
                    try:
                        st.session_state["sync_sha"] = sync.push_to_repo(
                            repo, None, "Snapshot awal dari database lokal"
                        )
                        st.session_state["sync_note"] = (
                            "Snapshot awal dibuat dari database lokal."
                        )
                    except github_store.GitHubError as exc:
                        st.session_state["sync_dirty"] = True
                        st.session_state["sync_error"] = str(exc)

    db.init_db()

    if repo is not None and not st.session_state.get("sync_dirty"):
        sync.remember_sidecar()

    st.session_state["boot_done"] = True


def push_sync(message: str) -> None:
    repo = st.session_state.get("sync_repo")
    if repo is None:
        return
    try:
        sha = sync.push_to_repo(repo, st.session_state.get("sync_sha"), message)
    except github_store.GitHubConflict as exc:
        st.session_state["sync_dirty"] = True
        st.session_state["sync_error"] = (
            f"{exc} Buka Pengaturan: pilih \"Timpa repo dengan data lokal\" "
            "atau \"Tarik ulang dari repo\"."
        )
    except github_store.GitHubError as exc:
        st.session_state["sync_dirty"] = True
        st.session_state["sync_error"] = str(exc)
    else:
        st.session_state["sync_sha"] = sha
        st.session_state["sync_dirty"] = False
        st.session_state["sync_error"] = None


def after_write(message: str) -> None:
    st.session_state["sync_dirty"] = True
    push_sync(message)


# ---------------------------------------------------------------- login gate


def render_gate() -> None:
    st.title("Rekap Bayar Kas")
    st.caption("Catat pengeluaran harian, pantau budget, lihat rekap bulanan.")

    if not password_is_set():
        st.caption("Pertama kali dipakai — buat password untuk membuka aplikasi.")
        with st.form("create_password", clear_on_submit=True):
            p1 = st.text_input("Password baru", type="password")
            p2 = st.text_input("Ulangi password", type="password")
            if st.form_submit_button("Simpan password", type="primary", use_container_width=True):
                if len(p1) < 6:
                    st.error("Password minimal 6 karakter.")
                elif p1 != p2:
                    st.error("Password dan ulangi password tidak sama.")
                else:
                    set_password(p1)
                    after_write("Set password aplikasi")
                    st.session_state["unlocked"] = True
                    st.rerun()
        return

    st.caption("Masukkan password untuk membuka aplikasi.")
    with st.form("login", clear_on_submit=True):
        pw = st.text_input("Password", type="password")
        if st.form_submit_button("Masuk", type="primary", use_container_width=True):
            if check_password(pw):
                st.session_state["unlocked"] = True
                st.rerun()
            else:
                st.error("Password salah.")


# ---------------------------------------------------------------- pages


def page_input(today: date) -> None:
    st.subheader("Tambah pengeluaran")
    show_flash()

    categories = db.DEFAULT_CATEGORIES + [
        c for c in db.categories_in_use() if c not in db.DEFAULT_CATEGORIES
    ]

    with st.form("add_tx", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            tx_date = st.date_input("Tanggal", value=today, max_value=today)
        with col2:
            category = st.selectbox("Kategori", categories)
        description = st.text_input(
            "Keterangan", placeholder="mis. makan siang, bensin, token listrik"
        )
        amount = st.number_input(
            "Nominal (Rp)", min_value=1, step=1000, value=10_000, format="%d"
        )
        if st.form_submit_button("Simpan", type="primary", use_container_width=True):
            db.add_transaction(tx_date, category, description, int(amount))
            after_write(f"Tambah: {category} {rupiah(amount)}")
            st.session_state["flash"] = f"Tersimpan: {category} — {rupiah(amount)}"
            st.rerun()

    st.divider()
    render_transaction_table(today)


def render_transaction_table(today: date) -> None:
    st.subheader("Daftar pengeluaran")

    current = today.strftime("%Y-%m")
    options = ["Semua bulan"] + [month_label(m) for m in month_options(current)]
    label_to_month = {month_label(m): m for m in month_options(current)}

    col1, col2 = st.columns(2)
    with col1:
        chosen = st.selectbox(
            "Periode", options, index=safe_index(options, month_label(current))
        )
    with col2:
        chosen_cat = st.selectbox(
            "Kategori", ["Semua kategori"] + sorted(db.categories_in_use())
        )

    start = end = None
    if chosen != "Semua bulan":
        start, end = month_bounds(label_to_month[chosen])

    rows = db.list_transactions(start, end)
    if chosen_cat != "Semua kategori":
        rows = [r for r in rows if r["category"] == chosen_cat]

    if not rows:
        st.info("Belum ada transaksi pada periode ini.")
        return

    total = sum(r["amount"] for r in rows)
    st.caption(f"{len(rows)} transaksi · total {rupiah(total)}")

    display = pd.DataFrame(rows)
    display["tx_date"] = pd.to_datetime(display["tx_date"]).dt.strftime("%d/%m/%Y")
    display["amount"] = display["amount"].map(rupiah)
    st.dataframe(
        display.rename(
            columns={
                "id": "ID",
                "tx_date": "Tanggal",
                "category": "Kategori",
                "description": "Keterangan",
                "amount": "Nominal",
            }
        )[["ID", "Tanggal", "Kategori", "Keterangan", "Nominal"]],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("**Ubah / hapus**")
    choices = {
        f"#{r['id']} · {r['tx_date']} · {r['category']} · {rupiah(r['amount'])}": r
        for r in rows
    }
    row = choices[st.selectbox("Pilih transaksi", list(choices))]

    with st.expander("Ubah transaksi"):
        with st.form(f"edit_tx_{row['id']}"):
            e_date = st.date_input(
                "Tanggal", value=datetime.strptime(row["tx_date"], "%Y-%m-%d").date()
            )
            cats = db.DEFAULT_CATEGORIES + [
                c for c in db.categories_in_use() if c not in db.DEFAULT_CATEGORIES
            ]
            e_cat = st.selectbox(
                "Kategori",
                cats,
                index=safe_index(cats, row["category"]),
            )
            e_desc = st.text_input("Keterangan", value=row["description"])
            e_amount = st.number_input(
                "Nominal (Rp)",
                min_value=1,
                value=int(row["amount"]),
                step=1000,
                format="%d",
            )
            if st.form_submit_button("Simpan perubahan", type="primary"):
                db.update_transaction(
                    row["id"], e_date.isoformat(), e_cat, e_desc, int(e_amount)
                )
                after_write(f"Ubah transaksi #{row['id']}")
                st.session_state["flash"] = "Perubahan tersimpan."
                st.rerun()

    with st.expander("Hapus transaksi"):
        confirm = st.checkbox(
            f"Ya, hapus transaksi #{row['id']} ({rupiah(row['amount'])})"
        )
        if st.button("Hapus", disabled=not confirm):
            db.delete_transaction(row["id"])
            after_write(f"Hapus transaksi #{row['id']}")
            st.session_state["flash"] = "Transaksi dihapus."
            st.rerun()


def page_dashboard(today: date) -> None:
    st.subheader("Dashboard")

    current = today.strftime("%Y-%m")
    label_to_month = {month_label(m): m for m in month_options(current)}
    chosen = st.selectbox("Bulan", list(label_to_month), key="dash_month")
    month = label_to_month[chosen]
    start, end = month_bounds(month)

    rows = db.list_transactions(start, end)
    if not rows:
        st.info("Belum ada transaksi pada bulan ini.")
        return

    df = pd.DataFrame(rows)
    df["tx_date"] = pd.to_datetime(df["tx_date"])

    total = int(df["amount"].sum())
    days_elapsed = today.day if month == current else int(df["tx_date"].dt.day.max())
    biggest = df.loc[df["amount"].idxmax()]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total bulan ini", rupiah(total))
    c2.metric("Transaksi", len(df))
    c3.metric("Rata-rata / hari", rupiah(total / max(days_elapsed, 1)))
    c4.metric(
        "Terbesar",
        rupiah(biggest["amount"]),
        help=f"{biggest['category']} — {biggest['description'] or '-'}",
    )

    by_cat = (
        df.groupby("category", as_index=False)["amount"]
        .sum()
        .sort_values("amount", ascending=False)
    )

    col_left, col_right = st.columns(2)
    with col_left:
        fig = px.pie(
            by_cat, names="category", values="amount", hole=0.5,
            title="Pengeluaran per kategori",
            color_discrete_sequence=["#111827", "#374151", "#6B7280", "#9CA3AF", "#D1D5DB"],
        )
        fig.update_traces(
            textinfo="percent+label",
            hovertemplate="%{label}<br>Rp %{value:,.0f}<extra></extra>",
        )
        fig.update_layout(
            showlegend=False,
            margin=dict(t=40, b=10, l=10, r=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col_right:
        fig2 = px.bar(
            by_cat.sort_values("amount"), x="amount", y="category",
            orientation="h", title="Peringkat kategori",
            labels={"amount": "Nominal", "category": ""},
            color_discrete_sequence=["#111827"],
        )
        fig2.update_traces(hovertemplate="%{y}<br>Rp %{x:,.0f}<extra></extra>")
        fig2.update_layout(
            margin=dict(t=40, b=10, l=10, r=10),
            xaxis=dict(tickformat=",.0f"),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig2, use_container_width=True)

    daily = df.groupby(df["tx_date"].dt.day)["amount"].sum().reset_index()
    daily.columns = ["tanggal", "amount"]
    fig3 = px.line(
        daily, x="tanggal", y="amount", markers=True,
        title="Tren pengeluaran harian",
        labels={"tanggal": "Tanggal", "amount": "Nominal"},
    )
    fig3.update_traces(
        line_color="#111827", marker_color="#111827",
        hovertemplate="Tgl %{x}<br>Rp %{y:,.0f}<extra></extra>",
    )
    fig3.update_layout(
        margin=dict(t=40, b=10, l=10, r=10),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig3, use_container_width=True)


def page_budget(today: date) -> None:
    st.subheader("Budget bulanan")
    show_flash()

    current = today.strftime("%Y-%m")
    label_to_month = {month_label(m): m for m in month_options(current, include_budgets=True)}
    chosen = st.selectbox("Bulan", list(label_to_month), key="budget_month")
    month = label_to_month[chosen]

    categories = db.DEFAULT_CATEGORIES + [
        c for c in db.categories_in_use() if c not in db.DEFAULT_CATEGORIES
    ]

    with st.expander("Atur budget", expanded=not db.list_budgets(month)):
        with st.form("set_budget", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                b_cat = st.selectbox("Kategori", categories)
            with col2:
                b_amount = st.number_input(
                    "Budget (Rp)", min_value=0, step=50_000, value=500_000, format="%d"
                )
            if st.form_submit_button("Simpan budget", type="primary"):
                db.set_budget(month, b_cat, int(b_amount))
                after_write(f"Budget {b_cat} {month}")
                st.session_state["flash"] = f"Budget {b_cat} = {rupiah(b_amount)}"
                st.rerun()

        prev_months = [
            m
            for m in month_options(current, include_budgets=True)
            if m < month and db.list_budgets(m)
        ]
        if prev_months:
            col_a, col_b = st.columns([2, 1])
            with col_a:
                src = st.selectbox(
                    "Salin budget dari",
                    prev_months,
                    format_func=month_label,
                    key="copy_budget_src",
                )
            with col_b:
                st.write("")
                if st.button("Salin", use_container_width=True):
                    n = db.copy_budgets(src, month)
                    after_write(f"Salin {n} budget dari {src} ke {month}")
                    st.session_state["flash"] = f"{n} budget disalin dari {month_label(src)}."
                    st.session_state["budget_month"] = month_label(month)
                    st.rerun()

    budgets = db.list_budgets(month)
    if not budgets:
        st.info("Belum ada budget untuk bulan ini.")
        return

    start, end = month_bounds(month)
    spent: dict[str, int] = {}
    for r in db.list_transactions(start, end):
        spent[r["category"]] = spent.get(r["category"], 0) + r["amount"]

    total_budget = sum(b["amount"] for b in budgets)
    total_spent = sum(spent.get(b["category"], 0) for b in budgets)
    pct = (total_spent / total_budget * 100) if total_budget else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Total budget", rupiah(total_budget))
    c2.metric("Terpakai", rupiah(total_spent))
    sisa = total_budget - total_spent
    c3.metric("Sisa", rupiah(sisa))

    st.progress(min(pct / 100, 1.0), text=f"{pct:.0f}% dari total budget terpakai")
    if pct >= 100:
        st.error("Total pengeluaran sudah melewati total budget bulan ini.")
    elif pct >= 80:
        st.warning("Total pengeluaran sudah mencapai 80% dari budget.")

    st.divider()
    for b in budgets:
        used = spent.get(b["category"], 0)
        ratio = used / b["amount"] if b["amount"] else (1.0 if used else 0.0)
        remaining = b["amount"] - used

        col1, col2 = st.columns([5, 1])
        with col1:
            st.markdown(f"**{b['category']}** — {rupiah(used)} / {rupiah(b['amount'])}")
            st.progress(min(ratio, 1.0))
            if ratio >= 1:
                st.caption(f"Lewat budget {rupiah(abs(remaining))}")
            elif ratio >= 0.8:
                st.caption(f"Hampir habis, sisa {rupiah(remaining)}")
            else:
                st.caption(f"Sisa {rupiah(remaining)}")
        with col2:
            if st.button("Hapus", key=f"del_budget_{b['id']}", use_container_width=True):
                db.delete_budget(b["id"])
                after_write(f"Hapus budget {b['category']} {month}")
                st.session_state["flash"] = f"Budget {b['category']} dihapus."
                st.rerun()


def page_categories() -> None:
    st.subheader("Kategori")
    show_flash()

    used = db.categories_in_use()
    counts: dict[str, int] = {}
    for r in db.list_transactions():
        counts[r["category"]] = counts.get(r["category"], 0) + 1

    st.caption(
        "Kategori bawaan tidak bisa dihapus. Kategori tambahan muncul setelah dipakai."
    )

    if used:
        df = pd.DataFrame(
            [{"Kategori": c, "Transaksi": counts.get(c, 0)} for c in used]
        ).sort_values("Transaksi", ascending=False)
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**Ganti nama / gabung kategori**")
    if used:
        with st.form("merge_category"):
            col1, col2 = st.columns(2)
            with col1:
                old = st.selectbox("Kategori lama", sorted(used))
            with col2:
                target = st.selectbox(
                    "Jadikan",
                    sorted(set(used) | set(db.DEFAULT_CATEGORIES)),
                )
            if st.form_submit_button("Terapkan", type="primary"):
                if old == target:
                    st.warning("Kategori lama dan tujuan sama.")
                else:
                    n = db.merge_old_categories({old: target})
                    after_write(f"Gabung kategori {old} -> {target}")
                    st.session_state["flash"] = f"{n} transaksi dipindah."
                    st.rerun()

    st.divider()
    st.markdown("**Hapus kategori tambahan**")
    extra = [c for c in used if c not in db.DEFAULT_CATEGORIES]
    if not extra:
        st.caption("Tidak ada kategori tambahan.")
    else:
        victim = st.selectbox("Kategori", extra, key="del_cat")
        st.caption("Transaksi kategori ini akan dipindah ke Lainnya.")
        confirm = st.checkbox(f"Ya, hapus kategori {victim}", key="confirm_del_cat")
        if st.button("Hapus kategori", disabled=not confirm):
            db.delete_category(victim)
            after_write(f"Hapus kategori {victim}")
            st.session_state["flash"] = f"Kategori {victim} dihapus."
            st.rerun()


def page_export(today: date) -> None:
    st.subheader("Export rekap")

    current = today.strftime("%Y-%m")
    options = ["Semua bulan"] + [month_label(m) for m in month_options(current)]
    label_to_month = {month_label(m): m for m in month_options(current)}

    chosen = st.selectbox("Periode", options, key="export_month")
    start = end = None
    if chosen != "Semua bulan":
        start, end = month_bounds(label_to_month[chosen])

    rows = db.list_transactions(start, end)
    if not rows:
        st.info("Tidak ada data untuk diexport.")
        return

    df = pd.DataFrame(rows)[["tx_date", "category", "description", "amount"]]
    df.columns = ["Tanggal", "Kategori", "Keterangan", "Nominal"]
    df["Tanggal"] = pd.to_datetime(df["Tanggal"])

    summary = (
        df.groupby("Kategori", as_index=False)["Nominal"]
        .sum()
        .sort_values("Nominal", ascending=False)
    )
    summary.loc[len(summary)] = ["TOTAL", int(df["Nominal"].sum())]

    suffix = "semua" if chosen == "Semua bulan" else label_to_month[chosen]
    stamp = datetime.now().strftime("%Y%m%d")
    pdf_bytes = build_pdf(rows, chosen, "pribadi")

    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Transaksi", index=False)
        summary.to_excel(writer, sheet_name="Rekap Kategori", index=False)

        ws = writer.sheets["Transaksi"]
        for col, width in zip("ABCD", (12, 22, 40, 16)):
            ws.column_dimensions[col].width = width
        for idx in range(2, len(df) + 2):
            ws.cell(row=idx, column=4).number_format = "#,##0"
            ws.cell(row=idx, column=1).number_format = "DD/MM/YYYY"

        ws2 = writer.sheets["Rekap Kategori"]
        ws2.column_dimensions["A"].width = 28
        ws2.column_dimensions["B"].width = 18
        for idx in range(2, len(summary) + 2):
            ws2.cell(row=idx, column=2).number_format = "#,##0"

    col_xls, col_pdf = st.columns(2)
    with col_xls:
        st.download_button(
            "Download Excel",
            data=excel_buf.getvalue(),
            file_name=f"rekap-pengeluaran-{suffix}-{stamp}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            use_container_width=True,
        )
    with col_pdf:
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name=f"rekap-pengeluaran-{suffix}-{stamp}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

    st.divider()
    st.markdown("**Pratinjau rekap kategori**")
    preview = summary.copy()
    preview["Nominal"] = preview["Nominal"].map(rupiah)
    st.dataframe(preview, use_container_width=True, hide_index=True)

    st.markdown("**Export CSV (data mentah)**")
    st.download_button(
        "Download CSV",
        data=df.assign(Tanggal=df["Tanggal"].dt.strftime("%Y-%m-%d"))
        .to_csv(index=False)
        .encode("utf-8"),
        file_name=f"rekap-pengeluaran-{suffix}-{stamp}.csv",
        mime="text/csv",
        use_container_width=True,
    )


def page_settings() -> None:
    st.subheader("Pengaturan & sinkronisasi")
    show_flash()

    state = sync_state()
    c1, c2 = st.columns(2)
    c1.metric("Status", state.status)
    c2.metric("Sync terakhir", state.last_sync or "belum pernah")

    if not state.enabled:
        st.info(
            "Sync GitHub tidak aktif — data hanya tersimpan di file lokal. "
            "Isi kredensial untuk menyimpan snapshot di repo private:"
        )
        st.code(
            '[github]\ntoken = "github_pat_xxx"\n'
            'data_repo = "username/rekap-kas-data"\ndata_branch = "main"',
            language="toml",
        )
        st.caption(
            "Lokal: simpan di `.streamlit/secrets.toml`. "
            "Streamlit Cloud: Settings -> Secrets."
        )
    else:
        st.caption(f"Repo data: `{state.repo}` · branch `{state.branch}`")
        if state.error:
            st.error(state.error)
        elif state.dirty:
            st.warning("Ada perubahan lokal yang belum terkirim ke repo.")

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Kirim sekarang", type="primary", use_container_width=True):
                push_sync("Sync manual")
                st.rerun()
        with col2:
            if st.button("Tarik ulang dari repo", use_container_width=True):
                st.session_state["confirm_pull"] = True
        with col3:
            if st.button("Timpa repo dengan data lokal", use_container_width=True):
                st.session_state["confirm_overwrite"] = True

        if st.session_state.get("confirm_pull"):
            st.warning(
                "Tarik ulang akan MENGGANTI database lokal dengan snapshot di repo. "
                "Perubahan lokal yang belum terkirim akan hilang."
            )
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Ya, tarik dan ganti lokal", type="primary"):
                    try:
                        sha = sync.restore_from_repo(st.session_state["sync_repo"])
                    except github_store.GitHubError as exc:
                        st.error(str(exc))
                    else:
                        if sha is None:
                            st.error(
                                "Repo data belum punya kas.db — tidak ada yang bisa ditarik."
                            )
                        else:
                            db.init_db()
                            st.session_state["sync_sha"] = sha
                            st.session_state["sync_dirty"] = False
                            st.session_state["sync_error"] = None
                            st.session_state.pop("confirm_pull", None)
                            st.session_state["boot_done"] = False
                            st.session_state["flash"] = (
                                "Database lokal diganti dengan snapshot repo."
                            )
                            st.rerun()
            with col_b:
                if st.button("Batal", key="cancel_pull"):
                    st.session_state.pop("confirm_pull", None)
                    st.rerun()

        if st.session_state.get("confirm_overwrite"):
            st.warning(
                "Data lokal akan dikirim dan MENIMPA snapshot di repo. "
                "Kalau perangkat lain sudah menambah data, data itu akan hilang."
            )
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Ya, timpa repo", type="primary"):
                    repo = st.session_state["sync_repo"]
                    try:
                        fresh_sha = repo.get_sha(sync.DB_FILE)
                        st.session_state["sync_sha"] = fresh_sha
                        sha = sync.push_to_repo(repo, fresh_sha, "Timpa snapshot dengan data lokal")
                    except github_store.GitHubError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["sync_sha"] = sha
                        st.session_state["sync_dirty"] = False
                        st.session_state["sync_error"] = None
                        st.session_state.pop("confirm_overwrite", None)
                        st.session_state["flash"] = "Snapshot repo ditimpa data lokal."
                        st.rerun()
            with col_b:
                if st.button("Batal", key="cancel_overwrite"):
                    st.session_state.pop("confirm_overwrite", None)
                    st.rerun()

    st.divider()
    st.markdown("**Backup manual**")
    st.download_button(
        "Unduh kas.db",
        data=sync.snapshot_bytes(),
        file_name=f"kas-{datetime.now().strftime('%Y%m%d-%H%M')}.db",
        mime="application/octet-stream",
        use_container_width=True,
    )

    st.divider()
    st.markdown("**Ganti password**")
    if st.session_state.get("confirm_password"):
        with st.form("change_password"):
            old = st.text_input("Password lama", type="password")
            new1 = st.text_input("Password baru", type="password")
            new2 = st.text_input("Ulangi password baru", type="password")
            if st.form_submit_button("Simpan password baru", type="primary"):
                if not check_password(old):
                    st.error("Password lama salah.")
                elif len(new1) < 6:
                    st.error("Password baru minimal 6 karakter.")
                elif new1 != new2:
                    st.error("Password baru dan ulangi tidak sama.")
                else:
                    set_password(new1)
                    after_write("Ganti password aplikasi")
                    st.session_state.pop("confirm_password", None)
                    st.session_state["flash"] = "Password diganti."
                    st.rerun()
    else:
        if st.button("Ganti password"):
            st.session_state["confirm_password"] = True
            st.rerun()

    st.divider()
    st.markdown("**Kunci aplikasi**")
    if st.button("Keluar sekarang"):
        st.session_state.pop("unlocked", None)
        st.rerun()


# ---------------------------------------------------------------- main


def main() -> None:
    bootstrap()

    if not st.session_state.get("unlocked"):
        render_gate()
        return

    today = date.today()
    state = sync_state()

    with st.sidebar:
        st.markdown("#### Rekap Bayar Kas")
        st.caption("Pencatat pengeluaran pribadi")
        page = st.radio(
            "Menu",
            ["Input", "Dashboard", "Budget", "Kategori", "Export", "Pengaturan"],
            label_visibility="collapsed",
        )
        st.divider()
        if state.enabled:
            badge = {
                "Tersinkron": "●",
                "Error": "●",
                "Ada perubahan belum terkirim": "●",
            }.get(state.status, "○")
            st.caption(f"{badge} GitHub: {state.status}")
        else:
            st.caption("○ GitHub: sync nonaktif")

    if state.enabled and state.error:
        st.error(f"Sync GitHub: {state.error}")

    if page == "Input":
        page_input(today)
    elif page == "Dashboard":
        page_dashboard(today)
    elif page == "Budget":
        page_budget(today)
    elif page == "Kategori":
        page_categories()
    elif page == "Export":
        page_export(today)
    else:
        page_settings()


main()
