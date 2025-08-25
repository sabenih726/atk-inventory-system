import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
from datetime import datetime
import requests
import hashlib
import io
import os
import supabase
from supabase import create_client

# ---------------------
# Konfigurasi Supabase
# ---------------------
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://omuihllziolfoqhezxum.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9tdWlobGx6aW9sZm9xaGV6eHVtIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc1NjExMTY4NCwiZXhwIjoyMDcxNjg3Njg0fQ.CdbaCPMBuI7xB5tEYzG1iQbKEMc7xosdhfKhWOt72v0")  # pakai service key untuk insert/update
HEADERS = {
    "apikey": sb_secret_0v3ElBKsarIv41hfSvHa6w_i7XqKojF,
    "Authorization": f"Bearer {sb_secret_0v3ElBKsarIv41hfSvHa6w_i7XqKojF}",
    "Content-Type": "application/json"
}

# ---------------------
# Items
# ---------------------
def get_all_items():
    url = f"{SUPABASE_URL}/rest/v1/items?select=*&order=nama_barang.asc"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return pd.DataFrame(r.json())

def add_new_item(nama_barang, stok, satuan):
    url = f"{SUPABASE_URL}/rest/v1/items"
    payload = {"nama_barang": nama_barang, "stok": stok, "satuan": satuan}
    r = requests.post(url, headers=HEADERS, json=payload)
    return r.status_code == 201

def update_item(item_id, nama_barang, stok, satuan):
    url = f"{SUPABASE_URL}/rest/v1/items?id=eq.{item_id}"
    payload = {"nama_barang": nama_barang, "stok": stok, "satuan": satuan}
    r = requests.patch(url, headers=HEADERS, json=payload)
    return r.status_code == 204

def delete_item(item_id):
    url = f"{SUPABASE_URL}/rest/v1/items?id=eq.{item_id}"
    r = requests.delete(url, headers=HEADERS)
    return r.status_code == 204

# ---------------------
# Requests
# ---------------------
def get_all_requests():
    url = f"{SUPABASE_URL}/rest/v1/requests?select=*&order=tanggal_request.desc"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return pd.DataFrame(r.json())

def submit_request(nama_pemohon, divisi, nama_barang, jumlah, keperluan):
    url = f"{SUPABASE_URL}/rest/v1/requests"
    payload = {
        "nama_pemohon": nama_pemohon,
        "divisi": divisi,
        "nama_barang": nama_barang,
        "jumlah": jumlah,
        "keperluan": keperluan
    }
    r = requests.post(url, headers=HEADERS, json=payload)
    return r.status_code == 201

def update_request_status(request_id, status, catatan_admin=""):
    url = f"{SUPABASE_URL}/rest/v1/requests?id=eq.{request_id}"
    payload = {"status": status, "catatan_admin": catatan_admin}
    if status == "approved":
        payload["tanggal_approve"] = "now()"  # gunakan fungsi Postgres di Supabase
    r = requests.patch(url, headers=HEADERS, json=payload)
    return r.status_code == 204

# ---------------------
# Stock Transactions
# ---------------------
def add_stock_transaction(item_id, nama_barang, transaction_type, quantity, reason, user_name="Admin"):
    # Tambah transaksi
    url = f"{SUPABASE_URL}/rest/v1/stock_transactions"
    payload = {
        "item_id": item_id,
        "nama_barang": nama_barang,
        "transaction_type": transaction_type,
        "quantity": quantity,
        "reason": reason,
        "user_name": user_name
    }
    r = requests.post(url, headers=HEADERS, json=payload)

    # Update stok item
    if transaction_type == "in":
        patch_payload = {"stok": {"increment": quantity}}
    else:
        patch_payload = {"stok": {"decrement": quantity}}
    requests.patch(f"{SUPABASE_URL}/rest/v1/items?id=eq.{item_id}", headers=HEADERS, json=patch_payload)

    return r.status_code == 201

def get_stock_transactions():
    url = f"{SUPABASE_URL}/rest/v1/stock_transactions?select=*&order=created_at.desc"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    return pd.DataFrame(r.json())

# ---------------------
# Admin
# ---------------------
def check_admin_login(username, password):
    hashed_password = hashlib.md5(password.encode()).hexdigest()
    url = f"{SUPABASE_URL}/rest/v1/admin?username=eq.{username}&password=eq.{hashed_password}"
    r = requests.get(url, headers=HEADERS)
    return r.status_code == 200 and len(r.json()) > 0

# ---------------------
# Import / Export
# ---------------------
def export_to_csv(df, filename="export.csv"):
    return df.to_csv(index=False)

