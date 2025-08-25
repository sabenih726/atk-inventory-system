import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime, date
import plotly.express as px
import plotly.graph_objects as go

# Konfigurasi halaman
st.set_page_config(
    page_title="Sistem Inventori ATK",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database setup
def init_database():
    conn = sqlite3.connect('atk_inventory.db')
    cursor = conn.cursor()
    
    # Tabel admin (hanya untuk admin)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            nama TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabel barang
    cursor.execute('''
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
    ''')
    
    # Tabel permintaan (tanpa foreign key user, langsung nama dan divisi)
    cursor.execute('''
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
    ''')
    
    # Tabel stok masuk
    cursor.execute('''
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
    ''')
    
    # Tabel stok keluar (untuk penyesuaian stok)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stok_keluar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            barang_id INTEGER NOT NULL,
            jumlah INTEGER NOT NULL,
            tanggal_keluar TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            keperluan TEXT,
            processed_by INTEGER,
            FOREIGN KEY (barang_id) REFERENCES barang (id),
            FOREIGN KEY (processed_by) REFERENCES admin_users (id)
        )
    ''')
    
    # Insert admin default jika belum ada
    cursor.execute("SELECT COUNT(*) FROM admin_users")
    if cursor.fetchone()[0] == 0:
        admin_password = hashlib.sha256("admin123".encode()).hexdigest()
        cursor.execute('''
            INSERT INTO admin_users (username, password, nama)
            VALUES (?, ?, ?)
        ''', ("admin", admin_password, "Administrator"))
    
    # Insert sample data barang jika belum ada
    cursor.execute("SELECT COUNT(*) FROM barang")
    if cursor.fetchone()[0] == 0:
        sample_barang = [
            ("Pulpen Hitam", "Alat Tulis", "Pcs", 50, 10, 2500),
            ("Pulpen Biru", "Alat Tulis", "Pcs", 45, 10, 2500),
            ("Kertas A4", "Kertas", "Rim", 25, 5, 65000),
            ("Stapler", "Alat Kantor", "Pcs", 15, 3, 45000),
            ("Klip Kertas", "Alat Kantor", "Box", 20, 5, 8000),
            ("Spidol Whiteboard", "Alat Tulis", "Pcs", 30, 8, 15000),
            ("Penghapus", "Alat Tulis", "Pcs", 40, 10, 3000),
            ("Pensil 2B", "Alat Tulis", "Pcs", 35, 10, 2000)
        ]
        cursor.executemany('''
            INSERT INTO barang (nama_barang, kategori, satuan, stok, minimum_stok, harga_satuan)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', sample_barang)
    
    conn.commit()
    conn.close()

# Fungsi utilitas
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_connection():
    return sqlite3.connect('atk_inventory.db')

def authenticate_admin(username, password):
    conn = get_connection()
    cursor = conn.cursor()
    hashed_password = hash_password(password)
    cursor.execute('''
        SELECT id, username, nama 
        FROM admin_users 
        WHERE username = ? AND password = ?
    ''', (username, hashed_password))
    admin = cursor.fetchone()
    conn.close()
    return admin

def get_barang_list():
    conn = get_connection()
    df = pd.read_sql_query('''
        SELECT id, nama_barang, kategori, satuan, stok, minimum_stok, harga_satuan
        FROM barang
        ORDER BY nama_barang
    ''', conn)
    conn.close()
    return df

def get_all_requests():
    conn = get_connection()
    df = pd.read_sql_query('''
        SELECT p.id, p.nama_karyawan, p.divisi, b.nama_barang, p.jumlah, 
               p.catatan, p.status, p.tanggal_permintaan, p.alasan_tolak,
               b.stok as stok_tersedia
        FROM permintaan p
        JOIN barang b ON p.barang_id = b.id
        ORDER BY p.tanggal_permintaan DESC
    ''', conn)
    conn.close()
    return df

# Fungsi untuk mendapatkan statistik
def get_dashboard_stats():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Total barang
    cursor.execute("SELECT COUNT(*) FROM barang")
    total_barang = cursor.fetchone()[0]
    
    # Barang stok menipis
    cursor.execute("SELECT COUNT(*) FROM barang WHERE stok <= minimum_stok")
    stok_menipis = cursor.fetchone()[0]
    
    # Permintaan pending
    cursor.execute("SELECT COUNT(*) FROM permintaan WHERE status = 'pending'")
    pending_requests = cursor.fetchone()[0]
    
    # Total permintaan bulan ini
    cursor.execute('''
        SELECT COUNT(*) FROM permintaan 
        WHERE strftime('%Y-%m', tanggal_permintaan) = strftime('%Y-%m', 'now')
    ''')
    monthly_requests = cursor.fetchone()[0]
    
    conn.close()
    return total_barang, stok_menipis, pending_requests, monthly_requests

# CSS untuk styling
def load_css():
    st.markdown("""
    <style>
    .main-header {
        text-align: center;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 2rem;
        border-radius: 10px;
        margin-bottom: 2rem;
    }
    .metric-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
    .success-metric {
        background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
    }
    .warning-metric {
        background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
    }
    .danger-metric {
        background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%);
        color: #333;
    }
    .stok-aman { 
        background-color: #d4edda !important; 
        color: #155724 !important; 
        padding: 8px; 
        border-radius: 5px; 
        margin: 3px 0;
    }
    .stok-menipis { 
        background-color: #fff3cd !important; 
        color: #856404 !important; 
        padding: 8px; 
        border-radius: 5px; 
        margin: 3px 0;
    }
    .stok-kritis { 
        background-color: #f8d7da !important; 
        color: #721c24 !important; 
        padding: 8px; 
        border-radius: 5px; 
        margin: 3px 0;
    }
    .status-pending { background-color: #fff3cd !important; color: #856404 !important; }
    .status-approved { background-color: #d4edda !important; color: #155724 !important; }
    .status-rejected { background-color: #f8d7da !important; color: #721c24 !important; }
    .status-completed { background-color: #d1ecf1 !important; color: #0c5460 !important; }
    .request-card {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 15px;
        margin: 10px 0;
        background: white;
    }
    </style>
    """, unsafe_allow_html=True)

