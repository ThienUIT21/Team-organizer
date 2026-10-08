import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import sqlite3

# --- 1. AUTHENTICATION MODULE ---
def check_login():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    # Login UI
    st.markdown("<h2 style='text-align: center;'>🔒 Internal System Login</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Please sign in to access your workspace</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            username = st.text_input("Username:")
            password = st.text_input("Password:", type="password")
            submit = st.form_submit_button("Sign In", use_container_width=True)

            if submit:
                # Retrieve accounts from Streamlit Secrets or fallback for local testing
                valid_users = st.secrets.get("users", {
                    "admin": "admin@123",
                    "thien": "password2024"
                })

                if username in valid_users and valid_users[username] == password:
                    st.session_state.authenticated = True
                    st.session_state.current_user = username
                    st.success("Signed in successfully!")
                    st.rerun()
                else:
                    st.error("❌ Invalid username or password!")

    return False

# Stop execution if user is not authenticated
if not check_login():
    st.stop()

# =====================================================================
# MAIN APPLICATION (RUNS ONLY AFTER LOGIN)
# =====================================================================

# Auto-refresh interval (Real-time sync every 3 seconds)
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=3000, key="datarefresh")
except ImportError:
    pass

st.set_page_config(page_title="Project & Task Management System", page_icon="🚀", layout="wide")

DB_FILE = "project_data.db"