def import_items_from_csv(uploaded_file):
    try:
        df = pd.read_csv(uploaded_file)
        required = ["nama_barang", "stok", "satuan"]
        if not all(col in df.columns for col in required):
            return False, f"Kolom wajib: {', '.join(required)}"

        success_count = 0
        for _, row in df.iterrows():
            url = f"{SUPABASE_URL}/rest/v1/items?nama_barang=eq.{row['nama_barang']}"
            r = requests.get(url, headers=HEADERS)
            if r.json():  # jika ada → update
                patch_url = f"{SUPABASE_URL}/rest/v1/items?nama_barang=eq.{row['nama_barang']}"
                payload = {"stok": row["stok"], "satuan": row["satuan"]}
                requests.patch(patch_url, headers=HEADERS, json=payload)
            else:  # kalau tidak ada → insert
                payload = {
                    "nama_barang": row["nama_barang"],
                    "stok": row["stok"],
                    "satuan": row["satuan"]
                }
                requests.post(f"{SUPABASE_URL}/rest/v1/items", headers=HEADERS, json=payload)
            success_count += 1
        return True, f"Berhasil import {success_count} item"
    except Exception as e:
        return False, str(e)

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

    # ---- Daftar Barang ----
    with tab1:
        items_df = get_all_items()
        if not items_df.empty:
            st.dataframe(items_df, use_container_width=True)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Jenis Barang", len(items_df))
            with col2:
                st.metric("Total Stok", items_df['stok'].sum())
            with col3:
                st.metric("Stok Menipis (≤5)", len(items_df[items_df['stok'] <= 5]))
        else:
            st.info("Belum ada data barang")

    # ---- Tambah Barang Baru ----
    with tab2:
        st.subheader("➕ Tambah Barang Baru")
        with st.form("add_item_form"):
            nama_barang = st.text_input("Nama Barang*")
            stok = st.number_input("Stok Awal", min_value=0, value=0)
            satuan = st.selectbox("Satuan", ["pcs", "rim", "box", "pack", "unit", "lembar", "buah"])

            if st.form_submit_button("➕ Tambah Barang"):
                if nama_barang:
                    # Cek apakah barang sudah ada di Supabase
                    url = f"{SUPABASE_URL}/rest/v1/items?nama_barang=eq.{nama_barang}"
                    r = requests.get(url, headers=HEADERS)
                    if r.json():
                        st.error(f"Barang '{nama_barang}' sudah ada!")
                    else:
                        add_new_item(nama_barang, stok, satuan)
                        st.success(f"Barang '{nama_barang}' berhasil ditambahkan!")
                        st.rerun()
                else:
                    st.error("Nama barang harus diisi!")

    # ---- Edit / Hapus Barang ----
    with tab3:
        st.subheader("✏️ Edit/Hapus Barang")
        items_df = get_all_items()

        if not items_df.empty:
            options = [f"{row['nama_barang']} (ID:{row['id']}, Stok:{row['stok']} {row['satuan']})" 
                       for _, row in items_df.iterrows()]
            selected_item = st.selectbox("Pilih Barang", ["-- Pilih Barang --"] + options)

            if selected_item != "-- Pilih Barang --":
                item_id = int(selected_item.split("ID:")[1].split(",")[0])
                item_data = items_df[items_df['id'] == item_id].iloc[0]

                # ---- Edit ----
                st.write("**Data Saat Ini:**", item_data.to_dict())
                with st.form("edit_item_form"):
                    new_nama = st.text_input("Nama Barang", value=item_data['nama_barang'])
                    new_stok = st.number_input("Stok", min_value=0, value=int(item_data['stok']))
                    new_satuan = st.selectbox("Satuan", ["pcs","rim","box","pack","unit","lembar","buah"], 
                                               index=["pcs","rim","box","pack","unit","lembar","buah"].index(item_data['satuan']) 
                                               if item_data['satuan'] in ["pcs","rim","box","pack","unit","lembar","buah"] else 0)
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.form_submit_button("💾 Update Barang"):
                            # Cek duplikat nama
                            url = f"{SUPABASE_URL}/rest/v1/items?nama_barang=eq.{new_nama}&id=neq.{item_id}"
                            r = requests.get(url, headers=HEADERS)
                            if r.json():
                                st.error(f"Nama barang '{new_nama}' sudah dipakai!")
                            else:
                                update_item(item_id, new_nama, new_stok, new_satuan)
                                st.success("Barang berhasil diupdate!")
                                st.rerun()

                    with col2:
                        if st.form_submit_button("🗑️ Hapus Barang"):
                            # Cek apakah barang masih ada transaksi/permintaan
                            r1 = requests.get(f"{SUPABASE_URL}/rest/v1/stock_transactions?item_id=eq.{item_id}", headers=HEADERS)
                            r2 = requests.get(f"{SUPABASE_URL}/rest/v1/requests?nama_barang=eq.{item_data['nama_barang']}", headers=HEADERS)
                            if r1.json() or r2.json():
                                st.error("Barang tidak bisa dihapus karena masih ada transaksi/permintaan.")
                            else:
                                delete_item(item_id)
                                st.success("Barang berhasil dihapus!")
                                st.rerun()

                # ---- Penyesuaian Stok ----
                st.write("---")
                st.subheader("📊 Penyesuaian Stok Cepat")
                with st.form("adjust_stock_form"):
                    st.write(f"Stok saat ini: {item_data['stok']} {item_data['satuan']}")
                    adjustment_type = st.radio("Jenis Penyesuaian", ["Set Nilai", "Tambah", "Kurangi"])
                    reason = st.text_input("Alasan")
                    if adjustment_type == "Set Nilai":
                        new_val = st.number_input("Set stok ke", min_value=0, value=int(item_data['stok']))
                        if st.form_submit_button("🔄 Set Stok"):
                            if reason:
                                update_item(item_id, item_data['nama_barang'], new_val, item_data['satuan'])
                                if new_val != item_data['stok']:
                                    diff = new_val - item_data['stok']
                                    trx_type = "in" if diff > 0 else "out"
                                    add_stock_transaction(item_id, item_data['nama_barang'], trx_type, abs(diff), f"Adjustment: {reason}")
                                st.success("Stok berhasil diubah!")
                                st.rerun()
                            else:
                                st.error("Alasan harus diisi!")

                    elif adjustment_type == "Tambah":
                        qty = st.number_input("Jumlah Tambah", min_value=1, value=1)
                        if st.form_submit_button("➕ Tambah"):
                            if reason:
                                add_stock_transaction(item_id, item_data['nama_barang'], "in", qty, reason)
                                st.success("Stok ditambahkan!")
                                st.rerun()
                            else:
                                st.error("Alasan harus diisi!")

                    elif adjustment_type == "Kurangi":
                        qty = st.number_input("Jumlah Kurangi", min_value=1, max_value=int(item_data['stok']), value=1)
                        if st.form_submit_button("➖ Kurangi"):
                            if reason:
                                add_stock_transaction(item_id, item_data['nama_barang'], "out", qty, reason)
                                st.success("Stok dikurangi!")
                                st.rerun()
                            else:
                                st.error("Alasan harus diisi!")
        else:
            st.info("Belum ada barang")

