import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
from datetime import datetime
import hashlib
import io
import os
import supabase
from supabase import create_client

def get_supabase_client():
    """Get Supabase client using REST API"""
    try:
        url = st.secrets.get("SUPABASE_URL")
        key = st.secrets.get("SUPABASE_KEY")

        if not url or not key:
            st.error("❌ Supabase URL atau API Key tidak ditemukan! Pastikan sudah diset di secrets.toml.")
            st.info("""
            **Cara setup Supabase REST API:**
            1. Buka project di https://supabase.com
            2. Masuk ke Settings > API
            3. Salin Project URL dan Anon Key
            4. Tambahkan ke secrets.toml:
            ```
            SUPABASE_URL = "https://xxxxx.supabase.co"
            SUPABASE_KEY = "your-anon-key"
            ```
            """)
            st.stop()

        supabase = create_client(url, key)
        return supabase
    except Exception as e:
        st.error(f"❌ Gagal koneksi ke Supabase REST API: {str(e)}")
        st.stop()

def init_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabel barang (items) - PostgreSQL syntax
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            nama_barang TEXT NOT NULL,
            stok INTEGER DEFAULT 0,
            satuan TEXT DEFAULT 'pcs',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabel permintaan (requests) - struktur sederhana
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # Tabel stock transactions
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stock_transactions (
            id SERIAL PRIMARY KEY,
            item_id INTEGER NOT NULL,
            nama_barang TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            reason TEXT,
            user_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items (id)
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
        cursor.executemany("INSERT INTO items (nama_barang, stok, satuan) VALUES (%s, %s, %s)", sample_items)
    
    # Insert admin default jika belum ada
    cursor.execute("SELECT COUNT(*) FROM admin")
    if cursor.fetchone()[0] == 0:
        admin_password = hashlib.md5("admin123".encode()).hexdigest()
        cursor.execute("INSERT INTO admin (username, password) VALUES (%s, %s)", ("admin", admin_password))
    
    conn.commit()
    cursor.close()
    conn.close()

def get_all_items():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM items ORDER BY nama_barang", conn)
    conn.close()
    return df

def get_all_requests():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM requests ORDER BY tanggal_request DESC", conn)
    conn.close()
    return df

def submit_request(nama_pemohon, divisi, nama_barang, jumlah, keperluan):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO requests (nama_pemohon, divisi, nama_barang, jumlah, keperluan)
        VALUES (%s, %s, %s, %s, %s)
    """, (nama_pemohon, divisi, nama_barang, jumlah, keperluan))
    conn.commit()
    cursor.close()
    conn.close()
    return True

def update_request_status(request_id, status, catatan_admin=""):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get request details
    cursor.execute("SELECT * FROM requests WHERE id = %s", (request_id,))
    request = cursor.fetchone()
    
    if request and status == 'approved':
        # Auto deduct stock
        cursor.execute("SELECT id FROM items WHERE nama_barang = %s", (request['nama_barang'],))
        item = cursor.fetchone()
        
        if item:
            # Update item stock
            cursor.execute("UPDATE items SET stok = stok - %s WHERE id = %s", 
                         (request['jumlah'], item['id']))
            
            # Record transaction
            cursor.execute("""
                INSERT INTO stock_transactions (item_id, nama_barang, transaction_type, quantity, reason, user_name)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (item['id'], request['nama_barang'], 'out', request['jumlah'], 
                  f"Approved request from {request['nama_pemohon']}", "Admin"))
    
    # Update request status
    cursor.execute("""
        UPDATE requests 
        SET status = %s, tanggal_approve = CURRENT_TIMESTAMP, catatan_admin = %s
        WHERE id = %s
    """, (status, catatan_admin, request_id))
    
    conn.commit()
    cursor.close()
    conn.close()