# Halaman Utama (Public - Tanpa Login untuk Karyawan)
def show_main_page():
    st.markdown("""
    <div class="main-header">
        <h1>🏢 Sistem Inventori ATK</h1>
        <p>Portal Permintaan Alat Tulis Kantor</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Tab untuk karyawan dan admin
    tab1, tab2, tab3 = st.tabs(["📦 Lihat Stok ATK", "📝 Form Permintaan", "👨‍💼 Login Admin"])
    
    with tab1:
        show_public_inventory()
    
    with tab2:
        show_public_request_form()
    
    with tab3:
        show_admin_login()

# Halaman Inventori Publik (untuk karyawan)
def show_public_inventory():
    st.subheader("📦 Daftar Stok ATK")
    st.write("Lihat ketersediaan stok barang ATK di perusahaan")
    
    df = get_barang_list()
    
    if not df.empty:
        # Filter dan pencarian
        col1, col2 = st.columns(2)
        with col1:
            search = st.text_input("🔍 Cari barang...", placeholder="Ketik nama barang")
        with col2:
            categories = ["Semua"] + list(df['kategori'].unique())
            selected_category = st.selectbox("🏷️ Filter Kategori", categories)
        
        # Apply filters
        filtered_df = df.copy()
        if search:
            filtered_df = filtered_df[filtered_df['nama_barang'].str.contains(search, case=False)]
        if selected_category != "Semua":
            filtered_df = filtered_df[filtered_df['kategori'] == selected_category]
        
        # Display cards
        for _, row in filtered_df.iterrows():
            if row['stok'] == 0:
                status_class = "stok-kritis"
                status_text = "🔴 HABIS"
                status_emoji = "🔴"
            elif row['stok'] <= row['minimum_stok']:
                status_class = "stok-menipis" 
                status_text = "🟡 MENIPIS"
                status_emoji = "🟡"
            else:
                status_class = "stok-aman"
                status_text = "🟢 TERSEDIA"
                status_emoji = "🟢"
            
            st.markdown(f"""
            <div class="{status_class}">
                <strong>📦 {row['nama_barang']}</strong><br>
                <small>Kategori: {row['kategori']} | Satuan: {row['satuan']}</small><br>
                <strong>Stok: {row['stok']} {row['satuan']}</strong> - {status_text}
            </div>
            """, unsafe_allow_html=True)
        
        # Summary cards
        st.subheader("📊 Ringkasan Stok")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            aman_count = len(filtered_df[filtered_df['stok'] > filtered_df['minimum_stok']])
            st.success(f"🟢 Stok Tersedia: {aman_count} item")
        
        with col2:
            menipis_count = len(filtered_df[(filtered_df['stok'] <= filtered_df['minimum_stok']) & (filtered_df['stok'] > 0)])
            st.warning(f"🟡 Stok Menipis: {menipis_count} item")
        
        with col3:
            habis_count = len(filtered_df[filtered_df['stok'] == 0])
            st.error(f"🔴 Stok Habis: {habis_count} item")
    
    else:
        st.info("Belum ada data barang dalam sistem.")

# Form Permintaan Publik (untuk karyawan)
def show_public_request_form():
    st.subheader("📝 Form Permintaan ATK")
    st.write("Isi form di bawah ini untuk mengajukan permintaan ATK")
    
    df_barang = get_barang_list()
    available_barang = df_barang[df_barang['stok'] > 0]  # Hanya barang yang tersedia
    
    if available_barang.empty:
        st.warning("⚠️ Saat ini tidak ada barang yang tersedia untuk diminta.")
        st.info("Silakan hubungi admin untuk informasi lebih lanjut.")
        return
    
    with st.form("public_request_form"):
        st.markdown("### 👤 Informasi Pemohon")
        col1, col2 = st.columns(2)
        
        with col1:
            nama_karyawan = st.text_input("Nama Lengkap*", placeholder="Masukkan nama lengkap Anda")
        with col2:
            divisi_options = [
                "IT", "HRD", "Finance", "Marketing", "Operations", 
                "General Affairs", "Production", "Quality Control", "Purchasing"
            ]
            divisi = st.selectbox("Divisi/Departemen*", divisi_options)
        
        st.markdown("### 📦 Detail Permintaan")
        
        # Pilih barang
        barang_options = []
        for _, row in available_barang.iterrows():
            barang_options.append(f"{row['nama_barang']} (Stok: {row['stok']} {row['satuan']})")
        
        selected_barang = st.selectbox("Pilih Barang*", ["-- Pilih Barang --"] + barang_options)
        
        jumlah = 1
        keperluan = "Kebutuhan harian"
        catatan = ""
        
        if selected_barang and selected_barang != "-- Pilih Barang --":
            # Get selected item details
            barang_nama = selected_barang.split(" (Stok:")[0]
            selected_item = available_barang[available_barang['nama_barang'] == barang_nama].iloc[0]
            
            # Display stock info
            st.info(f"📦 **{barang_nama}** - Stok tersedia: **{selected_item['stok']} {selected_item['satuan']}**")
            
            col1, col2 = st.columns(2)
            with col1:
                jumlah = st.number_input(
                    f"Jumlah yang diminta ({selected_item['satuan']})*", 
                    min_value=1, 
                    max_value=int(selected_item['stok']),
                    value=1
                )
            with col2:
                keperluan = st.selectbox("Keperluan*", [
                    "Kebutuhan harian",
                    "Project khusus", 
                    "Meeting/Presentasi",
                    "Training",
                    "Event perusahaan",
                    "Lainnya"
                ])
            
            catatan = st.text_area(
                "Catatan tambahan (opsional)", 
                placeholder="Jelaskan lebih detail keperluan atau catatan khusus..."
            )
        else:
            st.info("👆 Pilih barang yang ingin diminta terlebih dahulu")
        
        submit = st.form_submit_button("📤 Kirim Permintaan", type="primary")
        
        if submit:
            st.write("🔄 Memproses permintaan...")
            
            if not nama_karyawan:
                st.error("❌ Nama lengkap harus diisi!")
                return
            if not divisi:
                st.error("❌ Divisi harus dipilih!")
                return
            if selected_barang == "-- Pilih Barang --":
                st.error("❌ Barang harus dipilih!")
                return
                
            try:
                # Get selected item details again for submission
                barang_nama = selected_barang.split(" (Stok:")[0]
                selected_item = available_barang[available_barang['nama_barang'] == barang_nama].iloc[0]
                
                st.write(f"Debug: Inserting data - Nama: {nama_karyawan}, Divisi: {divisi}, Barang ID: {selected_item['id']}, Jumlah: {jumlah}")
                
                conn = get_connection()
                cursor = conn.cursor()
                
                # Gabungkan keperluan dengan catatan
                full_catatan = f"Keperluan: {keperluan}"
                if catatan:
                    full_catatan += f"\nCatatan: {catatan}"
                
                cursor.execute('''
                    INSERT INTO permintaan (nama_karyawan, divisi, barang_id, jumlah, catatan)
                    VALUES (?, ?, ?, ?, ?)
                ''', (nama_karyawan, divisi, selected_item['id'], jumlah, full_catatan))
                
                conn.commit()
                
                cursor.execute("SELECT last_insert_rowid()")
                new_id = cursor.fetchone()[0]
                st.write(f"Debug: Data berhasil disimpan dengan ID: {new_id}")
                
                cursor.execute("SELECT COUNT(*) FROM permintaan WHERE id = ?", (new_id,))
                count = cursor.fetchone()[0]
                st.write(f"Debug: Verifikasi data di database: {count} record ditemukan")
                
                conn.close()
                
                st.success(f"""
                ✅ **Permintaan berhasil dikirim!**
                
                **Detail Permintaan:**
                - **ID Permintaan:** {new_id}
                - **Nama:** {nama_karyawan}
                - **Divisi:** {divisi}
                - **Barang:** {barang_nama}
                - **Jumlah:** {jumlah} {selected_item['satuan']}
                - **Keperluan:** {keperluan}
                
                Permintaan Anda akan diproses oleh admin. Silakan hubungi admin untuk informasi lebih lanjut.
                """)
                st.balloons()
                
            except Exception as e:
                st.error(f"❌ Terjadi kesalahan saat menyimpan data: {str(e)}")
                st.write(f"Debug: Error details - {type(e).__name__}: {str(e)}")

# Login Admin
def show_admin_login():
    st.subheader("👨‍💼 Login Admin")
    st.write("Khusus untuk administrator sistem")
    
    with st.form("admin_login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("🔑 Login Admin")
        
        if submit:
            if username and password:
                admin = authenticate_admin(username, password)
                if admin:
                    st.session_state.logged_in = True
                    st.session_state.admin_id = admin[0]
                    st.session_state.admin_username = admin[1]
                    st.session_state.admin_nama = admin[2]
                    st.success(f"Selamat datang, {admin[2]}!")
                    st.rerun()
                else:
                    st.error("❌ Username atau password salah!")
            else:
                st.error("❌ Silakan isi username dan password!")
    
    st.info("**Login Default Admin:**\n- Username: admin\n- Password: admin123")

# Dashboard Admin
def show_admin_dashboard():
    st.title("👨‍💼 Dashboard Admin")
    st.write(f"Selamat datang, **{st.session_state.admin_nama}**")
    
    st.write("🔄 Memuat data dashboard...")
    
    # Statistik
    total_barang, stok_menipis, pending_requests, monthly_requests = get_dashboard_stats()
    
    st.write(f"Debug: Total barang: {total_barang}, Stok menipis: {stok_menipis}, Pending: {pending_requests}, Monthly: {monthly_requests}")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-container success-metric">
            <h3>{total_barang}</h3>
            <p>Total Barang</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-container warning-metric">
            <h3>{stok_menipis}</h3>
            <p>Stok Menipis</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-container danger-metric">
            <h3>{pending_requests}</h3>
            <p>Permintaan Pending</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-container">
            <h3>{monthly_requests}</h3>
            <p>Permintaan Bulan Ini</p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("⏳ Permintaan Pending")
        pending_df = get_all_requests()
        
        st.write(f"Debug: Total semua permintaan: {len(pending_df)}")
        
        pending_df = pending_df[pending_df['status'] == 'pending']
        st.write(f"Debug: Permintaan pending: {len(pending_df)}")
        
        if not pending_df.empty:
            st.write("Debug: Data permintaan pending:")
            st.dataframe(pending_df[['nama_karyawan', 'divisi', 'nama_barang', 'jumlah', 'tanggal_permintaan']])
            
            for _, row in pending_df.head(5).iterrows():
                st.markdown(f"""
                <div class="status-pending" style="padding: 10px; margin: 5px 0; border-radius: 5px;">
                    <strong>{row['nama_karyawan']}</strong> ({row['divisi']})<br>
                    {row['nama_barang']} - {row['jumlah']} unit<br>
                    <small>Tanggal: {row['tanggal_permintaan'][:16]}</small>
                </div>
                """, unsafe_allow_html=True)
            
            if len(pending_df) > 5:
                st.info(f"Dan {len(pending_df) - 5} permintaan lainnya...")
        else:
            st.success("✅ Tidak ada permintaan pending.")
            if st.button("🔄 Refresh Data"):
                st.rerun()
    
    with col2:
        st.subheader("⚠️ Stok Menipis")
        df_barang = get_barang_list()
        stok_menipis_df = df_barang[df_barang['stok'] <= df_barang['minimum_stok']]
        
        if not stok_menipis_df.empty:
            for _, row in stok_menipis_df.head(5).iterrows():
                if row['stok'] == 0:
                    status_class = "stok-kritis"
                else:
                    status_class = "stok-menipis"
                
                st.markdown(f"""
                <div class="{status_class}">
                    <strong>{row['nama_barang']}</strong><br>
                    Stok: {row['stok']} {row['satuan']} (Min: {row['minimum_stok']})
                </div>
                """, unsafe_allow_html=True)
            
            if len(stok_menipis_df) > 5:
                st.warning(f"Dan {len(stok_menipis_df) - 5} barang lainnya!")
        else:
            st.success("✅ Semua stok dalam kondisi aman!")

# Halaman Kelola Permintaan (Admin)
def show_manage_requests():
    st.title("📋 Kelola Permintaan ATK")
    
    df = get_all_requests()
    
    if not df.empty:
        # Filter
        col1, col2, col3 = st.columns(3)
        with col1:
            status_options = ["Semua"] + list(df['status'].unique())
            status_filter = st.selectbox("Filter Status", status_options)
        with col2:
            divisi_options = ["Semua"] + list(df['divisi'].unique())
            divisi_filter = st.selectbox("Filter Divisi", divisi_options)
        with col3:
            search_name = st.text_input("🔍 Cari nama karyawan")
        
        # Apply filters
        filtered_df = df.copy()
        if status_filter != "Semua":
            filtered_df = filtered_df[filtered_df['status'] == status_filter]
        if divisi_filter != "Semua":
            filtered_df = filtered_df[filtered_df['divisi'] == divisi_filter]
        if search_name:
            filtered_df = filtered_df[filtered_df['nama_karyawan'].str.contains(search_name, case=False)]
        
        st.write(f"Menampilkan {len(filtered_df)} dari {len(df)} permintaan")
        
        # Display requests
        for _, row in filtered_df.iterrows():
            status_emoji = {
                'pending': '⏳',
                'approved': '✅',
                'rejected': '❌', 
                'completed': '✔️'
            }
            
            status_color = {
                'pending': 'status-pending',
                'approved': 'status-approved',
                'rejected': 'status-rejected',
                'completed': 'status-completed'
            }
            
            with st.container():
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                
                with col1:
                    st.markdown(f"""
                    <div class="{status_color.get(row['status'], '')}" style="padding: 15px; border-radius: 8px; margin: 5px 0;">
                        <h4>{status_emoji.get(row['status'], '❓')} {row['nama_barang']}</h4>
                        <p><strong>Pemohon:</strong> {row['nama_karyawan']} ({row['divisi']})</p>
                        <p><strong>Jumlah:</strong> {row['jumlah']} unit | <strong>Stok:</strong> {row['stok_tersedia']} unit</p>
                        <p><strong>Tanggal:</strong> {row['tanggal_permintaan'][:16]}</p>
                        {f"<p><strong>Catatan:</strong> {row['catatan']}</p>" if row['catatan'] else ""}
                        {f"<p><strong>Alasan Ditolak:</strong> {row['alasan_tolak']}</p>" if row['alasan_tolak'] else ""}
                    </div>
                    """, unsafe_allow_html=True)
                
                with col2:
                    if row['status'] == 'pending':
                        if st.button(f"✅ Setujui", key=f"approve_{row['id']}"):
                            if row['jumlah'] <= row['stok_tersedia']:
                                conn = get_connection()
                                cursor = conn.cursor()
                                
                                # Update status permintaan
                                cursor.execute('''
                                    UPDATE permintaan 
                                    SET status = 'approved', tanggal_diproses = ?, processed_by = ?
                                    WHERE id = ?
                                ''', (datetime.now(), st.session_state.admin_id, row['id']))
                                
                                # Kurangi stok
                                cursor.execute('''
                                    UPDATE barang 
                                    SET stok = stok - ?, updated_at = ?
                                    WHERE id = ?
                                ''', (row['jumlah'], datetime.now(), row['barang_id']))
                                
                                conn.commit()
                                conn.close()
                                
                                st.success("✅ Permintaan disetujui!")
                                st.rerun()
                            else:
                                st.error("❌ Stok tidak mencukupi!")
                
                with col3:
                    if row['status'] == 'pending':
                        if st.button(f"❌ Tolak", key=f"reject_{row['id']}"):
                            st.session_state[f"reject_reason_{row['id']}"] = True
                            st.rerun()
                
                with col4:
                    if row['status'] == 'approved':
                        if st.button(f"✔️ Selesai", key=f"complete_{row['id']}"):
                            conn = get_connection()
                            cursor = conn.cursor()
                            cursor.execute('''
                                UPDATE permintaan 
                                SET status = 'completed'
                                WHERE id = ?
                            ''', (row['id'],))
                            conn.commit()
                            conn.close()
                            
                            st.success("✔️ Permintaan diselesaikan!")
                            st.rerun()
                
                # Rejection reason input
                if st.session_state.get(f"reject_reason_{row['id']}", False):
                    with st.form(f"reject_form_{row['id']}"):
                        reason = st.text_input("Alasan penolakan:")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            if st.form_submit_button("Tolak dengan alasan"):
                                conn = get_connection()
                                cursor = conn.cursor()
                                cursor.execute('''
                                    UPDATE permintaan 
                                    SET status = 'rejected', tanggal_diproses = ?, 
                                        processed_by = ?, alasan_tolak = ?
                                    WHERE id = ?
                                ''', (datetime.now(), st.session_state.admin_id, reason, row['id']))
                                conn.commit()
                                conn.close()
                                
                                del st.session_state[f"reject_reason_{row['id']}"]
                                st.success("❌ Permintaan ditolak!")
                                st.rerun()
                        
                        with col2:
                            if st.form_submit_button("Batal"):
                                del st.session_state[f"reject_reason_{row['id']}"]
                                st.rerun()
                
                st.divider()
    else:
        st.info("Belum ada permintaan dalam sistem.")

# Halaman Kelola Barang (Admin)
def show_manage_items():
    st.title("📦 Kelola Barang ATK")
    
    tab1, tab2, tab3 = st.tabs(["Daftar Barang", "Tambah Barang", "Stok Masuk"])
    
    with tab1:
        st.subheader("Daftar Barang")
        df = get_barang_list()
        
        if not df.empty:
            # Search dan filter
            col1, col2 = st.columns(2)
            with col1:
                search_barang = st.text_input("🔍 Cari barang", placeholder="Nama barang...")
            with col2:
                kategori_filter = st.selectbox("Filter Kategori", ["Semua"] + list(df['kategori'].unique()))
            
            # Apply filters
            filtered_barang = df.copy()
            if search_barang:
                filtered_barang = filtered_barang[filtered_barang['nama_barang'].str.contains(search_barang, case=False)]
            if kategori_filter != "Semua":
                filtered_barang = filtered_barang[filtered_barang['kategori'] == kategori_filter]
            
            # Display barang
            for _, row in filtered_barang.iterrows():
                # Status stok
                if row['stok'] == 0:
                    status_badge = "🔴 HABIS"
                    status_class = "stok-kritis"
                elif row['stok'] <= row['minimum_stok']:
                    status_badge = "🟡 MENIPIS"
                    status_class = "stok-menipis"
                else:
                    status_badge = "🟢 AMAN"
                    status_class = "stok-aman"
                
                with st.expander(f"📦 {row['nama_barang']} - {status_badge}"):
                    with st.form(f"edit_form_{row['id']}"):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            new_nama = st.text_input("Nama Barang", value=row['nama_barang'])
                            new_kategori = st.selectbox("Kategori", 
                                ["Alat Tulis", "Kertas", "Alat Kantor", "Elektronik", "Lainnya"],
                                index=["Alat Tulis", "Kertas", "Alat Kantor", "Elektronik", "Lainnya"].index(row['kategori']) if row['kategori'] in ["Alat Tulis", "Kertas", "Alat Kantor", "Elektronik", "Lainnya"] else 0)
                        
                        with col2:
                            new_satuan = st.selectbox("Satuan", 
                                ["Pcs", "Box", "Rim", "Pack", "Set", "Roll"],
                                index=["Pcs", "Box", "Rim", "Pack", "Set", "Roll"].index(row['satuan']) if row['satuan'] in ["Pcs", "Box", "Rim", "Pack", "Set", "Roll"] else 0)
                            new_stok = st.number_input("Stok Saat Ini", value=int(row['stok']), min_value=0)
                        
                        with col3:
                            new_min_stok = st.number_input("Minimum Stok", value=int(row['minimum_stok']), min_value=0)
                            new_harga = st.number_input("Harga Satuan (Rp)", value=float(row['harga_satuan']), min_value=0.0, step=100.0)
                        
                        # Info tambahan
                        st.info(f"""
                        **Status Stok:** {status_badge}  
                        **Terakhir Update:** {row.get('updated_at', 'Tidak ada data')[:16] if row.get('updated_at') else 'Tidak ada data'}
                        """)
                        
                        col1, col2, col3 = st.columns([2, 2, 1])
                        with col1:
                            if st.form_submit_button("💾 Update Barang", type="primary"):
                                conn = get_connection()
                                cursor = conn.cursor()
                                cursor.execute('''
                                    UPDATE barang 
                                    SET nama_barang=?, kategori=?, satuan=?, stok=?, 
                                        minimum_stok=?, harga_satuan=?, updated_at=?
                                    WHERE id=?
                                ''', (new_nama, new_kategori, new_satuan, new_stok, 
                                      new_min_stok, new_harga, datetime.now(), row['id']))
                                conn.commit()
                                conn.close()
                                st.success("✅ Barang berhasil diupdate!")
                                st.rerun()
                        
                        with col2:
                            if st.form_submit_button("🗑️ Hapus Barang", type="secondary"):
                                # Check if ada permintaan yang pending untuk barang ini
                                conn = get_connection()
                                cursor = conn.cursor()
                                cursor.execute("SELECT COUNT(*) FROM permintaan WHERE barang_id = ? AND status = 'pending'", (row['id'],))
                                pending_count = cursor.fetchone()[0]
                                
                                if pending_count > 0:
                                    st.error(f"❌ Tidak bisa hapus barang ini karena ada {pending_count} permintaan yang pending!")
                                else:
                                    cursor.execute("DELETE FROM barang WHERE id=?", (row['id'],))
                                    conn.commit()
                                    st.success("🗑️ Barang berhasil dihapus!")
                                    st.rerun()
                                
                                conn.close()
                        
                        with col3:
                            st.write("")  # Spacer
        else:
            st.info("Belum ada barang dalam sistem.")
    
    with tab2:
        st.subheader("➕ Tambah Barang Baru")
        with st.form("add_item_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                nama_barang = st.text_input("Nama Barang*", placeholder="Contoh: Pulpen Hitam")
                kategori = st.selectbox("Kategori*", ["Alat Tulis", "Kertas", "Alat Kantor", "Elektronik", "Lainnya"])
                satuan = st.selectbox("Satuan*", ["Pcs", "Box", "Rim", "Pack", "Set", "Roll"])
            
            with col2:
                stok_awal = st.number_input("Stok Awal", min_value=0, value=0, help="Jumlah barang saat pertama kali ditambahkan")
                min_stok = st.number_input("Minimum Stok", min_value=0, value=10, help="Alert akan muncul jika stok <= nilai ini")
                harga_satuan = st.number_input("Harga Satuan (Rp)", min_value=0.0, value=0.0, step=100.0)
            
            if st.form_submit_button("➕ Tambah Barang", type="primary"):
                if nama_barang and kategori and satuan:
                    conn = get_connection()
                    cursor = conn.cursor()
                    
                    # Check duplicate nama barang
                    cursor.execute("SELECT COUNT(*) FROM barang WHERE LOWER(nama_barang) = LOWER(?)", (nama_barang,))
                    if cursor.fetchone()[0] > 0:
                        st.error("❌ Nama barang sudah ada! Gunakan nama yang berbeda.")
                    else:
                        cursor.execute('''
                            INSERT INTO barang (nama_barang, kategori, satuan, stok, minimum_stok, harga_satuan)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (nama_barang, kategori, satuan, stok_awal, min_stok, harga_satuan))
                        conn.commit()
                        st.success(f"✅ Barang '{nama_barang}' berhasil ditambahkan!")
                        st.rerun()
                    
                    conn.close()
                else:
                    st.error("❌ Silakan lengkapi semua field yang bertanda *")
    
    with tab3:
        st.subheader("📥 Catat Stok Masuk")
        st.write("Gunakan fitur ini ketika ada pembelian/restock barang")
        
        df_barang = get_barang_list()
        
        if not df_barang.empty:
            with st.form("stock_in_form"):
                col1, col2 = st.columns(2)
                
                with col1:
                    barang_options = [f"{row['nama_barang']} (Stok: {row['stok']} {row['satuan']})" for _, row in df_barang.iterrows()]
                    selected_barang = st.selectbox("Pilih Barang*", barang_options)
                    jumlah_masuk = st.number_input("Jumlah Masuk*", min_value=1, value=1)
                    tanggal_masuk = st.date_input("Tanggal Masuk*", value=date.today())
                
                with col2:
                    supplier = st.text_input("Supplier", placeholder="Nama supplier/vendor")
                    harga_satuan = st.number_input("Harga Satuan (Rp)", min_value=0.0, value=0.0, step=100.0)
                    catatan_masuk = st.text_area("Catatan", placeholder="Catatan tambahan tentang pembelian ini...")
                
                # Kalkulasi otomatis
                if harga_satuan > 0 and jumlah_masuk > 0:
                    total_harga = jumlah_masuk * harga_satuan
                    st.info(f"💰 **Total Harga:** Rp {total_harga:,.0f}")
                
                if st.form_submit_button("📥 Catat Stok Masuk", type="primary"):
                    barang_nama = selected_barang.split(" (Stok:")[0]
                    selected_item = df_barang[df_barang['nama_barang'] == barang_nama].iloc[0]
                    total_harga = jumlah_masuk * harga_satuan
                    
                    conn = get_connection()
                    cursor = conn.cursor()
                    
                    # Insert ke tabel stok_masuk
                    cursor.execute('''
                        INSERT INTO stok_masuk 
                        (barang_id, jumlah, harga_satuan, total_harga, supplier, tanggal_masuk, catatan, admin_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (selected_item['id'], jumlah_masuk, harga_satuan, total_harga, 
                          supplier, tanggal_masuk, catatan_masuk, st.session_state.admin_id))
                    
                    # Update stok barang
                    cursor.execute('''
                        UPDATE barang 
                        SET stok = stok + ?, updated_at = ?
                        WHERE id = ?
                    ''', (jumlah_masuk, datetime.now(), selected_item['id']))
                    
                    conn.commit()
                    conn.close()
                    
                    st.success(f"""
                    ✅ **Stok masuk berhasil dicatat!**
                    
                    **Detail:**
                    - **Barang:** {barang_nama}
                    - **Jumlah:** {jumlah_masuk} {selected_item['satuan']}
                    - **Stok Baru:** {selected_item['stok'] + jumlah_masuk} {selected_item['satuan']}
                    - **Total Harga:** Rp {total_harga:,.0f}
                    """)
                    st.balloons()
                    st.rerun()
        else:
            st.info("Tambahkan barang terlebih dahulu sebelum mencatat stok masuk.")
        
        # History stok masuk
        st.subheader("📋 Riwayat Stok Masuk")
        conn = get_connection()
        df_history = pd.read_sql_query('''
            SELECT sm.*, b.nama_barang, b.satuan, a.nama as admin_nama
            FROM stok_masuk sm
            JOIN barang b ON sm.barang_id = b.id
            JOIN admin_users a ON sm.admin_id = a.id
            ORDER BY sm.created_at DESC
            LIMIT 10
        ''', conn)
        conn.close()
        
        if not df_history.empty:
            for _, row in df_history.iterrows():
                st.markdown(f"""
                <div style="border: 1px solid #ddd; padding: 10px; margin: 5px 0; border-radius: 5px; background: #f8f9fa;">
                    <strong>📦 {row['nama_barang']}</strong> - {row['jumlah']} {row['satuan']}<br>
                    <small>Tanggal: {row['tanggal_masuk']} | Supplier: {row['supplier'] or 'Tidak ada'} | 
                    Total: Rp {row['total_harga']:,.0f} | Oleh: {row['admin_nama']}</small>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("Belum ada riwayat stok masuk.")

# Halaman Laporan (Admin)
def show_reports():
    st.title("📊 Laporan & Analisis")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Laporan Penggunaan", "🏢 Laporan Divisi", "⚠️ Stok Menipis", "📊 Grafik Analisis"])
    
    with tab1:
        st.subheader("📈 Laporan Penggunaan Barang")
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Tanggal Mulai", value=date.today().replace(day=1))
        with col2:
            end_date = st.date_input("Tanggal Akhir", value=date.today())
        
        if st.button("📋 Generate Laporan Penggunaan"):
            conn = get_connection()
            df_usage = pd.read_sql_query('''
                SELECT b.nama_barang, b.kategori, b.satuan,
                       SUM(p.jumlah) as total_permintaan,
                       COUNT(p.id) as jumlah_transaksi,
                       ROUND(AVG(p.jumlah), 2) as rata_rata_permintaan,
                       SUM(CASE WHEN p.status IN ('approved', 'completed') THEN p.jumlah ELSE 0 END) as total_disetujui,
                       SUM(CASE WHEN p.status = 'rejected' THEN p.jumlah ELSE 0 END) as total_ditolak
                FROM permintaan p
                JOIN barang b ON p.barang_id = b.id
                WHERE DATE(p.tanggal_permintaan) BETWEEN ? AND ?
                GROUP BY b.id, b.nama_barang, b.kategori, b.satuan
                ORDER BY total_permintaan DESC
            ''', conn, params=(start_date, end_date))
            conn.close()
            
            if not df_usage.empty:
                st.success(f"📊 Ditemukan {len(df_usage)} barang yang diminta dalam periode {start_date} - {end_date}")
                
                # Display summary
                col1, col2, col3 = st.columns(3)
                with col1:
                    total_requests = df_usage['jumlah_transaksi'].sum()
                    st.metric("Total Transaksi", total_requests)
                with col2:
                    total_items = df_usage['total_permintaan'].sum()
                    st.metric("Total Item Diminta", total_items)
                with col3:
                    total_approved = df_usage['total_disetujui'].sum()
                    st.metric("Total Item Disetujui", total_approved)
                
                st.dataframe(df_usage, use_container_width=True, hide_index=True)
                
                # Download CSV
                csv = df_usage.to_csv(index=False)
                st.download_button(
                    label="📥 Download CSV",
                    data=csv,
                    file_name=f"laporan_penggunaan_{start_date}_{end_date}.csv",
                    mime="text/csv"
                )
            else:
                st.info("❌ Tidak ada data penggunaan dalam periode tersebut.")
    
    with tab2:
        st.subheader("🏢 Laporan Per Divisi")
        
        col1, col2 = st.columns(2)
        with col1:
            start_date_div = st.date_input("Tanggal Mulai", value=date.today().replace(day=1), key="div_start")
        with col2:
            end_date_div = st.date_input("Tanggal Akhir", value=date.today(), key="div_end")
        
        if st.button("📋 Generate Laporan Divisi"):
            conn = get_connection()
            df_div = pd.read_sql_query('''
                SELECT divisi, nama_karyawan,
                       COUNT(p.id) as total_permintaan,
                       SUM(CASE WHEN p.status IN ('approved', 'completed') THEN p.jumlah ELSE 0 END) as total_barang_disetujui,
                       SUM(CASE WHEN p.status = 'rejected' THEN 1 ELSE 0 END) as total_ditolak,
                       SUM(CASE WHEN p.status = 'pending' THEN 1 ELSE 0 END) as pending
                FROM permintaan p
                WHERE DATE(p.tanggal_permintaan) BETWEEN ? AND ?
                GROUP BY divisi, nama_karyawan
                ORDER BY divisi, total_permintaan DESC
            ''', conn, params=(start_date_div, end_date_div))
            conn.close()
            
            if not df_div.empty:
                st.success(f"📊 Data dari {len(df_div)} karyawan dalam periode {start_date_div} - {end_date_div}")
                
                # Summary per divisi
                div_summary = df_div.groupby('divisi').agg({
                    'total_permintaan': 'sum',
                    'total_barang_disetujui': 'sum', 
                    'total_ditolak': 'sum',
                    'pending': 'sum',
                    'nama_karyawan': 'count'
                }).reset_index()
                div_summary = div_summary.rename(columns={'nama_karyawan': 'jumlah_karyawan'})
                
                st.subheader("📋 Ringkasan per Divisi")
                st.dataframe(div_summary, use_container_width=True, hide_index=True)
                
                st.subheader("👥 Detail per Karyawan")
                st.dataframe(df_div, use_container_width=True, hide_index=True)
                
                # Charts
                col1, col2 = st.columns(2)
                with col1:
                    fig_div = px.bar(div_summary, x='divisi', y='total_permintaan',
                                    title='Total Permintaan per Divisi')
                    st.plotly_chart(fig_div, use_container_width=True)
                
                with col2:
                    fig_pie = px.pie(div_summary, values='total_barang_disetujui', names='divisi',
                                    title='Distribusi Barang Disetujui per Divisi')
                    st.plotly_chart(fig_pie, use_container_width=True)
            else:
                st.info("❌ Tidak ada data permintaan dalam periode tersebut.")
    
    with tab3:
        st.subheader("⚠️ Laporan Stok Menipis")
        
        df_barang = get_barang_list()
        stok_menipis_df = df_barang[df_barang['stok'] <= df_barang['minimum_stok']].copy()
        
        if not stok_menipis_df.empty:
            # Add status dan prioritas
            def get_status_priority(row):
                if row['stok'] == 0:
                    return "🔴 HABIS", 1
                elif row['stok'] <= row['minimum_stok'] / 2:
                    return "🟠 KRITIS", 2
                else:
                    return "🟡 MENIPIS", 3
            
            stok_menipis_df[['status', 'prioritas']] = stok_menipis_df.apply(
                lambda row: pd.Series(get_status_priority(row)), axis=1)
            stok_menipis_df['persentase_stok'] = (stok_menipis_df['stok'] / stok_menipis_df['minimum_stok'] * 100).round(1)
            
            # Sort by priority and percentage
            stok_menipis_df = stok_menipis_df.sort_values(['prioritas', 'persentase_stok'])
            
            # Alert summary
            habis = len(stok_menipis_df[stok_menipis_df['stok'] == 0])
            kritis = len(stok_menipis_df[(stok_menipis_df['stok'] > 0) & (stok_menipis_df['stok'] <= stok_menipis_df['minimum_stok'] / 2)])
            menipis = len(stok_menipis_df[stok_menipis_df['stok'] > stok_menipis_df['minimum_stok'] / 2])
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.error(f"🔴 **{habis}** barang HABIS")
            with col2:
                st.warning(f"🟠 **{kritis}** barang KRITIS")
            with col3:
                st.info(f"🟡 **{menipis}** barang MENIPIS")
            
            # Display table
            display_columns = ['nama_barang', 'kategori', 'stok', 'minimum_stok', 'status', 'persentase_stok']
            st.dataframe(stok_menipis_df[display_columns], use_container_width=True, hide_index=True)
            
            # Rekomendasi pembelian
            st.subheader("🛒 Rekomendasi Pembelian")
            for _, row in stok_menipis_df.iterrows():
                if row['stok'] == 0:
                    rekomendasi = row['minimum_stok'] * 2  # Beli 2x minimum stok
                    urgensi = "🚨 URGENT"
                else:
                    rekomendasi = row['minimum_stok'] - row['stok'] + 10  # Tambah buffer 10
                    urgensi = "⚠️ Segera"
                
                st.markdown(f"""
                <div style="border-left: 4px solid #ff6b6b; padding: 10px; margin: 5px 0; background: #fff5f5;">
                    <strong>{urgensi} - {row['nama_barang']}</strong><br>
                    Stok sekarang: {row['stok']} {row['satuan']} | Rekomendasi beli: {rekomendasi} {row['satuan']}
                </div>
                """, unsafe_allow_html=True)
        else:
            st.success("🎉 Semua stok dalam kondisi aman!")
            st.balloons()
    
    with tab4:
        st.subheader("📊 Grafik Analisis")
        
        conn = get_connection()
        
        # Grafik trend permintaan bulanan
        st.markdown("#### 📈 Trend Permintaan Bulanan")
        df_monthly = pd.read_sql_query('''
            SELECT strftime('%Y-%m', tanggal_permintaan) as bulan,
                   COUNT(*) as total_permintaan,
                   SUM(CASE WHEN status IN ('approved', 'completed') THEN 1 ELSE 0 END) as disetujui,
                   SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as ditolak,
                   SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending
            FROM permintaan
            WHERE tanggal_permintaan >= date('now', '-12 months')
            GROUP BY strftime('%Y-%m', tanggal_permintaan)
            ORDER BY bulan
        ''', conn)
        
        if not df_monthly.empty:
            fig1 = px.line(df_monthly, x='bulan', y=['total_permintaan', 'disetujui', 'ditolak'],
                          title='Trend Permintaan 12 Bulan Terakhir',
                          labels={'value': 'Jumlah Permintaan', 'bulan': 'Bulan'})
            st.plotly_chart(fig1, use_container_width=True)
        
        # Grafik kategori barang paling sering diminta
        st.markdown("#### 🏷️ Permintaan per Kategori")
        df_category = pd.read_sql_query('''
            SELECT b.kategori, 
                   SUM(p.jumlah) as total_diminta,
                   COUNT(p.id) as jumlah_permintaan
            FROM permintaan p
            JOIN barang b ON p.barang_id = b.id
            WHERE p.status IN ('approved', 'completed')
            GROUP BY b.kategori
            ORDER BY total_diminta DESC
        ''', conn)
        
        if not df_category.empty:
            col1, col2 = st.columns(2)
            with col1:
                fig2 = px.pie(df_category, values='total_diminta', names='kategori',
                             title='Distribusi Item Diminta per Kategori')
                st.plotly_chart(fig2, use_container_width=True)
            with col2:
                fig3 = px.bar(df_category, x='kategori', y='jumlah_permintaan',
                             title='Jumlah Transaksi per Kategori')
                st.plotly_chart(fig3, use_container_width=True)
        
        # Top barang paling sering diminta
        st.markdown("#### 🔥 Top Barang Paling Diminta")
        df_top_items = pd.read_sql_query('''
            SELECT b.nama_barang, b.kategori,
                   SUM(p.jumlah) as total_diminta,
                   COUNT(p.id) as frekuensi_permintaan
            FROM permintaan p
            JOIN barang b ON p.barang_id = b.id
            WHERE p.status IN ('approved', 'completed')
            GROUP BY b.nama_barang, b.kategori
            ORDER BY total_diminta DESC
            LIMIT 15
        ''', conn)
        
        if not df_top_items.empty:
            fig4 = px.bar(df_top_items, x='total_diminta', y='nama_barang',
                         title='Top 15 Barang Paling Sering Diminta',
                         orientation='h', color='kategori')
            fig4.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig4, use_container_width=True)
        
        # Statistik divisi paling aktif
        st.markdown("#### 🏢 Aktivitas per Divisi")
        df_divisi_aktif = pd.read_sql_query('''
            SELECT divisi,
                   COUNT(*) as total_permintaan,
                   COUNT(DISTINCT nama_karyawan) as jumlah_karyawan_aktif,
                   ROUND(AVG(jumlah), 2) as rata_rata_permintaan
            FROM permintaan
            WHERE tanggal_permintaan >= date('now', '-3 months')
            GROUP BY divisi
            ORDER BY total_permintaan DESC
        ''', conn)
        
        if not df_divisi_aktif.empty:
            fig5 = px.bar(df_divisi_aktif, x='divisi', y='total_permintaan',
                         title='Aktivitas Permintaan per Divisi (3 Bulan Terakhir)')
            st.plotly_chart(fig5, use_container_width=True)
        
        conn.close()

