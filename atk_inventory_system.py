import streamlit as st
import pandas as pd
import sqlite3
import hashlib
import os
from datetime import datetime, date
from contextlib import contextmanager

# ------------------ Konfigurasi Halaman ------------------
st.set_page_config(
    page_title="Sistem Inventori ATK",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------ Database Setup ------------------
DB_FILE = "atk_inventory.db"

@contextmanager
def get_connection():
    """Context manager untuk koneksi database dengan error handling"""
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        st.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()

def hash_password(password: str, salt: str = "atk_system_salt"):
    """Hash password dengan salt untuk keamanan lebih baik"""
    return hashlib.sha256((password + salt).encode()).hexdigest()

# ------------------ Init DB ------------------
def init_database():
    """Inisialisasi database dengan error handling"""
    try:
        with get_connection() as conn:
            c = conn.cursor()

            # Tabel admin dengan trigger untuk updated_at
            c.execute("""
                CREATE TABLE IF NOT EXISTS admin_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    nama TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Tabel barang dengan trigger untuk updated_at
            c.execute("""
                CREATE TABLE IF NOT EXISTS barang (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nama_barang TEXT NOT NULL,
                    kategori TEXT NOT NULL,
                    satuan TEXT NOT NULL,
                    stok INTEGER NOT NULL DEFAULT 0,
                    minimum_stok INTEGER NOT NULL DEFAULT 10,
                    harga_satuan REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Trigger untuk auto-update updated_at
            c.execute("""
                CREATE TRIGGER IF NOT EXISTS update_barang_timestamp 
                AFTER UPDATE ON barang
                BEGIN
                    UPDATE barang SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
                END
            """)

            # Tabel permintaan
            c.execute("""
                CREATE TABLE IF NOT EXISTS permintaan (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nama_karyawan TEXT NOT NULL,
                    divisi TEXT NOT NULL,
                    barang_id INTEGER NOT NULL,
                    jumlah INTEGER NOT NULL,
                    catatan TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    tanggal_permintaan TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    tanggal_diproses TIMESTAMP,
                    processed_by INTEGER,
                    alasan_tolak TEXT,
                    FOREIGN KEY (barang_id) REFERENCES barang (id),
                    FOREIGN KEY (processed_by) REFERENCES admin_users (id)
                )
            """)

            # Tabel stok masuk
            c.execute("""
                CREATE TABLE IF NOT EXISTS stok_masuk (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    barang_id INTEGER NOT NULL,
                    jumlah INTEGER NOT NULL,
                    harga_satuan REAL,
                    total_harga REAL,
                    supplier TEXT,
                    tanggal_masuk DATE NOT NULL,
                    catatan TEXT,
                    admin_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (barang_id) REFERENCES barang (id),
                    FOREIGN KEY (admin_id) REFERENCES admin_users (id)
                )
            """)

            # Tabel stok keluar
            c.execute("""
                CREATE TABLE IF NOT EXISTS stok_keluar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    barang_id INTEGER NOT NULL,
                    jumlah INTEGER NOT NULL,
                    permintaan_id INTEGER,
                    tanggal_keluar DATE NOT NULL,
                    catatan TEXT,
                    admin_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (barang_id) REFERENCES barang (id),
                    FOREIGN KEY (permintaan_id) REFERENCES permintaan (id),
                    FOREIGN KEY (admin_id) REFERENCES admin_users (id)
                )
            """)

            # Insert default admin jika belum ada
            c.execute("SELECT COUNT(*) FROM admin_users")
            if c.fetchone()[0] == 0:
                c.execute("INSERT INTO admin_users (username,password,nama) VALUES (?,?,?)",
                          ("admin", hash_password("admin123"), "Administrator"))

            # Sample barang
            c.execute("SELECT COUNT(*) FROM barang")
            if c.fetchone()[0] == 0:
                sample_barang = [
                    ("Pulpen Biru", "Alat Tulis", "Pcs", 50, 10, 2500),
                    ("Pulpen Hitam", "Alat Tulis", "Pcs", 45, 10, 2500),
                    ("Pensil 2B", "Alat Tulis", "Pcs", 30, 15, 1500),
                    ("Kertas A4", "Kertas", "Rim", 20, 5, 65000),
                    ("Kertas A3", "Kertas", "Rim", 10, 3, 85000),
                    ("Stapler", "Alat Kantor", "Pcs", 10, 3, 45000),
                    ("Lem Stick", "Perlengkapan", "Pcs", 25, 8, 8000),
                    ("Tinta Printer", "Printer", "Pcs", 15, 5, 125000)
                ]
                c.executemany("""
                    INSERT INTO barang (nama_barang,kategori,satuan,stok,minimum_stok,harga_satuan)
                    VALUES (?,?,?,?,?,?)
                """, sample_barang)

            conn.commit()
            return True
    except Exception as e:
        st.error(f"Gagal inisialisasi database: {e}")
        return False

# ------------------ Fungsi Utility dengan Error Handling ------------------
def authenticate_admin(username, password):
    """Autentikasi admin dengan validasi input"""
    if not username or not password:
        return None
    
    try:
        with get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM admin_users WHERE username=? AND password=?",
                      (username.strip(), hash_password(password)))
            row = c.fetchone()
            return dict(row) if row else None
    except Exception as e:
        st.error(f"Error saat login: {e}")
        return None

def get_barang_list():
    """Ambil daftar barang dengan error handling"""
    try:
        with get_connection() as conn:
            df = pd.read_sql_query("SELECT * FROM barang ORDER BY nama_barang", conn)
            return df
    except Exception as e:
        st.error(f"Error mengambil data barang: {e}")
        return pd.DataFrame()

def get_requests(status_filter=None):
    """Ambil daftar permintaan dengan filter status"""
    try:
        with get_connection() as conn:
            query = """
                SELECT p.id, p.nama_karyawan, p.divisi, b.nama_barang, p.jumlah, p.status,
                       p.tanggal_permintaan, p.catatan, p.alasan_tolak, b.stok as stok_tersedia,
                       a.nama as processed_by_name, p.tanggal_diproses
                FROM permintaan p
                JOIN barang b ON p.barang_id=b.id
                LEFT JOIN admin_users a ON p.processed_by=a.id
            """
            if status_filter:
                query += f" WHERE p.status='{status_filter}'"
            query += " ORDER BY p.tanggal_permintaan DESC"
            
            df = pd.read_sql_query(query, conn)
            return df
    except Exception as e:
        st.error(f"Error mengambil data permintaan: {e}")
        return pd.DataFrame()

def validate_input(nama, divisi, jumlah):
    """Validasi input form"""
    errors = []
    if not nama or len(nama.strip()) < 2:
        errors.append("Nama harus diisi minimal 2 karakter")
    if not divisi or len(divisi.strip()) < 2:
        errors.append("Divisi harus diisi minimal 2 karakter")
    if jumlah <= 0:
        errors.append("Jumlah harus lebih dari 0")
    if jumlah > 1000:
        errors.append("Jumlah terlalu besar (maksimal 1000)")
    return errors

def update_stok(barang_id, jumlah_keluar, admin_id, permintaan_id=None):
    """Update stok barang dan catat stok keluar"""
    try:
        with get_connection() as conn:
            c = conn.cursor()
            
            # Update stok barang
            c.execute("UPDATE barang SET stok = stok - ? WHERE id = ?", (jumlah_keluar, barang_id))
            
            # Catat stok keluar
            c.execute("""
                INSERT INTO stok_keluar (barang_id, jumlah, permintaan_id, tanggal_keluar, admin_id)
                VALUES (?, ?, ?, ?, ?)
            """, (barang_id, jumlah_keluar, permintaan_id, date.today(), admin_id))
            
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Error update stok: {e}")
        return False

# ------------------ Public Interface ------------------
def show_public_inventory():
    """Tampilkan inventori untuk public dengan tampilan yang lebih baik"""
    st.subheader("📦 Daftar Stok ATK")
    
    df = get_barang_list()
    if df.empty:
        st.info("Belum ada data barang")
        return
    
    # Filter berdasarkan kategori
    kategoris = df['kategori'].unique().tolist()
    kategori_filter = st.selectbox("Filter berdasarkan kategori:", ["Semua"] + kategoris)
    
    if kategori_filter != "Semua":
        df = df[df['kategori'] == kategori_filter]
    
    # Tampilkan dalam format yang lebih rapi
    cols = st.columns(3)
    for idx, (_, row) in enumerate(df.iterrows()):
        col = cols[idx % 3]
        
        with col:
            # Tentukan status dan warna
            if row['stok'] == 0:
                status = "🔴 HABIS"
                status_color = "red"
            elif row['stok'] <= row['minimum_stok']:
                status = "🟡 Menipis"
                status_color = "orange"
            else:
                status = "🟢 Tersedia"
                status_color = "green"
            
            st.markdown(f"""
            <div style="border: 1px solid #ddd; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                <h4>{row['nama_barang']}</h4>
                <p><strong>Kategori:</strong> {row['kategori']}</p>
                <p><strong>Stok:</strong> {row['stok']} {row['satuan']}</p>
                <p style="color: {status_color};"><strong>{status}</strong></p>
            </div>
            """, unsafe_allow_html=True)

def show_public_request_form():
    """Form permintaan ATK dengan validasi yang lebih baik"""
    st.subheader("📝 Form Permintaan ATK")
    
    df = get_barang_list()
    df_available = df[df['stok'] > 0]
    
    if df_available.empty:
        st.warning("Tidak ada barang tersedia saat ini")
        return
    
    with st.form("req_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            nama = st.text_input("Nama Lengkap *", placeholder="Masukkan nama lengkap")
            divisi = st.text_input("Divisi *", placeholder="Masukkan nama divisi")
        
        with col2:
            barang_options = [f"{row['nama_barang']} (Stok: {row['stok']} {row['satuan']})" 
                            for _, row in df_available.iterrows()]
            barang_selected = st.selectbox("Pilih Barang *", barang_options)
            
            # Ambil stok maksimal untuk barang yang dipilih
            if barang_selected:
                selected_idx = barang_options.index(barang_selected)
                max_stok = df_available.iloc[selected_idx]['stok']
                jumlah = st.number_input("Jumlah *", min_value=1, max_value=max_stok, value=1)
                st.caption(f"Stok tersedia: {max_stok}")
        
        catatan = st.text_area("Catatan (opsional)", placeholder="Tambahkan catatan jika diperlukan")
        
        submitted = st.form_submit_button("📤 Kirim Permintaan", use_container_width=True)
        
        if submitted:
            # Validasi input
            errors = validate_input(nama, divisi, jumlah)
            
            if errors:
                for error in errors:
                    st.error(error)
            else:
                # Ambil data barang yang dipilih
                selected_idx = barang_options.index(barang_selected)
                selected_barang = df_available.iloc[selected_idx]
                
                # Cek lagi stok terbaru
                current_df = get_barang_list()
                current_barang = current_df[current_df['id'] == selected_barang['id']].iloc[0]
                
                if current_barang['stok'] < jumlah:
                    st.error(f"Stok tidak mencukupi! Stok saat ini: {current_barang['stok']}")
                else:
                    # Simpan permintaan
                    try:
                        with get_connection() as conn:
                            c = conn.cursor()
                            c.execute("""
                                INSERT INTO permintaan (nama_karyawan, divisi, barang_id, jumlah, catatan)
                                VALUES (?, ?, ?, ?, ?)
                            """, (nama.strip(), divisi.strip(), selected_barang['id'], jumlah, catatan.strip() or None))
                            conn.commit()
                            
                            st.success("✅ Permintaan berhasil dikirim! Admin akan memproses permintaan Anda.")
                            st.info("💡 Anda dapat mengecek status permintaan melalui menu 'Status Permintaan'")
                    except Exception as e:
                        st.error(f"Gagal mengirim permintaan: {e}")

def show_request_status():
    """Tampilkan status permintaan"""
    st.subheader("📋 Status Permintaan")
    
    # Filter berdasarkan nama atau divisi
    col1, col2 = st.columns(2)
    with col1:
        nama_filter = st.text_input("Cari berdasarkan nama:")
    with col2:
        divisi_filter = st.text_input("Cari berdasarkan divisi:")
    
    df = get_requests()
    
    # Apply filters
    if nama_filter:
        df = df[df['nama_karyawan'].str.contains(nama_filter, case=False, na=False)]
    if divisi_filter:
        df = df[df['divisi'].str.contains(divisi_filter, case=False, na=False)]
    
    if df.empty:
        st.info("Tidak ada data permintaan")
        return
    
    # Tampilkan data dengan styling
    for _, row in df.iterrows():
        status_color = {
            'pending': 'orange',
            'approved': 'green', 
            'rejected': 'red'
        }.get(row['status'], 'gray')
        
        status_text = {
            'pending': '⏳ Menunggu',
            'approved': '✅ Disetujui',
            'rejected': '❌ Ditolak'
        }.get(row['status'], row['status'])
        
        with st.expander(f"{row['nama_karyawan']} - {row['nama_barang']} ({status_text})"):
            col1, col2 = st.columns(2)
            
            with col1:
                st.write(f"**Nama:** {row['nama_karyawan']}")
                st.write(f"**Divisi:** {row['divisi']}")
                st.write(f"**Barang:** {row['nama_barang']}")
                st.write(f"**Jumlah:** {row['jumlah']}")
            
            with col2:
                st.write(f"**Status:** {status_text}")
                st.write(f"**Tanggal Permintaan:** {row['tanggal_permintaan']}")
                if row['tanggal_diproses']:
                    st.write(f"**Tanggal Diproses:** {row['tanggal_diproses']}")
                if row['processed_by_name']:
                    st.write(f"**Diproses oleh:** {row['processed_by_name']}")
            
            if row['catatan']:
                st.write(f"**Catatan:** {row['catatan']}")
            if row['alasan_tolak']:
                st.write(f"**Alasan Penolakan:** {row['alasan_tolak']}")

# ------------------ Admin Interface ------------------
def show_admin_login():
    """Tampilan login admin yang lebih baik"""
    st.subheader("🔐 Login Admin")
    
    with st.form("login_form"):
        username = st.text_input("Username", placeholder="Masukkan username")
        password = st.text_input("Password", type="password", placeholder="Masukkan password")
        login_btn = st.form_submit_button("🚀 Login", use_container_width=True)
        
        if login_btn:
            if not username or not password:
                st.error("Username dan password harus diisi!")
            else:
                admin = authenticate_admin(username, password)
                if admin:
                    st.session_state.admin = admin
                    st.success("Login berhasil!")
                    st.rerun()
                else:
                    st.error("Username atau password salah!")
    
    st.info("💡 **Default Login:** Username: `admin`, Password: `admin123`")

def show_admin_dashboard():
    """Dashboard admin lengkap"""
    admin = st.session_state.admin
    
    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title(f"👋 Selamat datang, {admin['nama']}")
    with col2:
        if st.button("🚪 Logout"):
            del st.session_state.admin
            st.rerun()
    
    # Menu tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "✅ Kelola Permintaan", "📦 Kelola Barang", "📈 Laporan"])
    
    with tab1:
        show_dashboard_overview()
    
    with tab2:
        show_items_list()
    
    with tab3:
        show_stock_in_form()

def show_add_item_form():
    """Form tambah barang baru"""
    st.subheader("➕ Tambah Barang Baru")
    
    with st.form("add_item_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            nama_barang = st.text_input("Nama Barang *", placeholder="Contoh: Pulpen Biru")
            kategori = st.selectbox("Kategori *", 
                                   ["Alat Tulis", "Kertas", "Alat Kantor", "Perlengkapan", "Printer", "Lainnya"])
            satuan = st.selectbox("Satuan *", ["Pcs", "Rim", "Pack", "Dus", "Lusin", "Kg", "Liter"])
        
        with col2:
            stok_awal = st.number_input("Stok Awal", min_value=0, value=0)
            minimum_stok = st.number_input("Minimum Stok", min_value=1, value=10)
            harga_satuan = st.number_input("Harga Satuan (Rp)", min_value=0.0, value=0.0, format="%.2f")
        
        if st.form_submit_button("💾 Simpan Barang", use_container_width=True):
            if nama_barang and kategori and satuan:
                try:
                    with get_connection() as conn:
                        c = conn.cursor()
                        c.execute("""
                            INSERT INTO barang (nama_barang, kategori, satuan, stok, minimum_stok, harga_satuan)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (nama_barang.strip(), kategori, satuan, stok_awal, minimum_stok, harga_satuan))
                        conn.commit()
                        
                        st.success(f"✅ Barang '{nama_barang}' berhasil ditambahkan!")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"Gagal menambah barang: {e}")
            else:
                st.error("Nama barang, kategori, dan satuan harus diisi!")

def show_items_list():
    """Tampilkan dan kelola daftar barang"""
    st.subheader("📋 Daftar Barang")
    
    df = get_barang_list()
    if df.empty:
        st.info("Belum ada data barang")
        return
    
    # Filter dan pencarian
    col1, col2 = st.columns(2)
    with col1:
        search = st.text_input("🔍 Cari barang:", placeholder="Ketik nama barang...")
    with col2:
        kategori_filter = st.selectbox("Filter kategori:", 
                                     ["Semua"] + df['kategori'].unique().tolist())
    
    # Apply filters
    filtered_df = df.copy()
    if search:
        filtered_df = filtered_df[filtered_df['nama_barang'].str.contains(search, case=False, na=False)]
    if kategori_filter != "Semua":
        filtered_df = filtered_df[filtered_df['kategori'] == kategori_filter]
    
    # Tampilkan tabel dengan opsi edit
    for _, row in filtered_df.iterrows():
        with st.expander(f"{row['nama_barang']} - Stok: {row['stok']} {row['satuan']}"):
            col1, col2, col3 = st.columns([2, 2, 1])
            
            with col1:
                st.write(f"**ID:** {row['id']}")
                st.write(f"**Kategori:** {row['kategori']}")
                st.write(f"**Satuan:** {row['satuan']}")
                
            with col2:
                st.write(f"**Stok Saat Ini:** {row['stok']}")
                st.write(f"**Minimum Stok:** {row['minimum_stok']}")
                st.write(f"**Harga Satuan:** Rp {row['harga_satuan']:,.2f}")
                
                # Status stok
                if row['stok'] == 0:
                    st.error("🔴 HABIS")
                elif row['stok'] <= row['minimum_stok']:
                    st.warning("🟡 MENIPIS")
                else:
                    st.success("🟢 TERSEDIA")
            
            with col3:
                # Form edit cepat untuk minimum stok dan harga
                with st.form(f"quick_edit_{row['id']}"):
                    new_min_stok = st.number_input("Min Stok:", value=row['minimum_stok'], key=f"min_{row['id']}")
                    new_harga = st.number_input("Harga:", value=row['harga_satuan'], format="%.2f", key=f"price_{row['id']}")
                    
                    if st.form_submit_button("💾 Update"):
                        update_item_details(row['id'], new_min_stok, new_harga)
                        st.rerun()

def show_stock_in_form():
    """Form penambahan stok barang"""
    st.subheader("📈 Tambah Stok Masuk")
    
    df = get_barang_list()
    if df.empty:
        st.info("Belum ada data barang")
        return
    
    with st.form("stock_in_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            barang_options = [f"{row['nama_barang']} (Stok: {row['stok']} {row['satuan']})" 
                            for _, row in df.iterrows()]
            selected_barang = st.selectbox("Pilih Barang *", barang_options)
            jumlah_masuk = st.number_input("Jumlah Masuk *", min_value=1, value=1)
            harga_satuan = st.number_input("Harga Satuan (Rp)", min_value=0.0, format="%.2f")
        
        with col2:
            supplier = st.text_input("Supplier", placeholder="Nama supplier/toko")
            tanggal_masuk = st.date_input("Tanggal Masuk", value=date.today())
            catatan = st.text_area("Catatan", placeholder="Catatan tambahan")
        
        if st.form_submit_button("📦 Tambah Stok", use_container_width=True):
            if selected_barang and jumlah_masuk > 0:
                # Ambil data barang yang dipilih
                selected_idx = barang_options.index(selected_barang)
                barang_data = df.iloc[selected_idx]
                
                total_harga = harga_satuan * jumlah_masuk if harga_satuan > 0 else 0
                
                try:
                    with get_connection() as conn:
                        c = conn.cursor()
                        
                        # Insert ke stok_masuk
                        c.execute("""
                            INSERT INTO stok_masuk (barang_id, jumlah, harga_satuan, total_harga, 
                                                   supplier, tanggal_masuk, catatan, admin_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (barang_data['id'], jumlah_masuk, harga_satuan, total_harga,
                              supplier or None, tanggal_masuk, catatan or None, st.session_state.admin['id']))
                        
                        # Update stok barang
                        c.execute("UPDATE barang SET stok = stok + ? WHERE id = ?", 
                                (jumlah_masuk, barang_data['id']))
                        
                        # Update harga satuan jika diisi
                        if harga_satuan > 0:
                            c.execute("UPDATE barang SET harga_satuan = ? WHERE id = ?", 
                                    (harga_satuan, barang_data['id']))
                        
                        conn.commit()
                        st.success(f"✅ Berhasil menambah {jumlah_masuk} {barang_data['satuan']} {barang_data['nama_barang']}")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"Gagal menambah stok: {e}")
            else:
                st.error("Barang dan jumlah harus diisi!")

def update_item_details(item_id, min_stok, harga):
    """Update detail barang"""
    try:
        with get_connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE barang SET minimum_stok = ?, harga_satuan = ? WHERE id = ?", 
                     (min_stok, harga, item_id))
            conn.commit()
            st.success("✅ Data barang berhasil diupdate!")
            return True
    except Exception as e:
        st.error(f"Gagal update barang: {e}")
        return False

def show_reports():
    """Tampilkan laporan dan statistik"""
    st.subheader("📈 Laporan & Statistik")
    
    tab1, tab2, tab3 = st.tabs(["📊 Ringkasan", "📋 Stok Masuk", "📤 Stok Keluar"])
    
    with tab1:
        show_summary_report()
    
    with tab2:
        show_stock_in_report()
    
    with tab3:
        show_stock_out_report()

def show_summary_report():
    """Laporan ringkasan"""
    st.subheader("📊 Ringkasan Sistem")
    
    try:
        with get_connection() as conn:
            # Statistik dasar
            col1, col2, col3, col4 = st.columns(4)
            
            # Total barang
            total_barang = pd.read_sql_query("SELECT COUNT(*) as count FROM barang", conn).iloc[0]['count']
            
            # Total nilai inventori
            total_nilai = pd.read_sql_query("""
                SELECT SUM(stok * harga_satuan) as total FROM barang WHERE harga_satuan > 0
            """, conn).iloc[0]['total'] or 0
            
            # Total permintaan bulan ini
            permintaan_bulan = pd.read_sql_query("""
                SELECT COUNT(*) as count FROM permintaan 
                WHERE strftime('%Y-%m', tanggal_permintaan) = strftime('%Y-%m', 'now')
            """, conn).iloc[0]['count']
            
            # Permintaan disetujui bulan ini
            approved_bulan = pd.read_sql_query("""
                SELECT COUNT(*) as count FROM permintaan 
                WHERE status = 'approved' 
                AND strftime('%Y-%m', tanggal_permintaan) = strftime('%Y-%m', 'now')
            """, conn).iloc[0]['count']
            
            with col1:
                st.metric("Total Barang", total_barang, "📦")
            with col2:
                st.metric("Nilai Inventori", f"Rp {total_nilai:,.0f}", "💰")
            with col3:
                st.metric("Permintaan Bulan Ini", permintaan_bulan, "📝")
            with col4:
                st.metric("Disetujui Bulan Ini", approved_bulan, "✅")
            
            # Grafik permintaan per bulan
            st.subheader("📈 Tren Permintaan")
            monthly_requests = pd.read_sql_query("""
                SELECT 
                    strftime('%Y-%m', tanggal_permintaan) as bulan,
                    COUNT(*) as total_permintaan,
                    SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as disetujui,
                    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as ditolak,
                    SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
                FROM permintaan 
                GROUP BY strftime('%Y-%m', tanggal_permintaan)
                ORDER BY bulan DESC
                LIMIT 6
            """, conn)
            
            if not monthly_requests.empty:
                st.bar_chart(monthly_requests.set_index('bulan')[['disetujui', 'ditolak', 'pending']])
            
            # Top 10 barang paling sering diminta
            st.subheader("🏆 Top 10 Barang Terpopuler")
            top_items = pd.read_sql_query("""
                SELECT b.nama_barang, COUNT(p.id) as total_permintaan,
                       SUM(CASE WHEN p.status = 'approved' THEN p.jumlah ELSE 0 END) as total_keluar
                FROM permintaan p
                JOIN barang b ON p.barang_id = b.id
                GROUP BY b.id, b.nama_barang
                ORDER BY total_permintaan DESC
                LIMIT 10
            """, conn)
            
            if not top_items.empty:
                st.dataframe(top_items, use_container_width=True)
    
    except Exception as e:
        st.error(f"Error generating report: {e}")

def show_stock_in_report():
    """Laporan stok masuk"""
    st.subheader("📋 Laporan Stok Masuk")
    
    # Filter tanggal
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Dari Tanggal:", value=date.today().replace(day=1))
    with col2:
        end_date = st.date_input("Sampai Tanggal:", value=date.today())
    
    try:
        with get_connection() as conn:
            stock_in_data = pd.read_sql_query("""
                SELECT sm.tanggal_masuk, b.nama_barang, sm.jumlah, b.satuan,
                       sm.harga_satuan, sm.total_harga, sm.supplier, sm.catatan,
                       a.nama as admin_name
                FROM stok_masuk sm
                JOIN barang b ON sm.barang_id = b.id
                JOIN admin_users a ON sm.admin_id = a.id
                WHERE sm.tanggal_masuk BETWEEN ? AND ?
                ORDER BY sm.tanggal_masuk DESC
            """, conn, params=(start_date, end_date))
            
            if stock_in_data.empty:
                st.info("Tidak ada data stok masuk dalam periode tersebut")
            else:
                # Ringkasan
                total_transaksi = len(stock_in_data)
                total_nilai = stock_in_data['total_harga'].sum()
                
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("Total Transaksi", total_transaksi)
                with col2:
                    st.metric("Total Nilai", f"Rp {total_nilai:,.0f}")
                
                # Tabel detail
                st.dataframe(stock_in_data, use_container_width=True)
                
                # Export CSV
                csv = stock_in_data.to_csv(index=False)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv,
                    file_name=f"stok_masuk_{start_date}_to_{end_date}.csv",
                    mime="text/csv"
                )
    
    except Exception as e:
        st.error(f"Error generating stock in report: {e}")

def show_stock_out_report():
    """Laporan stok keluar"""
    st.subheader("📤 Laporan Stok Keluar")
    
    # Filter tanggal
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Dari Tanggal:", value=date.today().replace(day=1), key="out_start")
    with col2:
        end_date = st.date_input("Sampai Tanggal:", value=date.today(), key="out_end")
    
    try:
        with get_connection() as conn:
            stock_out_data = pd.read_sql_query("""
                SELECT sk.tanggal_keluar, b.nama_barang, sk.jumlah, b.satuan,
                       p.nama_karyawan, p.divisi, sk.catatan, a.nama as admin_name
                FROM stok_keluar sk
                JOIN barang b ON sk.barang_id = b.id
                LEFT JOIN permintaan p ON sk.permintaan_id = p.id
                JOIN admin_users a ON sk.admin_id = a.id
                WHERE sk.tanggal_keluar BETWEEN ? AND ?
                ORDER BY sk.tanggal_keluar DESC
            """, conn, params=(start_date, end_date))
            
            if stock_out_data.empty:
                st.info("Tidak ada data stok keluar dalam periode tersebut")
            else:
                # Ringkasan
                total_transaksi = len(stock_out_data)
                
                st.metric("Total Transaksi Keluar", total_transaksi)
                
                # Tabel detail
                st.dataframe(stock_out_data, use_container_width=True)
                
                # Export CSV
                csv = stock_out_data.to_csv(index=False)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv,
                    file_name=f"stok_keluar_{start_date}_to_{end_date}.csv",
                    mime="text/csv"
                )
    
    except Exception as e:
        st.error(f"Error generating stock out report: {e}")

# ------------------ Main Application ------------------
def main():
    """Aplikasi utama"""
    
    # Inisialisasi database
    if not init_database():
        st.stop()
    
    # Sidebar navigation
    st.sidebar.title("🏢 Sistem Inventori ATK")
    
    # Cek apakah user sudah login sebagai admin
    if 'admin' in st.session_state:
        # Mode Admin
        st.sidebar.success(f"👋 {st.session_state.admin['nama']}")
        show_admin_dashboard()
    else:
        # Mode Public
        menu = st.sidebar.radio("📍 Menu Utama:", [
            "🏠 Beranda",
            "📦 Lihat Stok",
            "📝 Ajukan Permintaan", 
            "📋 Cek Status Permintaan",
            "🔐 Login Admin"
        ])
        
        if menu == "🏠 Beranda":
            st.title("🏢 Sistem Inventori ATK")
            st.markdown("""
            ### Selamat datang di Sistem Inventori ATK
            
            Sistem ini memungkinkan Anda untuk:
            - 📦 **Melihat stok** barang ATK yang tersedia
            - 📝 **Mengajukan permintaan** barang yang dibutuhkan
            - 📋 **Mengecek status** permintaan Anda
            
            ### Cara Menggunakan:
            1. **Lihat Stok**: Cek ketersediaan barang ATK
            2. **Ajukan Permintaan**: Isi form permintaan dengan lengkap
            3. **Cek Status**: Pantau status permintaan Anda
            4. **Admin**: Mengelola sistem (khusus admin)
            
            ### Kontak Admin:
            Jika ada pertanyaan, silakan hubungi admin sistem.
            """)
            
            # Tampilkan ringkasan stok yang menipis
            df = get_barang_list()
            if not df.empty:
                alert_items = df[df['stok'] <= df['minimum_stok']]
                if not alert_items.empty:
                    st.warning("⚠️ **Barang yang perlu segera direstock:**")
                    for _, item in alert_items.iterrows():
                        if item['stok'] == 0:
                            st.error(f"🔴 {item['nama_barang']} - HABIS")
                        else:
                            st.warning(f"🟡 {item['nama_barang']} - Sisa {item['stok']} {item['satuan']}")
        
        elif menu == "📦 Lihat Stok":
            show_public_inventory()
        
        elif menu == "📝 Ajukan Permintaan":
            show_public_request_form()
        
        elif menu == "📋 Cek Status Permintaan":
            show_request_status()
        
        elif menu == "🔐 Login Admin":
            show_admin_login()
    
    # Footer
    st.sidebar.markdown("---")
    st.sidebar.markdown("💡 **Tips**: Pastikan permintaan Anda lengkap dan jelas")
    st.sidebar.markdown("📞 **Support**: Hubungi admin untuk bantuan")

if __name__ == "__main__":
    main()
        show_manage_requests()
    
    with tab3:
        show_manage_inventory()
    
    with tab4:
        show_reports()

def show_dashboard_overview():
    """Dashboard overview dengan statistik"""
    st.subheader("📊 Overview Sistem")
    
    # Statistik cards
    col1, col2, col3, col4 = st.columns(4)
    
    with get_connection() as conn:
        # Total barang
        total_barang = pd.read_sql_query("SELECT COUNT(*) as count FROM barang", conn).iloc[0]['count']
        
        # Barang habis
        barang_habis = pd.read_sql_query("SELECT COUNT(*) as count FROM barang WHERE stok = 0", conn).iloc[0]['count']
        
        # Barang menipis
        barang_menipis = pd.read_sql_query("SELECT COUNT(*) as count FROM barang WHERE stok <= minimum_stok AND stok > 0", conn).iloc[0]['count']
        
        # Permintaan pending
        pending_requests = pd.read_sql_query("SELECT COUNT(*) as count FROM permintaan WHERE status = 'pending'", conn).iloc[0]['count']
    
    with col1:
        st.metric("Total Barang", total_barang, "📦")
    with col2:
        st.metric("Barang Habis", barang_habis, "🔴", delta_color="inverse")
    with col3:
        st.metric("Barang Menipis", barang_menipis, "🟡", delta_color="inverse")
    with col4:
        st.metric("Permintaan Pending", pending_requests, "⏳", delta_color="inverse")
    
    # Alert untuk barang habis/menipis
    df = get_barang_list()
    barang_alert = df[(df['stok'] == 0) | (df['stok'] <= df['minimum_stok'])]
    
    if not barang_alert.empty:
        st.warning("⚠️ **Alert Stok!**")
        for _, row in barang_alert.iterrows():
            if row['stok'] == 0:
                st.error(f"🔴 **{row['nama_barang']}** - HABIS")
            else:
                st.warning(f"🟡 **{row['nama_barang']}** - Menipis (Stok: {row['stok']})")

def show_manage_requests():
    """Kelola permintaan dengan approval workflow"""
    st.subheader("✅ Kelola Permintaan")
    
    # Filter status
    status_filter = st.selectbox("Filter Status:", ["Semua", "pending", "approved", "rejected"])
    filter_status = None if status_filter == "Semua" else status_filter
    
    df = get_requests(filter_status)
    
    if df.empty:
        st.info("Tidak ada permintaan")
        return
    
    # Tampilkan permintaan pending terlebih dahulu
    if filter_status is None or filter_status == "pending":
        pending_df = df[df['status'] == 'pending']
        
        if not pending_df.empty:
            st.subheader("⏳ Permintaan Pending")
            
            for _, row in pending_df.iterrows():
                with st.expander(f"ID: {row['id']} - {row['nama_karyawan']} ({row['nama_barang']})"):
                    col1, col2, col3 = st.columns([2, 2, 1])
                    
                    with col1:
                        st.write(f"**Nama:** {row['nama_karyawan']}")
                        st.write(f"**Divisi:** {row['divisi']}")
                        st.write(f"**Barang:** {row['nama_barang']}")
                        st.write(f"**Jumlah:** {row['jumlah']}")
                        if row['catatan']:
                            st.write(f"**Catatan:** {row['catatan']}")
                    
                    with col2:
                        st.write(f"**Stok Tersedia:** {row['stok_tersedia']}")
                        st.write(f"**Tanggal:** {row['tanggal_permintaan']}")
                        
                        # Cek apakah stok mencukupi
                        if row['stok_tersedia'] >= row['jumlah']:
                            st.success("✅ Stok mencukupi")
                        else:
                            st.error("❌ Stok tidak mencukupi")
                    
                    with col3:
                        # Tombol approve
                        if st.button("✅ Setujui", key=f"approve_{row['id']}", 
                                   disabled=row['stok_tersedia'] < row['jumlah']):
                            if approve_request(row['id'], st.session_state.admin['id']):
                                st.success("Permintaan disetujui!")
                                st.rerun()
                        
                        # Form reject dengan alasan
                        with st.form(f"reject_form_{row['id']}"):
                            alasan = st.text_area("Alasan penolakan:", key=f"reason_{row['id']}")
                            if st.form_submit_button("❌ Tolak"):
                                if alasan.strip():
                                    if reject_request(row['id'], st.session_state.admin['id'], alasan):
                                        st.success("Permintaan ditolak!")
                                        st.rerun()
                                else:
                                    st.error("Alasan penolakan harus diisi!")
    
    # Tampilkan riwayat semua permintaan
    st.subheader("📋 Riwayat Permintaan")
    
    # Display dataframe dengan formatting
    display_df = df.copy()
    display_df = display_df[['id', 'nama_karyawan', 'divisi', 'nama_barang', 'jumlah', 
                            'status', 'tanggal_permintaan', 'processed_by_name']]
    display_df.columns = ['ID', 'Nama', 'Divisi', 'Barang', 'Jumlah', 'Status', 'Tanggal', 'Diproses oleh']
    
    st.dataframe(display_df, use_container_width=True)

def approve_request(request_id, admin_id):
    """Setujui permintaan dan update stok"""
    try:
        with get_connection() as conn:
            c = conn.cursor()
            
            # Ambil detail permintaan
            c.execute("""
                SELECT p.*, b.stok 
                FROM permintaan p 
                JOIN barang b ON p.barang_id = b.id 
                WHERE p.id = ?
            """, (request_id,))
            request_data = dict(c.fetchone())
            
            if request_data['stok'] < request_data['jumlah']:
                st.error("Stok tidak mencukupi!")
                return False
            
            # Update status permintaan
            c.execute("""
                UPDATE permintaan 
                SET status = 'approved', tanggal_diproses = ?, processed_by = ?
                WHERE id = ?
            """, (datetime.now(), admin_id, request_id))
            
            # Update stok dan catat pengeluaran
            if update_stok(request_data['barang_id'], request_data['jumlah'], admin_id, request_id):
                conn.commit()
                return True
            else:
                conn.rollback()
                return False
                
    except Exception as e:
        st.error(f"Error menyetujui permintaan: {e}")
        return False

def reject_request(request_id, admin_id, alasan):
    """Tolak permintaan"""
    try:
        with get_connection() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE permintaan 
                SET status = 'rejected', tanggal_diproses = ?, processed_by = ?, alasan_tolak = ?
                WHERE id = ?
            """, (datetime.now(), admin_id, alasan, request_id))
            conn.commit()
            return True
    except Exception as e:
        st.error(f"Error menolak permintaan: {e}")
        return False

def show_manage_inventory():
    """Kelola inventori barang"""
    st.subheader("📦 Kelola Barang")
    
    tab1, tab2, tab3 = st.tabs(["📝 Tambah Barang", "📊 Daftar Barang", "📈 Stok Masuk"])
    
    with tab1:
        show_add_item_form()
    
    with tab2: