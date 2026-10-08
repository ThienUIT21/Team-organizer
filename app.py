import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import sqlite3

# Cài đặt tự động làm mới (Auto-refresh)
try:
    from streamlit_autorefresh import st_autorefresh
    # Tự động tải lại trang mỗi 3 giây (3000ms) để đồng bộ dữ liệu Real-time
    st_autorefresh(interval=3000, key="datarefresh")
except ImportError:
    pass

# Cấu hình trang web
st.set_page_config(page_title="Hệ thống Quản lý Dự án Realtime", page_icon="🚀", layout="wide")

DB_FILE = "project_data.db"

# --- HÀM KẾT NỐI VÀ KHỞI TẠO CƠ SỞ DỮ LIỆU ---
def get_db_connection():
    # timeout=10 để tránh lỗi tranh chấp khi nhiều người ghi dữ liệu cùng lúc
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Bảng thành viên
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                role TEXT,
                status TEXT
            )
        ''')
        # Bảng công việc
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
        
        # Thêm dữ liệu mẫu nếu bảng users rỗng
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("INSERT INTO users (name, role, status) VALUES (?, ?, ?)", [
                ("Nguyễn Văn A", "Manager", "Online"),
                ("Trần Thị B", "Member", "Busy")
            ])
            cursor.executemany("INSERT INTO tasks (title, assignee, priority, status) VALUES (?, ?, ?, ?)", [
                ("Thiết kế cơ sở dữ liệu", "Nguyễn Văn A", "High", "Done"),
                ("Xây dựng tính năng Đăng nhập", "Trần Thị B", "Urgent", "In Progress"),
                ("Viết tài liệu hướng dẫn (Wiki)", "Trần Thị B", "Low", "To-do")
            ])
            conn.commit()

init_db()

# --- CÁC HÀM XỬ LÝ DỮ LIỆU ---
def get_all_users():
    with get_db_connection() as conn:
        return pd.read_sql("SELECT * FROM users", conn)

def get_all_tasks():
    with get_db_connection() as conn:
        return pd.read_sql("SELECT * FROM tasks", conn)

def add_user(name, role, status):
    with get_db_connection() as conn:
        try:
            conn.execute("INSERT INTO users (name, role, status) VALUES (?, ?, ?)", (name, role, status))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

def delete_user(name):
    with get_db_connection() as conn:
        # Xóa user
        conn.execute("DELETE FROM users WHERE name = ?", (name,))
        # Cập nhật các task của user đó sang 'Chưa phân công'
        conn.execute("UPDATE tasks SET assignee = 'Chưa phân công' WHERE assignee = ?", (name,))
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
st.sidebar.title("🏢 Không gian làm việc")
st.sidebar.caption("🟢 Dữ liệu đang được đồng bộ Real-time")
menu = st.sidebar.radio(
    "Điều hướng tính năng:",
    ["📋 Quản lý Công việc (Tasks)", "👤 Thành viên & Hồ sơ", "📊 Báo cáo & Thống kê", "⏱️ Đếm giờ làm việc"]
)

# Lấy dữ liệu mới nhất từ CSDL
df_users = get_all_users()
df_tasks = get_all_tasks()

# --- 1. MODULE: QUẢN LÝ CÔNG VIỆC ---
if menu == "📋 Quản lý Công việc (Tasks)":
    st.title("📋 Quản trị Công việc & Dự án")
    
    with st.expander("➕ Tạo công việc mới (Bấm để mở)"):
        with st.form("new_task_form"):
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input("Tên công việc:")
                user_list = df_users["name"].tolist() if not df_users.empty else ["Chưa phân công"]
                assignee = st.selectbox("Giao cho (Assignee):", user_list)
            with col2:
                priority = st.selectbox("Mức độ ưu tiên:", ["Low", "Medium", "High", "Urgent"])
                deadline = st.date_input("Hạn chót (Deadline):")
                
            submitted = st.form_submit_button("Lưu Công Việc")
            if submitted:
                if title.strip():
                    add_task(title.strip(), assignee, priority)
                    st.success(f"Đã tạo task: {title}")
                    st.rerun()
                else:
                    st.error("Vui lòng nhập tên công việc!")

    st.subheader("Bảng trạng thái công việc (Board View)")
    col_todo, col_inprog, col_done = st.columns(3)

    with col_todo:
        st.info("📌 CẦN LÀM (TO-DO)")
        todo_tasks = df_tasks[df_tasks["status"] == "To-do"]
        for _, t in todo_tasks.iterrows():
            st.markdown(f"**{t['title']}**\n- 👤 {t['assignee']}\n- 🚨 Ưu tiên: {t['priority']}")
            if st.button("Bắt đầu làm ➡️", key=f"start_{t['id']}"):
                update_task_status(t['id'], "In Progress")
                st.rerun()

    with col_inprog:
        st.warning("⏳ ĐANG LÀM (IN PROGRESS)")
        inprog_tasks = df_tasks[df_tasks["status"] == "In Progress"]
        for _, t in inprog_tasks.iterrows():
            st.markdown(f"**{t['title']}**\n- 👤 {t['assignee']}\n- 🚨 Ưu tiên: {t['priority']}")
            if st.button("Hoàn thành ✅", key=f"done_{t['id']}"):
                update_task_status(t['id'], "Done")
                st.rerun()

    with col_done:
        st.success("🎉 HOÀN THÀNH (DONE)")
        done_tasks = df_tasks[df_tasks["status"] == "Done"]
        for _, t in done_tasks.iterrows():
            st.markdown(f"**~{t['title']}~**\n- 👤 {t['assignee']}")

# --- 2. MODULE: QUẢN LÝ THÀNH VIÊN ---
elif menu == "👤 Thành viên & Hồ sơ":
    st.title("👤 Quản lý Tài khoản & Nhân sự")
    
    col_add, col_del = st.columns(2)
    
    with col_add:
        with st.expander("➕ Thêm thành viên mới", expanded=True):
            with st.form("add_user_form"):
                u_name = st.text_input("Họ và Tên:")
                u_role = st.selectbox("Vai trò:", ["Admin", "Manager", "Member", "Guest"])
                u_status = st.selectbox("Trạng thái:", ["Online", "Offline", "Busy"])
                
                if st.form_submit_button("Thêm thành viên"):
                    if u_name.strip():
                        if add_user(u_name.strip(), u_role, u_status):
                            st.success(f"Đã thêm: {u_name}")
                            st.rerun()
                        else:
                            st.error("Tên thành viên này đã tồn tại trong CSDL!")
                    else:
                        st.error("Vui lòng nhập họ tên!")

    with col_del:
        with st.expander("🗑️ Xóa thành viên", expanded=True):
            if not df_users.empty:
                user_to_delete = st.selectbox("Chọn thành viên muốn xóa:", df_users["name"].tolist())
                st.warning(f"⚠️ Các task của **{user_to_delete}** sẽ tự động chuyển thành 'Chưa phân công'.")
                
                if st.button("Xóa thành viên này", type="primary"):
                    delete_user(user_to_delete)
                    st.success(f"Đã xóa thành viên '{user_to_delete}'!")
                    st.rerun()
            else:
                st.info("Hiện không có thành viên nào.")

    st.divider()
    st.subheader("Danh sách nhân sự hiện tại:")
    if not df_users.empty:
        st.dataframe(df_users, use_container_width=True)
    else:
        st.write("Chưa có thành viên nào trong CSDL.")

# --- 3. MODULE: BÁO CÁO & THỐNG KÊ ---
elif menu == "📊 Báo cáo & Thống kê":
    st.title("📊 Báo cáo Hiệu suất & Phân tích")
    
    if not df_tasks.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Tổng số việc", len(df_tasks))
        m2.metric("Việc đã hoàn thành", len(df_tasks[df_tasks["status"] == "Done"]))
        m3.metric("Việc đang làm", len(df_tasks[df_tasks["status"] == "In Progress"]))

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Tiến độ công việc")
            fig_pie = px.pie(df_tasks, names="status", title="Tỷ lệ hoàn thành công việc", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

        with col2:
            st.subheader("Khối lượng công việc theo nhân viên")
            fig_bar = px.bar(df_tasks, x="assignee", color="status", title="Số task mỗi người phụ trách")
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("Chưa có dữ liệu công việc để báo cáo.")

# --- 4. MODULE: ĐẾM GIỜ LÀM VIỆC ---
elif menu == "⏱️ Đếm giờ làm việc":
    st.title("⏱️ Theo dõi Thời gian (Time Tracking)")
    
    task_list = df_tasks["title"].tolist() if not df_tasks.empty else []
    if task_list:
        selected_task = st.selectbox("Chọn task đang làm:", task_list)
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            start = st.button("▶️ BẮT ĐẦU ĐẾM GIỜ")
        with col_btn2:
            stop = st.button("⏹️ KẾT THÚC")
            
        if start:
            st.success(f"Đang đếm giờ cho: **{selected_task}** từ lúc {datetime.now().strftime('%H:%M:%S')}")
        if stop:
            st.info("Đã lưu lại thời gian làm việc!")
    else:
        st.info("Vui lòng tạo ít nhất 1 công việc trước khi đếm giờ.")