def show_stock_adjustment():
    st.subheader("🔄 Penyesuaian Stok")
    
    conn = get_connection()
    df_barang = pd.read_sql_query("SELECT * FROM barang ORDER BY nama_barang", conn)
    conn.close()
    
    if df_barang.empty:
        st.warning("⚠️ Belum ada barang dalam database.")
        return
    
    with st.form("stock_adjustment_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            barang_options = [f"{row['nama_barang']} (Stok: {row['stok']} {row['satuan']})" for _, row in df_barang.iterrows()]
            selected_barang = st.selectbox("Pilih Barang*", barang_options)
            
        with col2:
            adjustment_type = st.selectbox("Jenis Penyesuaian*", ["Penambahan", "Pengurangan"])
            
        jumlah_adjustment = st.number_input("Jumlah Penyesuaian*", min_value=1, value=1)
        alasan = st.text_area("Alasan Penyesuaian*", placeholder="Jelaskan alasan penyesuaian stok...")
        
        if st.form_submit_button("🔄 Lakukan Penyesuaian", type="primary"):
            if selected_barang and alasan:
                barang_nama = selected_barang.split(" (Stok:")[0]
                selected_item = df_barang[df_barang['nama_barang'] == barang_nama].iloc[0]
                
                conn = get_connection()
                cursor = conn.cursor()
                
                # Calculate new stock
                current_stock = selected_item['stok']
                if adjustment_type == "Penambahan":
                    new_stock = current_stock + jumlah_adjustment
                else:
                    new_stock = max(0, current_stock - jumlah_adjustment)
                
                # Update stock
                cursor.execute('''
                    UPDATE barang SET stok = ?, updated_at = ? WHERE id = ?
                ''', (new_stock, datetime.now(), selected_item['id']))
                
                # Log the adjustment
                cursor.execute('''
                    INSERT INTO stok_keluar (barang_id, jumlah, tanggal_keluar, keperluan, processed_by)
                    VALUES (?, ?, ?, ?, ?)
                ''', (selected_item['id'], jumlah_adjustment if adjustment_type == "Pengurangan" else -jumlah_adjustment, 
                      datetime.now(), f"Penyesuaian: {alasan}", st.session_state.admin_id))
                
                conn.commit()
                conn.close()
                
                st.success(f"✅ Stok berhasil disesuaikan! Stok baru: {new_stock} {selected_item['satuan']}")
                st.rerun()
            else:
                st.error("❌ Mohon lengkapi semua field yang wajib diisi!")

def show_user_management():
    st.subheader("👥 Manajemen User")
    
    # Add new admin form
    with st.expander("➕ Tambah Admin Baru"):
        with st.form("add_admin_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                new_username = st.text_input("Username*", placeholder="Username untuk login")
                new_password = st.text_input("Password*", type="password", placeholder="Password minimal 6 karakter")
                
            with col2:
                new_nama = st.text_input("Nama Lengkap*", placeholder="Nama lengkap admin")
                new_email = st.text_input("Email", placeholder="email@perusahaan.com")
            
            if st.form_submit_button("➕ Tambah Admin", type="primary"):
                if new_username and new_password and new_nama:
                    if len(new_password) < 6:
                        st.error("❌ Password minimal 6 karakter!")
                    else:
                        conn = get_connection()
                        cursor = conn.cursor()
                        
                        # Check if username already exists
                        cursor.execute("SELECT id FROM admin WHERE username = ?", (new_username,))
                        if cursor.fetchone():
                            st.error("❌ Username sudah digunakan!")
                        else:
                            # Hash password (simple hash for demo)
                            import hashlib
                            hashed_password = hashlib.md5(new_password.encode()).hexdigest()
                            
                            cursor.execute('''
                                INSERT INTO admin (username, password, nama_lengkap, email, created_at)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (new_username, hashed_password, new_nama, new_email, datetime.now()))
                            
                            conn.commit()
                            conn.close()
                            
                            st.success("✅ Admin baru berhasil ditambahkan!")
                            st.rerun()
                else:
                    st.error("❌ Mohon lengkapi semua field yang wajib diisi!")

def show_settings():
    st.subheader("⚙️ Pengaturan Sistem")
    
    # System settings form
    with st.form("system_settings_form"):
        st.markdown("### 🏢 Informasi Perusahaan")
        col1, col2 = st.columns(2)
        
        with col1:
            company_name = st.text_input("Nama Perusahaan", value="PT. Contoh Perusahaan")
            company_address = st.text_area("Alamat Perusahaan", value="Jl. Contoh No. 123, Jakarta")
            
        with col2:
            company_phone = st.text_input("Telepon", value="021-12345678")
            company_email = st.text_input("Email", value="info@perusahaan.com")
        
        st.markdown("### 📊 Pengaturan Stok")
        col1, col2 = st.columns(2)
        
        with col1:
            default_min_stock = st.number_input("Minimum Stok Default", value=10, min_value=1)
            auto_approve_limit = st.number_input("Batas Auto-Approve (qty)", value=5, min_value=1)
            
        with col2:
            notification_email = st.text_input("Email Notifikasi", value="admin@perusahaan.com")
            backup_frequency = st.selectbox("Frekuensi Backup", ["Harian", "Mingguan", "Bulanan"])
        
        if st.form_submit_button("💾 Simpan Pengaturan", type="primary"):
            st.success("✅ Pengaturan berhasil disimpan!")
            st.info("ℹ️ Pengaturan akan diterapkan pada sesi berikutnya.")

# Main App
def main():
    load_css()
    init_database()
    
    # Initialize session state
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    
    # Check if admin logged in
    if st.session_state.logged_in:
        # Admin interface
        st.sidebar.title(f"👨‍💼 {st.session_state.admin_nama}")
        st.sidebar.write("**Administrator**")
        st.sidebar.divider()
        
        # Admin menu
        admin_menu = [
            "🏠 Dashboard",
            "📋 Kelola Permintaan",
            "📦 Kelola Barang",
            "📊 Laporan",
            "🔄 Penyesuaian Stok",
            "⚙️ Pengaturan Sistem"
        ]
        
        selected_menu = st.sidebar.selectbox("Menu Admin", admin_menu)
        
        # Logout button
        if st.sidebar.button("🚪 Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
        # Route to admin pages
        if selected_menu == "🏠 Dashboard":
            show_admin_dashboard()
        elif selected_menu == "📋 Kelola Permintaan":
            show_manage_requests()
        elif selected_menu == "📦 Kelola Barang":
            show_manage_items()
        elif selected_menu == "📊 Laporan":
            show_reports()
        elif selected_menu == "🔄 Penyesuaian Stok":
            show_stock_adjustment()
        elif selected_menu == "⚙️ Pengaturan Sistem":
            show_settings()
    
    else:
        # Public interface (untuk karyawan dan admin login)
        show_main_page()

# Jalankan aplikasi
if __name__ == "__main__":
    main()