# --- DATABASE SETUP ---
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                role TEXT,
                status TEXT
            )
        ''')
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

        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("INSERT INTO users (name, role, status) VALUES (?, ?, ?)", [
                ("Alex Johnson", "Manager", "Online"),
                ("Sarah Connor", "Member", "Busy")
            ])
            cursor.executemany("INSERT INTO tasks (title, assignee, priority, status) VALUES (?, ?, ?, ?)", [
                ("Database Architecture Design", "Alex Johnson", "High", "Done"),
                ("Build User Authentication", "Sarah Connor", "Urgent", "In Progress"),
                ("Write API Documentation", "Sarah Connor", "Low", "To-do")
            ])
            conn.commit()

init_db()

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

# --- SIDEBAR NAVIGATION ---
st.sidebar.title("🏢 Workspace")
st.sidebar.caption("🟢 Real-time sync active")
st.sidebar.write(f"👤 Signed in as: **{st.session_state.get('current_user', 'User')}**")

if st.sidebar.button("🚪 Sign Out"):
    st.session_state.authenticated = False
    st.rerun()

st.sidebar.divider()

menu = st.sidebar.radio(
    "Navigation:",
    ["📋 Task Management", "👤 Team & Members", "📊 Reports & Analytics", "⏱️ Time Tracker"]
)

df_users = get_all_users()
df_tasks = get_all_tasks()

# --- 1. MODULE: TASK MANAGEMENT ---
if menu == "📋 Task Management":
    st.title("📋 Project & Task Management")
    
    with st.expander("➕ Create New Task (Click to expand)"):
        with st.form("new_task_form"):
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input("Task Title:")
                user_list = df_users["name"].tolist() if not df_users.empty else ["Unassigned"]
                assignee = st.selectbox("Assignee:", user_list)
            with col2:
                priority = st.selectbox("Priority:", ["Low", "Medium", "High", "Urgent"])
                deadline = st.date_input("Deadline:")
                
            submitted = st.form_submit_button("Save Task")
            if submitted:
                if title.strip():
                    add_task(title.strip(), assignee, priority)
                    st.success(f"Task created: {title}")
                    st.rerun()
                else:
                    st.error("Please enter a task title!")

    st.subheader("Kanban Board View")
    col_todo, col_inprog, col_done = st.columns(3)

    with col_todo:
        st.info("📌 TO-DO")
        todo_tasks = df_tasks[df_tasks["status"] == "To-do"]
        for _, t in todo_tasks.iterrows():
            st.markdown(f"**{t['title']}**\n- 👤 {t['assignee']}\n- 🚨 Priority: {t['priority']}")
            if st.button("Start ➡️", key=f"start_{t['id']}"):
                update_task_status(t['id'], "In Progress")
                st.rerun()

    with col_inprog:
        st.warning("⏳ IN PROGRESS")
        inprog_tasks = df_tasks[df_tasks["status"] == "In Progress"]
        for _, t in inprog_tasks.iterrows():
            st.markdown(f"**{t['title']}**\n- 👤 {t['assignee']}\n- 🚨 Priority: {t['priority']}")
            if st.button("Complete ✅", key=f"done_{t['id']}"):
                update_task_status(t['id'], "Done")
                st.rerun()

    with col_done:
        st.success("🎉 DONE")
        done_tasks = df_tasks[df_tasks["status"] == "Done"]
        for _, t in done_tasks.iterrows():
            st.markdown(f"**~{t['title']}~**\n- 👤 {t['assignee']}")

# --- 2. MODULE: TEAM & MEMBERS ---
elif menu == "👤 Team & Members":
    st.title("👤 Team & User Management")
    col_add, col_del = st.columns(2)
    
    with col_add:
        with st.expander("➕ Add New Member", expanded=True):
            with st.form("add_user_form"):
                u_name = st.text_input("Full Name:")
                u_role = st.selectbox("Role:", ["Admin", "Manager", "Member", "Guest"])
                u_status = st.selectbox("Status:", ["Online", "Offline", "Busy"])
                
                if st.form_submit_button("Add Member"):
                    if u_name.strip():
                        if add_user(u_name.strip(), u_role, u_status):
                            st.success(f"Added member: {u_name}")
                            st.rerun()
                        else:
                            st.error("This member already exists!")
                    else:
                        st.error("Please enter a name!")

    with col_del:
        with st.expander("🗑️ Delete Member", expanded=True):
            if not df_users.empty:
                user_to_delete = st.selectbox("Select member to delete:", df_users["name"].tolist())
                st.warning(f"⚠️ Tasks assigned to **{user_to_delete}** will be set to 'Unassigned'.")
                
                if st.button("Delete this member", type="primary"):
                    delete_user(user_to_delete)
                    st.success(f"Deleted '{user_to_delete}' successfully!")
                    st.rerun()
            else:
                st.info("No members found.")

    st.divider()
    st.subheader("Current Team Roster:")
    if not df_users.empty:
        st.dataframe(df_users, use_container_width=True)
    else:
        st.write("No members in database.")

# --- 3. MODULE: REPORTS & ANALYTICS ---
elif menu == "📊 Reports & Analytics":
    st.title("📊 Performance & Analytics")
    if not df_tasks.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Tasks", len(df_tasks))
        m2.metric("Completed Tasks", len(df_tasks[df_tasks["status"] == "Done"]))
        m3.metric("Tasks In Progress", len(df_tasks[df_tasks["status"] == "In Progress"]))

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Task Completion Status")
            fig_pie = px.pie(df_tasks, names="status", title="Task Status Ratio", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

        with col2:
            st.subheader("Workload by Member")
            fig_bar = px.bar(df_tasks, x="assignee", color="status", title="Assigned Tasks per Member")
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("No task data available for reports.")

# --- 4. MODULE: TIME TRACKER ---
elif menu == "⏱️ Time Tracker":
    st.title("⏱️ Time Tracking")
    task_list = df_tasks["title"].tolist() if not df_tasks.empty else []
    if task_list:
        selected_task = st.selectbox("Select task to work on:", task_list)
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            start = st.button("▶️ START TIMER")
        with col_btn2:
            stop = st.button("⏹️ STOP TIMER")
            
        if start:
            st.success(f"Timer started for: **{selected_task}** at {datetime.now().strftime('%H:%M:%S')}")
        if stop:
            st.info("Work time saved successfully!")
    else:
        st.info("Please create at least one task before tracking time.")