# Halaman Kelola Stok
elif menu == "Kelola Stok" and st.session_state.logged_in:
    st.title("📦 Kelola Stok")

    tab1, tab2 = st.tabs(["Stok Masuk", "Stok Keluar"])

    # ---- Stok Masuk ----
    with tab1:
        st.subheader("➕ Tambah Stok Masuk")
        with st.form("stock_in_form"):
            items_df = get_all_items()
            options = ["-- Pilih Barang --"] + [f"{row['nama_barang']} (Stok:{row['stok']} {row['satuan']})" for _, row in items_df.iterrows()]
            selected = st.selectbox("Pilih Barang", options)
            qty = st.number_input("Jumlah Masuk", min_value=1, value=1)
            reason = st.text_area("Keterangan")
            submitted = st.form_submit_button("Tambah")
            if submitted and selected != "-- Pilih Barang --":
                item_name = selected.split(" (")[0]
                item = items_df[items_df['nama_barang'] == item_name].iloc[0]
                add_stock_transaction(item['id'], item_name, "in", qty, reason)
                st.success(f"{qty} {item['satuan']} {item_name} ditambahkan!")
                st.rerun()

    # ---- Stok Keluar ----
    with tab2:
        st.subheader("➖ Stok Keluar Manual")
        with st.form("stock_out_form"):
            items_df = get_all_items()
            options = ["-- Pilih Barang --"] + [f"{row['nama_barang']} (Stok:{row['stok']} {row['satuan']})" for _, row in items_df.iterrows()]
            selected = st.selectbox("Pilih Barang", options, key="out")
            qty = st.number_input("Jumlah Keluar", min_value=1, value=1)
            reason = st.text_area("Keterangan")
            submitted = st.form_submit_button("Kurangi")
            if submitted and selected != "-- Pilih Barang --":
                item_name = selected.split(" (")[0]
                item = items_df[items_df['nama_barang'] == item_name].iloc[0]
                if qty > item['stok']:
                    st.error("Jumlah melebihi stok!")
                else:
                    add_stock_transaction(item['id'], item_name, "out", qty, reason)
                    st.success(f"{qty} {item['satuan']} {item_name} dikurangi!")
                    st.rerun()

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
