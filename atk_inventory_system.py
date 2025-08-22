import streamlit as st
import pandas as pd
import sqlite3
import hashlib
from datetime import datetime, date

# ------------------ Konfigurasi Halaman ------------------
st.set_page_config(
    page_title="Sistem Inventori ATK",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ------------------ Database Setup ------------------
DB_FILE = "atk_inventory.db"

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str):
    return hashlib.sha256(password.encode()).hexdigest()

# ------------------ Init DB ------------------
def init_database():
    conn = get_connection()
    c = conn.cursor()

    # Tabel admin
    c.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            nama TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tabel barang
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

    # Insert default admin jika belum ada
    c.execute("SELECT COUNT(*) FROM admin_users")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO admin_users (username,password,nama) VALUES (?,?,?)",
                  ("admin", hash_password("admin123"), "Administrator"))

    # Sample barang
    c.execute("SELECT COUNT(*) FROM barang")
    if c.fetchone()[0] == 0:
        c.executemany("""
            INSERT INTO barang (nama_barang,kategori,satuan,stok,minimum_stok,harga_satuan)
            VALUES (?,?,?,?,?,?)
        """,[
            ("Pulpen Biru","Alat Tulis","Pcs",50,10,2500),
            ("Kertas A4","Kertas","Rim",20,5,65000),
            ("Stapler","Alat Kantor","Pcs",10,3,45000)
        ])

    conn.commit()
    conn.close()

# ------------------ Fungsi Utility ------------------
def authenticate_admin(username, password):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM admin_users WHERE username=? AND password=?",
              (username, hash_password(password)))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_barang_list():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM barang", conn)
    conn.close()
    return df