def add_stock_transaction(item_id, nama_barang, transaction_type, quantity, reason, user_name="Admin"):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Record transaction
    cursor.execute("""
        INSERT INTO stock_transactions (item_id, nama_barang, transaction_type, quantity, reason, user_name)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (item_id, nama_barang, transaction_type, quantity, reason, user_name))
    
    # Update item stock
    if transaction_type == 'in':
        cursor.execute("UPDATE items SET stok = stok + %s WHERE id = %s", (quantity, item_id))
    else:  # transaction_type == 'out'
        cursor.execute("UPDATE items SET stok = stok - %s WHERE id = %s", (quantity, item_id))
    
    conn.commit()
    cursor.close()
    conn.close()

def get_stock_transactions():
    conn = get_db_connection()
    df = pd.read_sql_query("""
        SELECT * FROM stock_transactions 
        ORDER BY created_at DESC
    """, conn)
    conn.close()
    return df

def check_admin_login(username, password):
    conn = get_db_connection()
    cursor = conn.cursor()
    hashed_password = hashlib.md5(password.encode()).hexdigest()
    cursor.execute("SELECT * FROM admin WHERE username = %s AND password = %s", (username, hashed_password))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return result is not None

def add_new_item(nama_barang, stok, satuan):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO items (nama_barang, stok, satuan) VALUES (%s, %s, %s)", 
                   (nama_barang, stok, satuan))
    conn.commit()
    cursor.close()
    conn.close()

def update_item(item_id, nama_barang, stok, satuan):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get old item name for updating related records
    cursor.execute("SELECT nama_barang FROM items WHERE id = %s", (item_id,))
    old_item = cursor.fetchone()
    old_nama = old_item['nama_barang'] if old_item else ""
    
    # Update item
    cursor.execute("UPDATE items SET nama_barang = %s, stok = %s, satuan = %s WHERE id = %s", 
                   (nama_barang, stok, satuan, item_id))
    
    # Update related records if name changed
    if old_nama != nama_barang:
        cursor.execute("UPDATE requests SET nama_barang = %s WHERE nama_barang = %s", 
                       (nama_barang, old_nama))
        cursor.execute("UPDATE stock_transactions SET nama_barang = %s WHERE nama_barang = %s", 
                       (nama_barang, old_nama))
    
    conn.commit()
    cursor.close()
    conn.close()

def delete_item(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM items WHERE id = %s", (item_id,))
    conn.commit()
    cursor.close()
    conn.close()

# Export dataframe to CSV
def export_to_csv(df, filename):
    """Export dataframe to CSV"""
    csv = df.to_csv(index=False)
    return csv

# Import items from CSV file
def import_items_from_csv(uploaded_file):
    """Import items from CSV file"""
    try:
        df = pd.read_csv(uploaded_file)
        required_columns = ['nama_barang', 'stok', 'satuan']
        
        if not all(col in df.columns for col in required_columns):
            return False, f"File harus memiliki kolom: {', '.join(required_columns)}"
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        success_count = 0
        for _, row in df.iterrows():
            try:
                # Check if item already exists
                cursor.execute("SELECT id FROM items WHERE nama_barang = %s", (row['nama_barang'],))
                existing = cursor.fetchone()
                
                if existing:
                    # Update existing item
                    cursor.execute("UPDATE items SET stok = %s, satuan = %s WHERE nama_barang = %s", 
                                 (row['stok'], row['satuan'], row['nama_barang']))
                else:
                    # Insert new item
                    cursor.execute("INSERT INTO items (nama_barang, stok, satuan) VALUES (%s, %s, %s)", 
                                 (row['nama_barang'], row['stok'], row['satuan']))
                success_count += 1
            except Exception as e:
                continue
        
        conn.commit()
        cursor.close()
        conn.close()
        return True, f"Berhasil import {success_count} item"
        
    except Exception as e:
        return False, f"Error: {str(e)}"

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
    menu = st.sidebar.selectbox("Menu", ["Dashboard Admin", "Kelola Permintaan", "Kelola Barang", "Kelola Stok", "Riwayat Transaksi", "Import/Export", "Logout"])

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
    
    # Get data for analytics
    requests_df = get_all_requests()
    items_df = get_all_items()
    transactions_df = get_stock_transactions()
    
    # Main metrics
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
    
    # Additional metrics row
    col5, col6, col7, col8 = st.columns(4)
    
    with col5:
        total_stock = items_df['stok'].sum() if not items_df.empty else 0
        st.metric("Total Stok", total_stock)
    
    with col6:
        low_stock_items = len(items_df[items_df['stok'] <= 5]) if not items_df.empty else 0
        st.metric("Stok Menipis", low_stock_items, delta=f"≤5 unit" if low_stock_items > 0 else None)
    
    with col7:
        total_transactions = len(transactions_df) if not transactions_df.empty else 0
        st.metric("Total Transaksi", total_transactions)
    
    with col8:
        rejected_count = len(requests_df[requests_df['status'] == 'rejected'])
        approval_rate = round((approved_count / len(requests_df) * 100), 1) if len(requests_df) > 0 else 0
        st.metric("Tingkat Persetujuan", f"{approval_rate}%")
    
    # Charts and Analytics
    st.subheader("📈 Analisis Data")
    
    tab1, tab2, tab3, tab4 = st.tabs(["Permintaan per Divisi", "Barang Terpopuler", "Trend Stok", "Aktivitas Harian"])
    
    with tab1:
        if not requests_df.empty:
            # Requests by division
            division_stats = requests_df['divisi'].value_counts()
            st.bar_chart(division_stats)
            
            # Status breakdown by division
            st.write("**Status Permintaan per Divisi:**")
            status_by_division = requests_df.groupby(['divisi', 'status']).size().unstack(fill_value=0)
            st.dataframe(status_by_division, use_container_width=True)
        else:
            st.info("Belum ada data permintaan untuk dianalisis")
    
    with tab2:
        if not requests_df.empty:
            # Most requested items
            popular_items = requests_df['nama_barang'].value_counts().head(10)
            st.bar_chart(popular_items)
            
            # Quantity analysis
            st.write("**Total Jumlah Diminta per Barang:**")
            quantity_by_item = requests_df.groupby('nama_barang')['jumlah'].sum().sort_values(ascending=False).head(10)
            st.bar_chart(quantity_by_item)
        else:
            st.info("Belum ada data permintaan untuk dianalisis")
    
    with tab3:
        if not transactions_df.empty:
            # Stock movement over time
            transactions_df['created_at'] = pd.to_datetime(transactions_df['created_at'])
            transactions_df['date'] = transactions_df['created_at'].dt.date
            
            daily_in = transactions_df[transactions_df['transaction_type'] == 'in'].groupby('date')['quantity'].sum()
            daily_out = transactions_df[transactions_df['transaction_type'] == 'out'].groupby('date')['quantity'].sum()
            
            # Create combined chart data
            stock_trend = pd.DataFrame({
                'Stok Masuk': daily_in,
                'Stok Keluar': daily_out
            }).fillna(0)
            
            st.line_chart(stock_trend)
            
            # Stock movement summary
            total_in = transactions_df[transactions_df['transaction_type'] == 'in']['quantity'].sum()
            total_out = transactions_df[transactions_df['transaction_type'] == 'out']['quantity'].sum()
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Stok Masuk", total_in)
            with col2:
                st.metric("Total Stok Keluar", total_out)
            with col3:
                net_movement = total_in - total_out
                st.metric("Net Movement", net_movement, delta=f"{'Surplus' if net_movement > 0 else 'Defisit'}")
        else:
            st.info("Belum ada data transaksi untuk dianalisis")
    
    with tab4:
        if not requests_df.empty:
            # Daily activity
            requests_df['tanggal_request'] = pd.to_datetime(requests_df['tanggal_request'])
            requests_df['date'] = requests_df['tanggal_request'].dt.date
            
            daily_requests = requests_df.groupby('date').size()
            st.line_chart(daily_requests)
            
            # Recent activity summary
            today = datetime.now().date()
            last_7_days = requests_df[requests_df['date'] >= (today - pd.Timedelta(days=7))]
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Permintaan 7 Hari Terakhir", len(last_7_days))
            with col2:
                avg_daily = len(last_7_days) / 7
                st.metric("Rata-rata Harian", f"{avg_daily:.1f}")
        else:
            st.info("Belum ada data aktivitas untuk dianalisis")
    
    # Alerts and Notifications
    st.subheader("🚨 Peringatan & Notifikasi")
    
    alert_col1, alert_col2 = st.columns(2)
    
    with alert_col1:
        # Low stock alerts
        if not items_df.empty:
            low_stock = items_df[items_df['stok'] <= 5]
            if not low_stock.empty:
                st.warning("**⚠️ Stok Menipis:**")
                for _, item in low_stock.iterrows():
                    st.write(f"• {item['nama_barang']}: {item['stok']} {item['satuan']}")
            else:
                st.success("✅ Semua stok dalam kondisi baik")
    
    with alert_col2:
        # Pending requests alert
        if pending_count > 0:
            st.info(f"**📋 {pending_count} Permintaan Menunggu Persetujuan**")
            if pending_count > 5:
                st.warning("Banyak permintaan pending, segera tindak lanjuti!")
        else:
            st.success("✅ Tidak ada permintaan pending")
    
    # Recent activity summary
    st.subheader("📋 Aktivitas Terbaru")
    
    activity_tab1, activity_tab2, activity_tab3 = st.tabs(["Permintaan Terbaru", "Transaksi Terbaru", "Ringkasan Mingguan"])
    
    with activity_tab1:
        if not requests_df.empty:
            recent_requests = requests_df.head(10)
            st.dataframe(
                recent_requests[['nama_pemohon', 'divisi', 'nama_barang', 'jumlah', 'status', 'tanggal_request']], 
                use_container_width=True
            )
        else:
            st.info("Belum ada permintaan")
    
    with activity_tab2:
        if not transactions_df.empty:
            recent_transactions = transactions_df.head(10)
            # Add icons for transaction types
            recent_transactions['type_icon'] = recent_transactions['transaction_type'].map({'in': '➕', 'out': '➖'})
            st.dataframe(
                recent_transactions[['type_icon', 'nama_barang', 'quantity', 'reason', 'user_name', 'created_at']], 
                use_container_width=True
            )
        else:
            st.info("Belum ada transaksi")
    
    with activity_tab3:
        # Weekly summary
        if not requests_df.empty or not transactions_df.empty:
            today = datetime.now().date()
            week_start = today - pd.Timedelta(days=7)
            
            # Weekly requests
            weekly_requests = requests_df[requests_df['date'] >= week_start] if not requests_df.empty else pd.DataFrame()
            weekly_transactions = transactions_df[transactions_df['created_at'].dt.date >= week_start] if not transactions_df.empty else pd.DataFrame()
            
            summary_col1, summary_col2, summary_col3 = st.columns(3)
            
            with summary_col1:
                st.metric("Permintaan Minggu Ini", len(weekly_requests))
                if not weekly_requests.empty:
                    approved_weekly = len(weekly_requests[weekly_requests['status'] == 'approved'])
                    st.write(f"Disetujui: {approved_weekly}")
                    st.write(f"Pending: {len(weekly_requests[weekly_requests['status'] == 'pending'])}")
            
            with summary_col2:
                st.metric("Transaksi Minggu Ini", len(weekly_transactions))
                if not weekly_transactions.empty:
                    weekly_in = len(weekly_transactions[weekly_transactions['transaction_type'] == 'in'])
                    weekly_out = len(weekly_transactions[weekly_transactions['transaction_type'] == 'out'])
                    st.write(f"Stok Masuk: {weekly_in}")
                    st.write(f"Stok Keluar: {weekly_out}")
            
            with summary_col3:
                if not weekly_requests.empty:
                    top_division = weekly_requests['divisi'].value_counts().index[0] if len(weekly_requests) > 0 else "N/A"
                    st.metric("Divisi Teraktif", top_division)
                    
                    if not weekly_requests.empty:
                        top_item = weekly_requests['nama_barang'].value_counts().index[0]
                        st.write(f"Barang Terpopuler: {top_item}")
        else:
            st.info("Belum ada data untuk ringkasan mingguan")

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
    
    tab1, tab2, tab3 = st.tabs(["Daftar Barang", "Tambah Barang Baru", "Edit/Hapus Barang"])
    
    with tab1:
        items_df = get_all_items()
        if not items_df.empty:
            st.dataframe(items_df, use_container_width=True)
            
            # Summary statistics
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Jenis Barang", len(items_df))
            with col2:
                total_stock = items_df['stok'].sum()
                st.metric("Total Stok", total_stock)
            with col3:
                low_stock = len(items_df[items_df['stok'] <= 5])
                st.metric("Stok Menipis (≤5)", low_stock)
        else:
            st.info("Belum ada data barang")
    
    with tab2:
        st.subheader("➕ Tambah Barang Baru")
        with st.form("add_item_form"):
            nama_barang = st.text_input("Nama Barang*")
            stok = st.number_input("Stok Awal", min_value=0, value=0)
            satuan = st.selectbox("Satuan", ["pcs", "rim", "box", "pack", "unit", "lembar", "buah"])
            
            if st.form_submit_button("➕ Tambah Barang"):
                if nama_barang:
                    # Check if item already exists
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM items WHERE nama_barang = %s", (nama_barang,))
                    existing = cursor.fetchone()
                    
                    if existing:
                        st.error(f"Barang '{nama_barang}' sudah ada! Gunakan tab Edit/Hapus untuk mengubah data.")
                        conn.close()
                    else:
                        add_new_item(nama_barang, stok, satuan)
                        st.success(f"Barang '{nama_barang}' berhasil ditambahkan!")
                        st.rerun()
                else:
                    st.error("Nama barang harus diisi!")
    
    with tab3:
        st.subheader("✏️ Edit/Hapus Barang")
        items_df = get_all_items()
        
        if not items_df.empty:
            # Select item to edit/delete
            item_options = [f"{row['nama_barang']} (ID: {row['id']}, Stok: {row['stok']} {row['satuan']})" for _, row in items_df.iterrows()]
            selected_item = st.selectbox("Pilih Barang untuk Edit/Hapus", ["-- Pilih Barang --"] + item_options)
            
            if selected_item != "-- Pilih Barang --":
                # Extract item ID from selection
                item_id = int(selected_item.split("ID: ")[1].split(",")[0])
                item_data = items_df[items_df['id'] == item_id].iloc[0]
                
                # Show current data
                st.write("**Data Saat Ini:**")
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**Nama:** {item_data['nama_barang']}")
                with col2:
                    st.write(f"**Stok:** {item_data['stok']}")
                with col3:
                    st.write(f"**Satuan:** {item_data['satuan']}")
                
                # Edit form
                st.write("---")
                st.subheader("✏️ Edit Barang")
                with st.form("edit_item_form"):
                    new_nama = st.text_input("Nama Barang", value=item_data['nama_barang'])
                    new_stok = st.number_input("Stok", min_value=0, value=int(item_data['stok']))
                    new_satuan = st.selectbox("Satuan", ["pcs", "rim", "box", "pack", "unit", "lembar", "buah"], 
                                            index=["pcs", "rim", "box", "pack", "unit", "lembar", "buah"].index(item_data['satuan']) if item_data['satuan'] in ["pcs", "rim", "box", "pack", "unit", "lembar", "buah"] else 0)
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Update Barang", type="primary"):
                            if new_nama:
                                conn = get_db_connection()
                                cursor = conn.cursor()
                                
                                # Check if new name already exists (except current item)
                                cursor.execute("SELECT id FROM items WHERE nama_barang = %s AND id != %s", (new_nama, item_id))
                                existing = cursor.fetchone()
                                
                                if existing:
                                    st.error(f"Nama barang '{new_nama}' sudah digunakan oleh barang lain!")
                                    cursor.close()
                                    conn.close()
                                else:
                                    # Update item
                                    update_item(item_id, new_nama, new_stok, new_satuan)
                                    st.success(f"Barang berhasil diupdate!")
                                    st.rerun()
                            else:
                                st.error("Nama barang tidak boleh kosong!")
                    
                    with col2:
                        if st.form_submit_button("🗑️ Hapus Barang", type="secondary"):
                            # Check if item has transactions or requests
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            
                            cursor.execute("SELECT COUNT(*) FROM stock_transactions WHERE item_id = %s", (item_id,))
                            transaction_count = cursor.fetchone()[0] if cursor.fetchone() else 0
                            
                            cursor.execute("SELECT COUNT(*) FROM requests WHERE nama_barang = %s", (item_data['nama_barang'],))
                            request_count = cursor.fetchone()[0] if cursor.fetchone() else 0
                            
                            if transaction_count > 0 or request_count > 0:
                                st.error(f"Tidak dapat menghapus barang ini karena memiliki {transaction_count} transaksi dan {request_count} permintaan. Hapus data terkait terlebih dahulu atau ubah stok menjadi 0.")
                                cursor.close()
                                conn.close()
                            else:
                                delete_item(item_id)
                                st.success(f"Barang '{item_data['nama_barang']}' berhasil dihapus!")
                                st.rerun()
                
                # Bulk stock adjustment
                st.write("---")
                st.subheader("📊 Penyesuaian Stok Cepat")
                with st.form("adjust_stock_form"):
                    st.write(f"Stok saat ini: **{item_data['stok']} {item_data['satuan']}**")
                    adjustment_type = st.radio("Jenis Penyesuaian", ["Set ke nilai tertentu", "Tambah stok", "Kurangi stok"])
                    
                    if adjustment_type == "Set ke nilai tertentu":
                        new_stock_value = st.number_input("Set stok ke", min_value=0, value=int(item_data['stok']))
                        reason = st.text_input("Alasan penyesuaian", placeholder="Contoh: Penyesuaian stok fisik")
                        
                        if st.form_submit_button("🔄 Set Stok"):
                            if reason:
                                conn = get_db_connection()
                                cursor = conn.cursor()
                                
                                # Calculate difference for transaction record
                                difference = new_stock_value - int(item_data['stok'])
                                
                                # Update stock
                                cursor.execute("UPDATE items SET stok = %s WHERE id = %s", (new_stock_value, item_id))
                                
                                # Record transaction
                                if difference != 0:
                                    transaction_type = 'in' if difference > 0 else 'out'
                                    cursor.execute("""
                                        INSERT INTO stock_transactions (item_id, nama_barang, transaction_type, quantity, reason, user_name)
                                        VALUES (%s, %s, %s, %s, %s, %s)
                                    """, (item_id, item_data['nama_barang'], transaction_type, abs(difference), f"Stock adjustment: {reason}", "Admin"))
                                
                                conn.commit()
                                cursor.close()
                                conn.close()
                                st.success(f"Stok berhasil diset ke {new_stock_value} {item_data['satuan']}")
                                st.rerun()
                            else:
                                st.error("Alasan penyesuaian harus diisi!")
                    
                    elif adjustment_type == "Tambah stok":
                        add_amount = st.number_input("Jumlah yang ditambahkan", min_value=1, value=1)
                        reason = st.text_input("Alasan penambahan", placeholder="Contoh: Pembelian baru")
                        
                        if st.form_submit_button("➕ Tambah Stok"):
                            if reason:
                                add_stock_transaction(item_id, item_data['nama_barang'], 'in', add_amount, reason)
                                st.success(f"Berhasil menambah {add_amount} {item_data['satuan']} ke stok")
                                st.rerun()
                            else:
                                st.error("Alasan penambahan harus diisi!")
                    
                    else:  # Kurangi stok
                        max_reduce = int(item_data['stok'])
                        if max_reduce > 0:
                            reduce_amount = st.number_input("Jumlah yang dikurangi", min_value=1, max_value=max_reduce, value=1)
                            reason = st.text_input("Alasan pengurangan", placeholder="Contoh: Barang rusak")
                            
                            if st.form_submit_button("➖ Kurangi Stok"):
                                if reason:
                                    add_stock_transaction(item_id, item_data['nama_barang'], 'out', reduce_amount, reason)
                                    st.success(f"Berhasil mengurangi {reduce_amount} {item_data['satuan']} dari stok")
                                    st.rerun()
                                else:
                                    st.error("Alasan pengurangan harus diisi!")
                        else:
                            st.warning("Stok sudah habis, tidak bisa dikurangi lagi")
                            st.form_submit_button("➖ Kurangi Stok", disabled=True)
        else:
            st.info("Belum ada barang untuk diedit/dihapus")

# Halaman Kelola Stok
elif menu == "Kelola Stok" and st.session_state.logged_in:
    st.title("📦 Kelola Stok")
    
    tab1, tab2 = st.tabs(["Stok Masuk", "Stok Keluar"])
    
    with tab1:
        st.subheader("➕ Tambah Stok Masuk")
        with st.form("stock_in_form"):
            items_df = get_all_items()
            item_options = ["-- Pilih Barang --"] + [f"{row['nama_barang']} (Stok: {row['stok']} {row['satuan']})" for _, row in items_df.iterrows()]
            selected_item = st.selectbox("Pilih Barang", item_options)
            
            quantity = 1
            reason = ""
            item_info = None
            item_name = ""
            
            if selected_item != "-- Pilih Barang --":
                item_name = selected_item.split(" (Stok:")[0]
                item_info = items_df[items_df['nama_barang'] == item_name].iloc[0]
                
                quantity = st.number_input("Jumlah Masuk", min_value=1, value=1)
                reason = st.text_area("Keterangan", placeholder="Alasan penambahan stok (pembelian, donasi, dll)")
            else:
                st.number_input("Jumlah Masuk", min_value=1, value=1, disabled=True, help="Pilih barang terlebih dahulu")
                st.text_area("Keterangan", placeholder="Pilih barang terlebih dahulu", disabled=True)
            
            submitted = st.form_submit_button("Tambah Stok")
            
            if submitted:
                if selected_item == "-- Pilih Barang --":
                    st.error("Silakan pilih barang terlebih dahulu!")
                elif not reason:
                    st.error("Keterangan harus diisi!")
                else:
                    add_stock_transaction(item_info['id'], item_name, 'in', quantity, reason)
                    st.success(f"Berhasil menambah {quantity} {item_info['satuan']} {item_name}")
                    st.rerun()
    
    with tab2:
        st.subheader("➖ Stok Keluar Manual")
        with st.form("stock_out_form"):
            items_df = get_all_items()
            item_options = ["-- Pilih Barang --"] + [f"{row['nama_barang']} (Stok: {row['stok']} {row['satuan']})" for _, row in items_df.iterrows()]
            selected_item = st.selectbox("Pilih Barang", item_options, key="stock_out_item")
            
            quantity = 1
            reason = ""
            item_info = None
            item_name = ""
            
            if selected_item != "-- Pilih Barang --":
                item_name = selected_item.split(" (Stok:")[0]
                item_info = items_df[items_df['nama_barang'] == item_name].iloc[0]
                
                current_stock = item_info['stok'] if item_info['stok'] is not None else 0
                max_quantity = int(current_stock) if current_stock > 0 else 0
                
                if max_quantity > 0:
                    quantity = st.number_input("Jumlah Keluar", min_value=1, max_value=max_quantity, value=1)
                    reason = st.text_area("Keterangan", placeholder="Alasan pengurangan stok (rusak, hilang, dll)", key="stock_out_reason")
                else:
                    st.warning("Stok barang ini sudah habis!")
                    st.number_input("Jumlah Keluar", min_value=1, value=1, disabled=True)
                    st.text_area("Keterangan", placeholder="Stok habis", disabled=True, key="stock_out_reason_disabled")
            else:
                st.number_input("Jumlah Keluar", min_value=1, value=1, disabled=True, help="Pilih barang terlebih dahulu")
                st.text_area("Keterangan", placeholder="Pilih barang terlebih dahulu", disabled=True, key="stock_out_reason_placeholder")
            
            submitted = st.form_submit_button("Kurangi Stok")
            
            if submitted:
                if selected_item == "-- Pilih Barang --":
                    st.error("Silakan pilih barang terlebih dahulu!")
                elif item_info is not None:
                    current_stock = item_info['stok'] if item_info['stok'] is not None else 0
                    if current_stock <= 0:
                        st.error("Stok barang ini sudah habis!")
                    elif not reason:
                        st.error("Keterangan harus diisi!")
                    elif quantity > current_stock:
                        st.error(f"Jumlah keluar ({quantity}) tidak boleh lebih dari stok tersedia ({current_stock})")
                    else:
                        add_stock_transaction(item_info['id'], item_name, 'out', quantity, reason)
                        st.success(f"Berhasil mengurangi {quantity} {item_info['satuan']} {item_name}")
                        st.rerun()
                else:
                    st.error("Terjadi kesalahan dalam memproses data barang!")

# Halaman Riwayat Transaksi
elif menu == "Riwayat Transaksi" and st.session_state.logged_in:
    st.title("📊 Riwayat Transaksi Stok")
    
    transactions_df = get_stock_transactions()
    
    if not transactions_df.empty:
        # Filter options
        col1, col2 = st.columns(2)
        with col1:
            transaction_filter = st.selectbox("Filter Jenis", ["Semua", "in", "out"])
        with col2:
            items_df = get_all_items()
            item_filter = st.selectbox("Filter Barang", ["Semua"] + items_df['nama_barang'].tolist())
        
        # Apply filters
        filtered_df = transactions_df.copy()
        if transaction_filter != "Semua":
            filtered_df = filtered_df[filtered_df['transaction_type'] == transaction_filter]
        if item_filter != "Semua":
            filtered_df = filtered_df[filtered_df['nama_barang'] == item_filter]
        
        # Display transactions
        for _, row in filtered_df.iterrows():
            transaction_type_icon = "➕" if row['transaction_type'] == 'in' else "➖"
            transaction_type_text = "Masuk" if row['transaction_type'] == 'in' else "Keluar"
            
            with st.expander(f"{transaction_type_icon} {row['nama_barang']} - {row['quantity']} ({row['created_at']})"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Barang:** {row['nama_barang']}")
                    st.write(f"**Jenis:** {transaction_type_text}")
                    st.write(f"**Jumlah:** {row['quantity']}")
                with col2:
                    st.write(f"**User:** {row['user_name']}")
                    st.write(f"**Tanggal:** {row['created_at']}")
                    st.write(f"**Keterangan:** {row['reason']}")
    else:
        st.info("Belum ada transaksi stok")

# Halaman Import/Export
elif menu == "Import/Export" and st.session_state.logged_in:
    st.title("📁 Import/Export Data")
    
    tab1, tab2 = st.tabs(["Export Data", "Import Data"])
    
    with tab1:
        st.subheader("📤 Export Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Export Inventori**")
            items_df = get_all_items()
            if not items_df.empty:
                csv_items = export_to_csv(items_df, "inventori_atk.csv")
                st.download_button(
                    label="📥 Download Inventori (CSV)",
                    data=csv_items,
                    file_name=f"inventori_atk_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
                st.info(f"Total: {len(items_df)} item")
            else:
                st.warning("Tidak ada data inventori")
            
            st.write("**Export Permintaan**")
            requests_df = get_all_requests()
            if not requests_df.empty:
                csv_requests = export_to_csv(requests_df, "permintaan_atk.csv")
                st.download_button(
                    label="📥 Download Permintaan (CSV)",
                    data=csv_requests,
                    file_name=f"permintaan_atk_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
                st.info(f"Total: {len(requests_df)} permintaan")
            else:
                st.warning("Tidak ada data permintaan")
        
        with col2:
            st.write("**Export Transaksi Stok**")
            transactions_df = get_stock_transactions()
            if not transactions_df.empty:
                csv_transactions = export_to_csv(transactions_df, "transaksi_stok.csv")
                st.download_button(
                    label="📥 Download Transaksi (CSV)",
                    data=csv_transactions,
                    file_name=f"transaksi_stok_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
                st.info(f"Total: {len(transactions_df)} transaksi")
            else:
                st.warning("Tidak ada data transaksi")
            
            st.write("**Export Laporan Lengkap**")
            if not items_df.empty:
                # Create comprehensive report
                report_data = []
                for _, item in items_df.iterrows():
                    # Get transactions for this item
                    item_transactions = transactions_df[transactions_df['nama_barang'] == item['nama_barang']] if not transactions_df.empty else pd.DataFrame()
                    
                    total_in = item_transactions[item_transactions['transaction_type'] == 'in']['quantity'].sum() if not item_transactions.empty else 0
                    total_out = item_transactions[item_transactions['transaction_type'] == 'out']['quantity'].sum() if not item_transactions.empty else 0
                    
                    report_data.append({
                        'nama_barang': item['nama_barang'],
                        'stok_saat_ini': item['stok'],
                        'satuan': item['satuan'],
                        'total_masuk': total_in,
                        'total_keluar': total_out,
                        'created_at': item['created_at']
                    })
                
                report_df = pd.DataFrame(report_data)
                csv_report = export_to_csv(report_df, "laporan_lengkap.csv")
                st.download_button(
                    label="📥 Download Laporan Lengkap (CSV)",
                    data=csv_report,
                    file_name=f"laporan_lengkap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
    
    with tab2:
        st.subheader("📤 Import Data")
        
        st.write("**Import Inventori dari CSV**")
        st.info("Format CSV harus memiliki kolom: nama_barang, stok, satuan")
        
        # Template download
        template_data = {
            'nama_barang': ['Contoh Pulpen', 'Contoh Kertas'],
            'stok': [10, 5],
            'satuan': ['pcs', 'rim']
        }
        template_df = pd.DataFrame(template_data)
        template_csv = export_to_csv(template_df, "template_import.csv")
        
        st.download_button(
            label="📥 Download Template CSV",
            data=template_csv,
            file_name="template_import_inventori.csv",
            mime="text/csv"
        )
        
        uploaded_file = st.file_uploader("Pilih file CSV", type=['csv'])
        
        if uploaded_file is not None:
            # Preview data
            try:
                preview_df = pd.read_csv(uploaded_file)
                st.write("**Preview Data:**")
                st.dataframe(preview_df.head())
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🚀 Import Data", type="primary"):
                        success, message = import_items_from_csv(uploaded_file)
                        if success:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
                
                with col2:
                    if st.button("❌ Batal"):
                        st.rerun()
                        
            except Exception as e:
                st.error(f"Error membaca file: {str(e)}")
        
        st.write("---")
        st.write("**Petunjuk Import:**")
        st.write("1. Download template CSV terlebih dahulu")
        st.write("2. Isi data sesuai format template")
        st.write("3. Upload file CSV yang sudah diisi")
        st.write("4. Jika nama barang sudah ada, stok akan diupdate")
        st.write("5. Jika nama barang belum ada, akan ditambahkan sebagai item baru")

# Logout
elif menu == "Logout":
    st.session_state.logged_in = False
    st.success("Logout berhasil!")
    st.rerun()
