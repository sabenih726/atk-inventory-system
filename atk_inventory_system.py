import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, date
import hashlib
import altair as alt
from io import BytesIO

# -----------------------------
# Helpers & DB Layer
# -----------------------------
DB_PATH = 'atk_inventory.db'

STATUS_OPTIONS = ["Pending", "Approved", "Rejected", "Completed"]
ROLES = ["admin", "user"]

@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def run_migrations(conn):
    cur = conn.cursor()
    # Users
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            department TEXT,
            role TEXT NOT NULL CHECK(role in ('admin','user')),
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
        """
    )
    # Items
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT,
            unit TEXT NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            min_stock INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    # Requests
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            qty INTEGER NOT NULL,
            note TEXT,
            status TEXT NOT NULL CHECK(status in ('Pending','Approved','Rejected','Completed')),
            reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(item_id) REFERENCES items(id)
        )
        """
    )
    # Inventory transactions (stock in/out/adjust)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS inv_tx (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            tx_type TEXT NOT NULL CHECK(tx_type in ('IN','OUT','ADJ')),
            qty INTEGER NOT NULL,
            ref TEXT,
            note TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(item_id) REFERENCES items(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
        """
    )
    conn.commit()


def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode('utf-8')).hexdigest()


def seed_defaults(conn):
    cur = conn.cursor()
    # Seed admin and demo user if not exists
    cur.execute("SELECT COUNT(*) as c FROM users")
    if cur.fetchone()[0] == 0:
        now = datetime.utcnow().isoformat()
        cur.execute(
            "INSERT INTO users (username,name,department,role,password_hash,created_at) VALUES (?,?,?,?,?,?)",
            ("admin", "Administrator", "Office", "admin", hash_pw("admin"), now),
        )
        cur.execute(
            "INSERT INTO users (username,name,department,role,password_hash,created_at) VALUES (?,?,?,?,?,?)",
            ("user", "Demo User", "Finance", "user", hash_pw("user"), now),
        )
        conn.commit()
    # Seed sample items if empty
    cur.execute("SELECT COUNT(*) FROM items")
    if cur.fetchone()[0] == 0:
        now = datetime.utcnow().isoformat()
        items = [
            ("Pulpen Biru", "Alat Tulis", "pcs", 100, 20, now, now),
            ("Buku Tulis A5", "Kertas", "pcs", 50, 15, now, now),
            ("Kertas HVS A4 80gsm", "Kertas", "rim", 25, 10, now, now),
            ("Staples No.10", "Perlengkapan", "box", 12, 5, now, now),
        ]
        cur.executemany(
            "INSERT INTO items (name,category,unit,stock,min_stock,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            items,
        )
        conn.commit()


# -----------------------------
# Auth Utilities
# -----------------------------

def login(conn, username, password):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username=? AND is_active=1", (username,))
    row = cur.fetchone()
    if row and row["password_hash"] == hash_pw(password):
        return dict(row)
    return None


def require_auth():
    if "user" not in st.session_state:
        st.session_state.user = None


# -----------------------------
# UI Components
# -----------------------------

def badge(text, color="gray"):
    st.markdown(
        f"""
        <span style='background:{color};color:white;padding:2px 8px;border-radius:12px;font-size:12px;'>
        {text}
        </span>
        """,
        unsafe_allow_html=True,
    )


def status_color(status: str) -> str:
    return {
        "Pending": "#a3a3a3",
        "Approved": "#2563eb",
        "Rejected": "#dc2626",
        "Completed": "#16a34a",
    }.get(status, "#6b7280")


# -----------------------------
# INVENTORY PAGES (Admin)
# -----------------------------

def page_inventory(conn):
    st.subheader("Manajemen Inventori")
    tabs = st.tabs(["Daftar Barang", "Stok Masuk", "Penyesuaian Stok"])

    # 1) Daftar Barang
    with tabs[0]:
        st.markdown("#### Daftar Barang")
        with st.expander("Tambah Barang Baru"):
            with st.form("form_add_item"):
                name = st.text_input("Nama Barang")
                category = st.text_input("Kategori")
                unit = st.text_input("Satuan", value="pcs")
                min_stock = st.number_input("Batas Minimum (min stock)", min_value=0, step=1, value=0)
                submitted = st.form_submit_button("Simpan")
            if submitted:
                if not name or not unit:
                    st.error("Nama dan Satuan wajib diisi")
                else:
                    now = datetime.utcnow().isoformat()
                    conn.execute(
                        "INSERT INTO items (name,category,unit,stock,min_stock,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
                        (name, category, unit, 0, min_stock, now, now),
                    )
                    conn.commit()
                    st.success("Barang ditambahkan")
        # List + edit/delete
        q = st.text_input("Cari nama barang")
        cat = st.text_input("Filter kategori")
        items_df = pd.read_sql_query("SELECT * FROM items", conn)
        if q:
            items_df = items_df[items_df['name'].str.contains(q, case=False, na=False)]
        if cat:
            items_df = items_df[items_df['category'].fillna('').str.contains(cat, case=False, na=False)]

        # Color stock indicator
        def stock_indicator(row):
            if row['stock'] <= row['min_stock']:
                return 'Kritis'
            elif row['stock'] <= row['min_stock'] * 1.5:
                return 'Menipis'
            else:
                return 'Aman'
        items_df['indikator'] = items_df.apply(stock_indicator, axis=1)

        st.dataframe(
            items_df[['id','name','category','unit','stock','min_stock','indikator']]
            .rename(columns={'name':'Nama','category':'Kategori','unit':'Satuan','stock':'Sisa Stok','min_stock':'Min Stock','indikator':'Indikator'}),
            use_container_width=True,
        )

        with st.expander("Edit / Hapus Barang"):
            item_options = {f"{r['id']} - {r['name']}": r['id'] for _, r in items_df.iterrows()}
            sel = st.selectbox("Pilih Barang", options=list(item_options.keys())) if len(item_options) else None
            if sel:
                item_id = item_options[sel]
                r = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
                with st.form("form_edit_item"):
                    name = st.text_input("Nama", value=r['name'])
                    category = st.text_input("Kategori", value=r['category'] or "")
                    unit = st.text_input("Satuan", value=r['unit'])
                    min_stock = st.number_input("Min Stock", min_value=0, step=1, value=r['min_stock'])
                    col1, col2 = st.columns(2)
                    with col1:
                        save = st.form_submit_button("Simpan Perubahan")
                    with col2:
                        delete = st.form_submit_button("Hapus Barang", type="primary")
                if save:
                    now = datetime.utcnow().isoformat()
                    conn.execute(
                        "UPDATE items SET name=?, category=?, unit=?, min_stock=?, updated_at=? WHERE id=?",
                        (name, category, unit, int(min_stock), now, item_id),
                    )
                    conn.commit()
                    st.success("Perubahan disimpan")
                if delete:
                    # Ensure no foreign key issues (simple delete)
                    conn.execute("DELETE FROM items WHERE id=?", (item_id,))
                    conn.commit()
                    st.warning("Barang dihapus")

    # 2) Stok Masuk
    with tabs[1]:
        st.markdown("#### Stok Masuk (Restock)")
        items_df = pd.read_sql_query("SELECT id, name, unit FROM items ORDER BY name", conn)
        if items_df.empty:
            st.info("Belum ada barang.")
        else:
            name_to_id = {f"{r['name']} ({r['unit']})": r['id'] for _, r in items_df.iterrows()}
            with st.form("form_stock_in"):
                item_label = st.selectbox("Pilih Barang", list(name_to_id.keys()))
                qty = st.number_input("Jumlah Masuk", min_value=1, step=1)
                note = st.text_input("Catatan/Pembelian")
                submit = st.form_submit_button("Catat Stok Masuk")
            if submit:
                item_id = name_to_id[item_label]
                now = datetime.utcnow().isoformat()
                conn.execute("UPDATE items SET stock = stock + ?, updated_at=? WHERE id=?", (int(qty), now, item_id))
                conn.execute(
                    "INSERT INTO inv_tx (item_id, tx_type, qty, ref, note, created_by, created_at) VALUES (?,?,?,?,?,?,?)",
                    (item_id, 'IN', int(qty), 'RESTOCK', note, st.session_state.user['id'], now)
                )
                conn.commit()
                st.success("Stok masuk berhasil dicatat")

    # 3) Penyesuaian Stok
    with tabs[2]:
        st.markdown("#### Penyesuaian Stok (Stock Opname)")
        items_df = pd.read_sql_query("SELECT id, name, unit, stock FROM items ORDER BY name", conn)
        name_to_id = {f"{r['name']} (stok: {r['stock']} {r['unit']})": r['id'] for _, r in items_df.iterrows()}
        with st.form("form_adjust"):
            label = st.selectbox("Pilih Barang", list(name_to_id.keys()))
            new_stock = st.number_input("Stok Aktual", min_value=0, step=1)
            note = st.text_input("Catatan")
            submit = st.form_submit_button("Sesuaikan")
        if submit:
            item_id = name_to_id[label]
            cur = conn.execute("SELECT stock FROM items WHERE id=?", (item_id,)).fetchone()
            diff = int(new_stock) - int(cur['stock'])
            now = datetime.utcnow().isoformat()
            conn.execute("UPDATE items SET stock=?, updated_at=? WHERE id=?", (int(new_stock), now, item_id))
            conn.execute(
                "INSERT INTO inv_tx (item_id, tx_type, qty, ref, note, created_by, created_at) VALUES (?,?,?,?,?,?,?)",
                (item_id, 'ADJ', int(diff), 'ADJUST', note, st.session_state.user['id'], now)
            )
            conn.commit()
            st.success(f"Stok disesuaikan. Perubahan: {diff:+d}")


# -----------------------------
# REQUESTS (User & Admin)
# -----------------------------

def page_request_form(conn):
    st.subheader("Formulir Permintaan ATK")
    # Dropdown barang dengan sisa stok realtime
    items = pd.read_sql_query("SELECT id, name, unit, stock FROM items ORDER BY name", conn)
    if items.empty:
        st.info("Belum ada barang di inventori.")
        return
    options = {f"{r['name']} ({r['unit']})": r['id'] for _, r in items.iterrows()}
    selected_label = st.selectbox("Nama Barang", list(options.keys()))
    selected_id = options[selected_label]
    selected_item = items[items['id'] == selected_id].iloc[0]

    st.info(f"Sisa Stok: **{int(selected_item['stock'])} {selected_item['unit']}**")

    qty = st.number_input("Jumlah Dibutuhkan", min_value=1, step=1)
    note = st.text_area("Catatan (opsional)")

    # Validasi qty tidak melebihi stok saat approve (stok tidak berkurang di sini)
    can_submit = qty > 0
    submit = st.button("Kirim Permintaan", disabled=not can_submit)
    if submit:
        now = datetime.utcnow().isoformat()
        conn.execute(
            "INSERT INTO requests (user_id, item_id, qty, note, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (st.session_state.user['id'], int(selected_id), int(qty), note, 'Pending', now, now)
        )
        conn.commit()
        st.success("Permintaan dibuat. Status: Pending")


def page_requests_admin(conn):
    st.subheader("Daftar Permintaan (Admin)")
    df = pd.read_sql_query(
        """
        SELECT r.id, r.created_at, u.name as peminta, u.department, i.name as barang, i.unit, r.qty, r.status, r.reason
        FROM requests r
        JOIN users u ON u.id = r.user_id
        JOIN items i ON i.id = r.item_id
        ORDER BY r.id DESC
        """,
        conn,
    )
    st.dataframe(df, use_container_width=True)

    st.markdown("#### Proses Permintaan")
    ids = pd.read_sql_query("SELECT id, status FROM requests WHERE status='Pending' ORDER BY id DESC", conn)
    if ids.empty:
        st.info("Tidak ada permintaan Pending")
    else:
        id_list = ids['id'].astype(str).tolist()
        sel_id = st.selectbox("Pilih ID Permintaan (Pending)", id_list)
        req = conn.execute(
            "SELECT * FROM requests WHERE id=?", (int(sel_id),)
        ).fetchone()
        item = conn.execute("SELECT * FROM items WHERE id=?", (req['item_id'],)).fetchone()
        user = conn.execute("SELECT * FROM users WHERE id=?", (req['user_id'],)).fetchone()

        st.write(f"**Peminta:** {user['name']} ({user['department']})")
        st.write(f"**Barang:** {item['name']} ({item['unit']}) | **Qty:** {req['qty']}")
        st.write(f"**Sisa Stok Saat Ini:** {item['stock']} {item['unit']}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Setujui (Approve)"):
                if item['stock'] < req['qty']:
                    st.error("Stok tidak mencukupi untuk approve")
                else:
                    now = datetime.utcnow().isoformat()
                    # Kurangi stok
                    conn.execute("UPDATE items SET stock = stock - ?, updated_at=? WHERE id=?", (int(req['qty']), now, item['id']))
                    # Catat transaksi OUT
                    conn.execute(
                        "INSERT INTO inv_tx (item_id, tx_type, qty, ref, note, created_by, created_at) VALUES (?,?,?,?,?,?,?)",
                        (item['id'], 'OUT', int(req['qty']), f"REQ#{req['id']}", req['note'], st.session_state.user['id'], now)
                    )
                    # Update request status -> Approved
                    conn.execute("UPDATE requests SET status='Approved', updated_at=? WHERE id=?", (now, req['id']))
                    conn.commit()
                    st.success("Permintaan disetujui. Stok telah berkurang.")
        with col2:
            reason = st.text_input("Alasan Penolakan (jika ditolak)")
            if st.button("Tolak (Reject)"):
                now = datetime.utcnow().isoformat()
                conn.execute("UPDATE requests SET status='Rejected', reason=?, updated_at=? WHERE id=?", (reason, now, req['id']))
                conn.commit()
                st.warning("Permintaan ditolak.")

    st.markdown("#### Tandai Selesai (Completed)")
    ids2 = pd.read_sql_query("SELECT id FROM requests WHERE status='Approved' ORDER BY id DESC", conn)
    if ids2.empty:
        st.info("Tidak ada permintaan berstatus Approved")
    else:
        sel2 = st.selectbox("Pilih ID Permintaan (Approved)", ids2['id'].astype(str).tolist())
        if st.button("Tandai Completed"):
            now = datetime.utcnow().isoformat()
            conn.execute("UPDATE requests SET status='Completed', updated_at=? WHERE id=?", (now, int(sel2)))
            conn.commit()
            st.success("Permintaan ditandai Completed")


def page_requests_user(conn):
    st.subheader("Riwayat Permintaan Saya")
    uid = st.session_state.user['id']
    df = pd.read_sql_query(
        """
        SELECT r.id, r.created_at, i.name as barang, i.unit, r.qty, r.status, r.reason
        FROM requests r
        JOIN items i ON i.id = r.item_id
        WHERE r.user_id = ?
        ORDER BY r.id DESC
        """,
        conn,
        params=(uid,),
    )
    if df.empty:
        st.info("Belum ada permintaan.")
    else:
        # Status chip
        for _, row in df.iterrows():
            with st.container(border=True):
                st.write(f"**ID:** {row['id']} | **{row['barang']}** x {row['qty']} {row['unit']}")
                st.write(f"Tanggal: {row['created_at']}")
                st.markdown(
                    f"Status: <span style='color:white;background:{status_color(row['status'])};padding:2px 8px;border-radius:12px'>{row['status']}</span>",
                    unsafe_allow_html=True,
                )
                if row['reason']:
                    st.write(f"Alasan: {row['reason']}")


# -----------------------------
# REPORTS (Admin)
# -----------------------------

def df_to_excel_bytes(df: pd.DataFrame) -> bytes:
    out = BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    return out.getvalue()


def page_reports(conn):
    st.subheader("Laporan")
    tabs = st.tabs(["Penggunaan per Periode", "Penggunaan per Departemen/Karyawan", "Stok Menipis"])

    # 1) Usage per period
    with tabs[0]:
        st.markdown("#### Laporan Penggunaan per Periode")
        start = st.date_input("Dari", value=date(date.today().year, 1, 1))
        end = st.date_input("Sampai", value=date.today())
        q = """
            SELECT it.name as barang, it.unit, SUM(CASE WHEN tx.tx_type='OUT' THEN tx.qty ELSE 0 END) as total_keluar
            FROM inv_tx tx
            JOIN items it ON it.id = tx.item_id
            WHERE date(tx.created_at) BETWEEN ? AND ?
            GROUP BY it.name, it.unit
            ORDER BY total_keluar DESC
        """
        df = pd.read_sql_query(q, conn, params=(start.isoformat(), end.isoformat()))
        st.dataframe(df, use_container_width=True)
        if not df.empty:
            chart = alt.Chart(df).mark_bar().encode(
                x=alt.X('barang:N', sort='-y'),
                y='total_keluar:Q',
                tooltip=['barang','total_keluar']
            )
            st.altair_chart(chart, use_container_width=True)
            st.download_button("Unduh Excel", data=df_to_excel_bytes(df), file_name="laporan_penggunaan.xlsx")

    # 2) Usage per department/employee via requests
    with tabs[1]:
        st.markdown("#### Laporan Penggunaan per Departemen / Karyawan")
        q = """
            SELECT u.department, u.name as karyawan, i.name as barang, SUM(r.qty) as total_qty
            FROM requests r
            JOIN users u ON u.id = r.user_id
            JOIN items i ON i.id = r.item_id
            WHERE r.status IN ('Approved','Completed')
            GROUP BY u.department, u.name, i.name
            ORDER BY u.department, u.name
        """
        df = pd.read_sql_query(q, conn)
        st.dataframe(df, use_container_width=True)
        if not df.empty:
            st.download_button("Unduh Excel", data=df_to_excel_bytes(df), file_name="laporan_departemen_karyawan.xlsx")

    # 3) Low stock report
    with tabs[2]:
        st.markdown("#### Laporan Stok Menipis")
        q = "SELECT name as barang, category as kategori, unit, stock as sisa_stok, min_stock FROM items ORDER BY name"
        df = pd.read_sql_query(q, conn)
        df['status'] = df.apply(lambda r: 'Kritis' if r['sisa_stok'] <= r['min_stock'] else ('Menipis' if r['sisa_stok'] <= r['min_stock']*1.5 else 'Aman'), axis=1)
        low_df = df[df['status'].isin(['Kritis','Menipis'])]
        st.dataframe(low_df, use_container_width=True)
        if not low_df.empty:
            st.download_button("Unduh Excel", data=df_to_excel_bytes(low_df), file_name="laporan_stok_menipis.xlsx")


# -----------------------------
# USERS (Admin)
# -----------------------------

def page_users(conn):
    st.subheader("Manajemen Pengguna")
    with st.expander("Tambah Pengguna Baru"):
        with st.form("form_add_user"):
            username = st.text_input("Username")
            name = st.text_input("Nama Lengkap")
            department = st.text_input("Departemen")
            role = st.selectbox("Peran", ROLES)
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Simpan")
        if submit:
            if not (username and name and password):
                st.error("Username, Nama, dan Password wajib diisi")
            else:
                try:
                    conn.execute(
                        "INSERT INTO users (username,name,department,role,password_hash,is_active,created_at) VALUES (?,?,?,?,?,?,?)",
                        (username, name, department, role, hash_pw(password), 1, datetime.utcnow().isoformat()),
                    )
                    conn.commit()
                    st.success("Pengguna ditambahkan")
                except sqlite3.IntegrityError:
                    st.error("Username sudah digunakan")

    # List users
    df = pd.read_sql_query("SELECT id, username, name, department, role, is_active, created_at FROM users ORDER BY id DESC", conn)
    st.dataframe(df, use_container_width=True)

    with st.expander("Atur Status / Reset Password"):
        if df.empty:
            st.info("Belum ada pengguna")
        else:
            id_map = {f"{r['id']} - {r['username']} ({r['role']})": r['id'] for _, r in df.iterrows()}
            sel = st.selectbox("Pilih Pengguna", list(id_map.keys()))
            if sel:
                uid = id_map[sel]
                row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
                col1, col2 = st.columns(2)
                with col1:
                    active_toggle = st.toggle("Aktif?", value=bool(row['is_active']))
                    save = st.button("Simpan Status")
                with col2:
                    new_pw = st.text_input("Password Baru", type="password")
                    reset = st.button("Reset Password")
                if save:
                    conn.execute("UPDATE users SET is_active=? WHERE id=?", (1 if active_toggle else 0, uid))
                    conn.commit()
                    st.success("Status diperbarui")
                if reset and new_pw:
                    conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_pw(new_pw), uid))
                    conn.commit()
                    st.success("Password direset")


# -----------------------------
# DASHBOARD
# -----------------------------

def page_dashboard(conn):
    st.subheader("Dashboard")
    # Stats
    pending = conn.execute("SELECT COUNT(*) FROM requests WHERE status='Pending'").fetchone()[0]
    low = conn.execute("SELECT COUNT(*) FROM items WHERE stock <= min_stock").fetchone()[0]
    approve_today = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE status='Approved' AND date(updated_at)=date('now')"
    ).fetchone()[0]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Permintaan Pending", pending)
    with c2:
        st.metric("Barang Stok Kritis", low)
    with c3:
        st.metric("Approved Hari Ini", approve_today)

    # Recent requests table (limit 5)
    st.markdown("#### 5 Permintaan Terbaru")
    df = pd.read_sql_query(
        """
        SELECT r.id, r.created_at, u.name as peminta, i.name as barang, r.qty, r.status
        FROM requests r
        JOIN users u ON u.id = r.user_id
        JOIN items i ON i.id = r.item_id
        ORDER BY r.id DESC
        LIMIT 5
        """,
        conn,
    )
    st.dataframe(df, use_container_width=True)

    # Simple monthly usage chart
    st.markdown("#### Grafik Penggunaan Bulanan (OUT)")
    q = """
        SELECT substr(created_at,1,7) as bulan, SUM(CASE WHEN tx_type='OUT' THEN qty ELSE 0 END) as total_out
        FROM inv_tx
        GROUP BY substr(created_at,1,7)
        ORDER BY bulan
    """
    mdf = pd.read_sql_query(q, conn)
    if not mdf.empty:
        chart = alt.Chart(mdf).mark_line(point=True).encode(
            x='bulan:T', y='total_out:Q', tooltip=['bulan','total_out']
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Belum ada data transaksi.")


# -----------------------------
# PUBLIC INVENTORY DISPLAY (All)
# -----------------------------

def page_public_inventory(conn):
    st.subheader("Daftar Stok ATK")
    q = st.text_input("Cari nama barang")
    cat = st.text_input("Filter kategori")
    items_df = pd.read_sql_query("SELECT name, category, unit, stock, min_stock FROM items", conn)
    if q:
        items_df = items_df[items_df['name'].str.contains(q, case=False, na=False)]
    if cat:
        items_df = items_df[items_df['category'].fillna('').str.contains(cat, case=False, na=False)]
    def label_status(r):
        if r['stock'] <= r['min_stock']:
            return 'Merah - Kritis'
        elif r['stock'] <= r['min_stock']*1.5:
            return 'Kuning - Menipis'
        else:
            return 'Hijau - Aman'
    items_df['Status Stok'] = items_df.apply(label_status, axis=1)
    st.dataframe(
        items_df.rename(columns={'name':'Nama Barang','category':'Kategori','unit':'Satuan','stock':'Sisa Stok'}),
        use_container_width=True,
    )
    st.caption("Kode warna: Hijau (Aman), Kuning (Menipis), Merah (Kritis)")


# -----------------------------
# MAIN APP
# -----------------------------

def main():
    st.set_page_config(page_title="Inventori ATK", layout="wide")
    st.title("📦 Sistem Inventori ATK")

    conn = get_conn()
    run_migrations(conn)
    seed_defaults(conn)

    require_auth()

    # AUTH
    if st.session_state.user is None:
        st.sidebar.header("Login")
        username = st.sidebar.text_input("Username")
        password = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Masuk"):
            u = login(conn, username, password)
            if u:
                st.session_state.user = u
                st.rerun()
            else:
                st.sidebar.error("Login gagal")

        st.info("Anda dapat melihat daftar stok tanpa login.")
        page_public_inventory(conn)
        st.stop()

    # Logged in
    user = st.session_state.user
    with st.sidebar:
        st.markdown(f"**Masuk sebagai:** {user['name']} ({user['role']})")
        menu = ["Dashboard", "Daftar Stok", "Buat Permintaan", "Riwayat Permintaan"]
        if user['role'] == 'admin':
            menu += ["Manajemen Inventori", "Daftar Permintaan", "Laporan", "Pengguna"]
        choice = st.selectbox("Menu", menu)
        if st.button("Keluar"):
            st.session_state.user = None
            st.rerun()

    # Router
    if choice == "Dashboard":
        page_dashboard(conn)
    elif choice == "Daftar Stok":
        page_public_inventory(conn)
    elif choice == "Buat Permintaan":
        page_request_form(conn)
    elif choice == "Riwayat Permintaan":
        page_requests_user(conn)
    elif choice == "Manajemen Inventori":
        if user['role'] != 'admin':
            st.error("Akses ditolak")
        else:
            page_inventory(conn)
    elif choice == "Daftar Permintaan":
        if user['role'] != 'admin':
            st.error("Akses ditolak")
        else:
            page_requests_admin(conn)
    elif choice == "Laporan":
        if user['role'] != 'admin':
            st.error("Akses ditolak")
        else:
            page_reports(conn)
    elif choice == "Pengguna":
        if user['role'] != 'admin':
            st.error("Akses ditolak")
        else:
            page_users(conn)


if __name__ == '__main__':
    main()