def get_requests():
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT p.id, p.nama_karyawan, p.divisi, b.nama_barang, p.jumlah, p.status,
               p.tanggal_permintaan, p.catatan, p.alasan_tolak, b.stok as stok_tersedia
        FROM permintaan p
        JOIN barang b ON p.barang_id=b.id
        ORDER BY p.tanggal_permintaan DESC
    """, conn)
    conn.close()
    return df

# ------------------ Public ------------------
def show_public_inventory():
    st.subheader("📦 Daftar Stok ATK")
    df = get_barang_list()
    if df.empty:
        st.info("Belum ada data barang")
        return
    for _, r in df.iterrows():
        if r['stok'] == 0:
            warna = "🔴 HABIS"
        elif r['stok'] <= r['minimum_stok']:
            warna = "🟡 Menipis"
        else:
            warna = "🟢 Tersedia"
        st.markdown(f"**{r['nama_barang']}** ({r['kategori']}) - Stok: {r['stok']} {r['satuan']} {warna}")

def show_public_request_form():
    st.subheader("📝 Form Permintaan ATK")
    df = get_barang_list()
    df = df[df['stok']>0]
    if df.empty:
        st.warning("Tidak ada barang tersedia")
        return
    with st.form("req_form",clear_on_submit=True):
        nama = st.text_input("Nama")
        divisi = st.text_input("Divisi")
        barang = st.selectbox("Barang", df['nama_barang'].tolist())
        jumlah = st.number_input("Jumlah",min_value=1)
        catatan = st.text_area("Catatan")
        ok = st.form_submit_button("Kirim")
        if ok and nama and divisi:
            row = df[df['nama_barang']==barang].iloc[0]
            conn = get_connection()
            c = conn.cursor()
            c.execute("INSERT INTO permintaan (nama_karyawan,divisi,barang_id,jumlah,catatan) VALUES (?,?,?,?,?)",
                      (nama,divisi,row['id'],jumlah,catatan))
            conn.commit(); conn.close()
            st.success("Permintaan dikirim!")

# ------------------ Admin ------------------
def show_admin_login():
    st.subheader("Login Admin")
    user = st.text_input("Username")
    pw = st.text_input("Password",type="password")
    if st.button("Login"):
        admin = authenticate_admin(user,pw)
        if admin:
            st.session_state.admin = admin
            st.rerun()
        else:
            st.error("Login gagal")

def show_admin_dashboard():
    st.title("Dashboard Admin")
    df_req = get_requests()
    total_barang = len(get_barang_list())
    total_req = len(df_req)
    pending = len(df_req[df_req['status']=='pending'])
    col1,col2,col3 = st.columns(3)
    col1.metric("Barang",total_barang)
    col2.metric("Permintaan",total_req)
    col3.metric("Pending",pending)

def show_manage_requests():
    st.title("Kelola Permintaan")
    df = get_requests()
    if df.empty:
        st.info("Belum ada permintaan")
        return
    for _,r in df.iterrows():
        with st.expander(f"{r['nama_karyawan']} - {r['nama_barang']} ({r['status']})"):
            st.write(r.to_dict())
            if r['status']=='pending':
                c1,c2 = st.columns(2)
                with c1:
                    if st.button("Setujui",key=f"ok{r['id']}"):
                        if r['jumlah']<=r['stok_tersedia']:
                            conn=get_connection();c=conn.cursor()
                            c.execute("UPDATE permintaan SET status='approved',tanggal_diproses=? WHERE id=?",
                                      (datetime.now(),r['id']))
                            c.execute("UPDATE barang SET stok=stok-? WHERE id=(SELECT barang_id FROM permintaan WHERE id=?)",
                                      (r['jumlah'],r['id']))
                            conn.commit();conn.close();st.rerun()
                with c2:
                    if st.button("Tolak",key=f"rej{r['id']}"):
                        alasan = st.text_input("Alasan",key=f"al{r['id']}")
                        if alasan:
                            conn=get_connection();c=conn.cursor()
                            c.execute("UPDATE permintaan SET status='rejected',alasan_tolak=?,tanggal_diproses=? WHERE id=?",
                                      (alasan,datetime.now(),r['id']))
                            conn.commit();conn.close();st.rerun()
            elif r['status']=='approved':
                if st.button("Selesai",key=f"done{r['id']}"):
                    conn=get_connection();c=conn.cursor()
                    c.execute("UPDATE permintaan SET status='completed',tanggal_diproses=? WHERE id=?",
                              (datetime.now(),r['id']))
                    conn.commit();conn.close();st.rerun()

def show_manage_items():
    st.title("Kelola Barang")
    df=get_barang_list()
    st.dataframe(df)
    with st.form("add_item"):
        nama=st.text_input("Nama")
        kategori=st.text_input("Kategori")
        satuan=st.text_input("Satuan")
        stok=st.number_input("Stok",min_value=0)
        minstok=st.number_input("Minimum",min_value=0,value=10)
        harga=st.number_input("Harga",min_value=0.0,step=100.0)
        if st.form_submit_button("Tambah") and nama:
            conn=get_connection();c=conn.cursor()
            c.execute("INSERT INTO barang (nama_barang,kategori,satuan,stok,minimum_stok,harga_satuan) VALUES (?,?,?,?,?,?)",
                      (nama,kategori,satuan,stok,minstok,harga))
            conn.commit();conn.close();st.rerun()

def show_stock_in():
    st.title("Stok Masuk")
    df=get_barang_list()
    if df.empty:
        st.info("Belum ada barang")
        return
    with st.form("stok_in"):
        barang=st.selectbox("Barang",df['nama_barang'].tolist())
        jumlah=st.number_input("Jumlah",min_value=1)
        supplier=st.text_input("Supplier")
        harga=st.number_input("Harga",min_value=0.0,step=100.0)
        if st.form_submit_button("Catat"):
            row=df[df['nama_barang']==barang].iloc[0]
            total=jumlah*harga
            conn=get_connection();c=conn.cursor()
            c.execute("INSERT INTO stok_masuk (barang_id,jumlah,harga_satuan,total_harga,supplier,tanggal_masuk,admin_id) VALUES (?,?,?,?,?,?,?)",
                      (row['id'],jumlah,harga,total,supplier,date.today(),st.session_state.admin['id']))
            c.execute("UPDATE barang SET stok=stok+? WHERE id=?",(jumlah,row['id']))
            conn.commit();conn.close();st.success("Stok masuk dicatat");st.rerun()

def show_reports():
    st.title("Laporan")
    df_req=get_requests()
    st.subheader("Permintaan")
    st.dataframe(df_req)
    st.subheader("Barang")
    st.dataframe(get_barang_list())

# ------------------ Main ------------------
def main():
    init_database()
    if 'admin' not in st.session_state:
        st.session_state.admin=None
    st.title("🏢 Sistem Inventori ATK")
    if st.session_state.admin:
        menu=["Dashboard","Barang","Permintaan","Stok Masuk","Laporan"]
        choice=st.sidebar.radio("Menu",menu)
        if choice=="Dashboard":
            show_admin_dashboard()
        elif choice=="Barang":
            show_manage_items()
        elif choice=="Permintaan":
            show_manage_requests()
        elif choice=="Stok Masuk":
            show_stock_in()
        elif choice=="Laporan":
            show_reports()
        if st.sidebar.button("Logout"): st.session_state.admin=None;st.rerun()
    else:
        tab1,tab2,tab3=st.tabs(["Lihat Stok","Form Permintaan","Login Admin"])
        with tab1: show_public_inventory()
        with tab2: show_public_request_form()
        with tab3: show_admin_login()

if __name__=="__main__":
    main()
