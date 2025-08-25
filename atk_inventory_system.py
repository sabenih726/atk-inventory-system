import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import hashlib

# Konfigurasi halaman
st.set_page_config(
    page_title="Sistem Inventori ATK",
    page_icon="📋",
    layout="wide"
)

# Inisialisasi database
def init_database():
    conn = sqlite3.connect('atk_inventory.db')
    cursor = conn.cursor()
    
    # Tabel barang (items)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_barang TEXT NOT NULL,
            stok INTEGER DEFAULT 0,
            satuan TEXT DEFAULT 'pcs',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabel permintaan (requests) - struktur sederhana
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama_pemohon TEXT NOT NULL,
            divisi TEXT NOT NULL,
            nama_barang TEXT NOT NULL,
            jumlah INTEGER NOT NULL,
            keperluan TEXT,
            status TEXT DEFAULT 'pending',
            tanggal_request TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            tanggal_approve TIMESTAMP,
            catatan_admin TEXT
        )
    ''')
    
    # Tabel admin
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # Insert data barang contoh jika belum ada
    cursor.execute("SELECT COUNT(*) FROM items")
    if cursor.fetchone()[0] == 0:
        sample_items = [
            ('Pulpen Biru', 50, 'pcs'),
            ('Pulpen Hitam', 30, 'pcs'),
            ('Pensil 2B', 25, 'pcs'),
            ('Kertas A4', 100, 'rim'),
            ('Stapler', 5, 'pcs'),
            ('Penghapus', 20, 'pcs'),
            ('Penggaris', 15, 'pcs'),
            ('Spidol Whiteboard', 10, 'pcs')
        ]
        cursor.executemany("INSERT INTO items (nama_barang, stok, satuan) VALUES (?, ?, ?)", sample_items)
    
    # Insert admin default jika belum ada
    cursor.execute("SELECT COUNT(*) FROM admin")
    if cursor.fetchone()[0] == 0:
        admin_password = hashlib.md5("admin123".encode()).hexdigest()
        cursor.execute("INSERT INTO admin (username, password) VALUES (?, ?)", ("admin", admin_password))
    
    conn.commit()
    conn.close()

# Fungsi untuk mendapatkan semua barang
def get_all_items():
    conn = sqlite3.connect('atk_inventory.db')
    df = pd.read_sql_query("SELECT * FROM items ORDER BY nama_barang", conn)
    conn.close()
    return df

# Fungsi untuk mendapatkan semua permintaan
def get_all_requests():
    conn = sqlite3.connect('atk_inventory.db')
    df = pd.read_sql_query("SELECT * FROM requests ORDER BY tanggal_request DESC", conn)
    conn.close()
    return df

# Fungsi untuk submit permintaan
def submit_request(nama_pemohon, divisi, nama_barang, jumlah, keperluan):
    conn = sqlite3.connect('atk_inventory.db')
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO requests (nama_pemohon, divisi, nama_barang, jumlah, keperluan)
        VALUES (?, ?, ?, ?, ?)
    """, (nama_pemohon, divisi, nama_barang, jumlah, keperluan))
    conn.commit()
    conn.close()
    return True

# Fungsi untuk update status permintaan
def update_request_status(request_id, status, catatan_admin=""):
    conn = sqlite3.connect('atk_inventory.db')
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE requests 
        SET status = ?, catatan_admin = ?, tanggal_approve = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (status, catatan_admin, request_id))
    conn.commit()
    conn.close()

# Fungsi login admin
def check_admin_login(username, password):
    conn = sqlite3.connect('atk_inventory.db')
    cursor = conn.cursor()
    hashed_password = hashlib.md5(password.encode()).hexdigest()
    cursor.execute("SELECT * FROM admin WHERE username = ? AND password = ?", (username, hashed_password))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# Inisialisasi database
init_database()

# Session state untuk login
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

# Sidebar untuk navigasi
st.sidebar.title("📋 Sistem Inventori ATK")

if not st.session_state.logged_in:
    menu = st.sidebar.selectbox("Menu", ["Form Permintaan ATK", "Login Admin"])
else:
    menu = st.sidebar.selectbox("Menu", ["Dashboard Admin", "Kelola Permintaan", "Kelola Barang", "Logout"])

# Halaman Form Permintaan ATK
if menu == "Form Permintaan ATK":
    st.title("📝 Form Permintaan ATK")
    st.write("Isi form di bawah ini untuk mengajukan permintaan ATK")
    
    with st.form("request_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("👤 Informasi Pemohon")
            nama_pemohon = st.text_input("Nama Lengkap*", placeholder="Masukkan nama lengkap Anda")
            divisi = st.selectbox("Divisi/Departemen*", [
                "-- Pilih Divisi --", "IT", "Finance", "HR", "Marketing", 
                "Operations", "Sales", "Admin"
            ])
        
        with col2:
            st.subheader("📦 Detail Permintaan")
            items_df = get_all_items()
            item_options = ["-- Pilih Barang --"] + items_df['nama_barang'].tolist()
            nama_barang = st.selectbox("Pilih Barang*", item_options)
            
            if nama_barang != "-- Pilih Barang --":
                # Tampilkan stok tersedia
                item_info = items_df[items_df['nama_barang'] == nama_barang].iloc[0]
                st.info(f"Stok tersedia: {item_info['stok']} {item_info['satuan']}")
                
                jumlah = st.number_input("Jumlah*", min_value=1, max_value=int(item_info['stok']), value=1)
            else:
                jumlah = 1
        
        keperluan = st.text_area("Keperluan/Keterangan", placeholder="Jelaskan untuk keperluan apa barang ini dibutuhkan")
        
        submitted = st.form_submit_button("🚀 Kirim Permintaan", use_container_width=True)
        
        if submitted:
            if not nama_pemohon or divisi == "-- Pilih Divisi --" or nama_barang == "-- Pilih Barang --":
                st.error("❌ Mohon lengkapi semua field yang wajib diisi!")
            else:
                try:
                    submit_request(nama_pemohon, divisi, nama_barang, jumlah, keperluan)
                    st.success("✅ Permintaan berhasil dikirim! Admin akan segera memproses permintaan Anda.")
                    st.balloons()
                except Exception as e:
                    st.error(f"❌ Terjadi kesalahan: {str(e)}")

# Halaman Login Admin
elif menu == "Login Admin":
    st.title("🔐 Login Admin")
    
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        login_button = st.form_submit_button("Login")
        
        if login_button:
            if check_admin_login(username, password):
                st.session_state.logged_in = True
                st.success("✅ Login berhasil!")
                st.rerun()
            else:
                st.error("❌ Username atau password salah!")

# Halaman Dashboard Admin
elif menu == "Dashboard Admin" and st.session_state.logged_in:
    st.title("📊 Dashboard Admin")
    
    # Statistik
    requests_df = get_all_requests()
    items_df = get_all_items()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Permintaan", len(requests_df))
    
    with col2:
        pending_count = len(requests_df[requests_df['status'] == 'pending'])
        st.metric("Permintaan Pending", pending_count)
    
    with col3:
        approved_count = len(requests_df[requests_df['status'] == 'approved'])
        st.metric("Permintaan Disetujui", approved_count)
    
    with col4:
        total_items = len(items_df)
        st.metric("Total Jenis Barang", total_items)
    
    # Permintaan terbaru
    st.subheader("📋 Permintaan Terbaru")
    if not requests_df.empty:
        recent_requests = requests_df.head(5)
        st.dataframe(recent_requests[['nama_pemohon', 'divisi', 'nama_barang', 'jumlah', 'status', 'tanggal_request']], use_container_width=True)
    else:
        st.info("Belum ada permintaan")

# Halaman Kelola Permintaan
elif menu == "Kelola Permintaan" and st.session_state.logged_in:
    st.title("📋 Kelola Permintaan ATK")
    
    requests_df = get_all_requests()
    
    if not requests_df.empty:
        # Filter berdasarkan status
        status_filter = st.selectbox("Filter Status", ["Semua", "pending", "approved", "rejected"])
        
        if status_filter != "Semua":
            filtered_df = requests_df[requests_df['status'] == status_filter]
        else:
            filtered_df = requests_df
        
        # Tampilkan data
        for idx, row in filtered_df.iterrows():
            with st.expander(f"#{row['id']} - {row['nama_pemohon']} ({row['status']})"):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Nama:** {row['nama_pemohon']}")
                    st.write(f"**Divisi:** {row['divisi']}")
                    st.write(f"**Barang:** {row['nama_barang']}")
                    st.write(f"**Jumlah:** {row['jumlah']}")
                    st.write(f"**Keperluan:** {row['keperluan']}")
                
                with col2:
                    st.write(f"**Status:** {row['status']}")
                    st.write(f"**Tanggal Request:** {row['tanggal_request']}")
                    if row['tanggal_approve']:
                        st.write(f"**Tanggal Approve:** {row['tanggal_approve']}")
                    if row['catatan_admin']:
                        st.write(f"**Catatan Admin:** {row['catatan_admin']}")
                
                if row['status'] == 'pending':
                    col3, col4, col5 = st.columns(3)
                    
                    with col3:
                        if st.button(f"✅ Setujui #{row['id']}", key=f"approve_{row['id']}"):
                            update_request_status(row['id'], 'approved', 'Permintaan disetujui')
                            st.success("Permintaan disetujui!")
                            st.rerun()
                    
                    with col4:
                        if st.button(f"❌ Tolak #{row['id']}", key=f"reject_{row['id']}"):
                            update_request_status(row['id'], 'rejected', 'Permintaan ditolak')
                            st.success("Permintaan ditolak!")
                            st.rerun()
    else:
        st.info("Belum ada permintaan")

# Halaman Kelola Barang
elif menu == "Kelola Barang" and st.session_state.logged_in:
    st.title("📦 Kelola Barang")
    
    tab1, tab2 = st.tabs(["Daftar Barang", "Tambah Barang"])
    
    with tab1:
        items_df = get_all_items()
        st.dataframe(items_df, use_container_width=True)
    
    with tab2:
        with st.form("add_item_form"):
            nama_barang = st.text_input("Nama Barang")
            stok = st.number_input("Stok Awal", min_value=0, value=0)
            satuan = st.selectbox("Satuan", ["pcs", "rim", "box", "pack", "unit"])
            
            if st.form_submit_button("Tambah Barang"):
                if nama_barang:
                    conn = sqlite3.connect('atk_inventory.db')
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO items (nama_barang, stok, satuan) VALUES (?, ?, ?)", 
                                 (nama_barang, stok, satuan))
                    conn.commit()
                    conn.close()
                    st.success("Barang berhasil ditambahkan!")
                    st.rerun()
                else:
                    st.error("Nama barang harus diisi!")

# Logout
elif menu == "Logout":
    st.session_state.logged_in = False
    st.success("Logout berhasil!")
    st.rerun()
