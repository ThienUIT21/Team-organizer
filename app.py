import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import sqlite3
import hashlib

# Cấu hình trang web
st.set_page_config(page_title="Project & Task Management", page_icon="🚀", layout="wide")

DB_FILE = "project_data.db"

# --- HÀM MÃ HÓA MẬT KHẨU (SHA-256) ---
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# --- HÀM KẾT NỐI VÀ KHỞI TẠO CƠ SỞ DỮ LIỆU ---
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Bảng Users (chứa cả thông tin đăng nhập và thành viên)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'Member',
                status TEXT DEFAULT 'Online'
            )
        ''')
        # Bảng Tasks
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                assignee TEXT,
                priority TEXT,
                status TEXT
            )
        ''')
        conn.commit()

        # Tạo sẵn tài khoản Admin mặc định nếu database còn trống
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            default_admin_pw = hash_password("admin123")
            default_member_pw = hash_password("123456")
            cursor.executemany("INSERT INTO users (name, password_hash, role, status) VALUES (?, ?, ?, ?)", [
                ("Admin", default_admin_pw, "Admin", "Online"),
                ("Alex Johnson", default_member_pw, "Manager", "Online"),
                ("Sarah Connor", default_member_pw, "Member", "Busy")
            ])
            cursor.executemany("INSERT INTO tasks (title, assignee, priority, status) VALUES (?, ?, ?, ?)", [
                ("Design Database Architecture", "Alex Johnson", "High", "Done"),
                ("Implement Authentication", "Sarah Connor", "Urgent", "In Progress"),
                ("Write Documentation", "Sarah Connor", "Low", "To-do")
            ])
            conn.commit()

init_db()

# --- CÁC HÀM XỬ LÝ AUTHENTICATION ---
def authenticate_user(username, password):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE name = ? AND password_hash = ?", (username, hash_password(password)))
        return cursor.fetchone()

def register_user(username, password, role):
    with get_db_connection() as conn:
        try:
            conn.execute(
                "INSERT INTO users (name, password_hash, role, status) VALUES (?, ?, ?, 'Online')",
                (username, hash_password(password), role)
            )
            conn.commit()
            return True, "Account registered successfully! Please sign in."
        except sqlite3.IntegrityError:
            return False, "Username already exists! Please choose another one."

# --- GIAO DIỆN ĐĂNG NHẬP / ĐĂNG KÝ (SIGN IN / SIGN UP) ---
def render_auth_page():
    st.markdown("<h2 style='text-align: center;'>🔐 Workspace Access</h2>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        tab_signin, tab_signup = st.tabs(["🔑 Sign In", "📝 Sign Up"])

        # TAB 1: SIGN IN
        with tab_signin:
            with st.form("signin_form"):
                username = st.text_input("Username:")
                password = st.text_input("Password:", type="password")
                submit_signin = st.form_submit_button("Sign In", use_container_width=True)

                if submit_signin:
                    if not username.strip() or not password.strip():
                        st.error("Please provide both username and password!")
                    else:
                        user = authenticate_user(username.strip(), password.strip())
                        if user:
                            st.session_state.authenticated = True
                            st.session_state.current_user = user["name"]
                            st.session_state.current_role = user["role"]
                            st.success("Signed in successfully!")
                            st.rerun()
                        else:
                            st.error("Invalid username or password!")

        # TAB 2: SIGN UP
        with tab_signup:
            with st.form("signup_form"):
                new_username = st.text_input("Choose a Username:")
                new_password = st.text_input("Create Password:", type="password")
                confirm_password = st.text_input("Confirm Password:", type="password")
                role = st.selectbox("Role:", ["Member", "Manager", "Guest"])
                submit_signup = st.form_submit_button("Create Account", use_container_width=True)

                if submit_signup:
                    if not new_username.strip() or not new_password.strip():
                        st.error("Username and password cannot be empty!")
                    elif len(new_password) < 6:
                        st.error("Password must be at least 6 characters long!")
                    elif new_password != confirm_password:
                        st.error("Passwords do not match!")
                    else:
                        success, msg = register_user(new_username.strip(), new_password.strip(), role)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)

# Kiểm tra trạng thái phiên làm việc
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    render_auth_page()
    st.stop()  # Chặn không cho tải dữ liệu phía dưới nếu chưa đăng nhập

# =====================================================================
# NỘI DUNG ỨNG DỤNG SAU KHI ĐĂNG NHẬP THÀNH CÔNG
# =====================================================================

# Tự động làm mới Real-time mỗi 3 giây
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=3000, key="datarefresh")
except ImportError:
    pass

# --- CÁC HÀM XỬ LÝ DỮ LIỆU ---
def get_all_users():
    with get_db_connection() as conn:
        return pd.read_sql("SELECT id, name, role, status FROM users", conn)

def get_all_tasks():
    with get_db_connection() as conn:
        return pd.read_sql("SELECT * FROM tasks", conn)

def delete_user(name):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM users WHERE name = ?", (name,))
        conn.execute("UPDATE tasks SET assignee = 'Unassigned' WHERE assignee = ?", (name,))
        conn.commit()

def add_task(title, assignee, priority):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO tasks (title, assignee, priority, status) VALUES (?, ?, ?, 'To-do')",
            (title, assignee, priority)
        )
        conn.commit()

def update_task_status(task_id, new_status):
    with get_db_connection() as conn:
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))
        conn.commit()

# --- THANH MENU BÊN TRÁI (SIDEBAR) ---
st.sidebar.title("🏢 Workspace")
st.sidebar.caption("🟢 Real-time sync active")
st.sidebar.write(f"👤 User: **{st.session_state.get('current_user')}** ({st.session_state.get('current_role')})")

if st.sidebar.button("🚪 Sign Out"):
    st.session_state.authenticated = False
    st.session_state.current_user = None
    st.session_state.current_role = None
    st.rerun()

st.sidebar.divider()

menu = st.sidebar.radio(
    "Navigation:",
    ["📋 Task Management", "👤 Team & Members", "📊 Reports & Analytics", "⏱️ Time Tracker"]
)

df_users = get_all_users()
df_tasks = get_all_tasks()

# --- 1. MODULE:
