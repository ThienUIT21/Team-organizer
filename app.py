import calendar
import hashlib
import os
import sqlite3
from datetime import date, datetime, time
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="Project & Meeting Management",
    page_icon="🚀",
    layout="wide",
)

DB_FILE = "project_data.db"
UPLOAD_DIR = "uploaded_meeting_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)


# --- PASSWORD HASHING ---
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# --- DATABASE CONNECTION & INITIALIZATION ---
def get_db_connection():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Users table
        cursor.execute("PRAGMA table_info(users)")
        existing_cols = [col[1] for col in cursor.fetchall()]
        if existing_cols and "password_hash" not in existing_cols:
            cursor.execute("DROP TABLE users")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'Member',
                status TEXT DEFAULT 'Online'
            )
        """)

        # Tasks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                assignee TEXT,
                priority TEXT,
                status TEXT DEFAULT 'To-do',
                deadline TEXT DEFAULT ''
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)")

        # Meetings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                meeting_date TEXT NOT NULL,
                meeting_time TEXT NOT NULL,
                location TEXT DEFAULT '',
                minutes TEXT DEFAULT '',
                file_name TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                created_by TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_meetings_date ON meetings(meeting_date)")

        # Seed initial data if database is empty
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            cursor.executemany(
                "INSERT INTO users (name, password_hash, role, status) VALUES (?, ?, ?, ?)",
                [
                    ("Admin", hash_password("admin123"), "Admin", "Online"),
                    ("Alex Johnson", hash_password("123456"), "Manager", "Online"),
                    ("Sarah Connor", hash_password("123456"), "Member", "Busy"),
                ],
            )

            today_str = date.today().isoformat()
            cursor.executemany(
                "INSERT INTO tasks (title, assignee, priority, status, deadline) VALUES (?, ?, ?, ?, ?)",
                [
                    ("Design Database Architecture", "Alex Johnson", "High", "Done", today_str),
                    ("Implement Authentication", "Sarah Connor", "Urgent", "In Progress", today_str),
                ],
            )

            cursor.execute(
                """
                INSERT INTO meetings (title, meeting_date, meeting_time, location, minutes, created_by)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    "Sprint Planning & Kickoff",
                    today_str,
                    "09:30",
                    "Room A / Google Meet",
                    "Agreed on the key project deliverables for this week.",
                    "Admin",
                ),
            )


init_db()


# --- AUTHENTICATION ---
def authenticate_user(username: str, password: str):
    with get_db_connection() as conn:
        return conn.execute(
            "SELECT * FROM users WHERE name = ? AND password_hash = ?",
            (username, hash_password(password)),
        ).fetchone()


def register_user(username: str, password: str, role: str):
    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO users (name, password_hash, role, status) VALUES (?, ?, ?, 'Online')",
                (username, hash_password(password), role),
            )
        return True, "Account created successfully! Please sign in."
    except sqlite3.IntegrityError:
        return False, "Username already exists!"


def render_auth_page():
    st.markdown("<h2 style='text-align: center;'>🔐 Workspace Access</h2>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.6, 1])

    with col:
        tab_signin, tab_signup = st.tabs(["🔑 Sign In", "📝 Sign Up"])

        with tab_signin:
            with st.form("signin_form"):
                username = st.text_input("Username:")
                password = st.text_input("Password:", type="password")
                if st.form_submit_button("Sign In", use_container_width=True):
                    user = authenticate_user(username.strip(), password.strip())
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.current_user = user["name"]
                        st.session_state.current_role = user["role"]
                        st.rerun()
                    else:
                        st.error("Invalid credentials!")

        with tab_signup:
            with st.form("signup_form"):
                new_username = st.text_input("Choose Username:")
                new_password = st.text_input("Create Password:", type="password")
                confirm_password = st.text_input("Confirm Password:", type="password")
                role = st.selectbox("Role:", ["Member", "Manager", "Guest"])
                if st.form_submit_button("Create Account", use_container_width=True):
                    if not new_username.strip() or not new_password.strip():
                        st.error("Please fill in all fields.")
                    elif len(new_password) < 6:
                        st.error("Password must be at least 6 characters.")
                    elif new_password != confirm_password:
                        st.error("Passwords do not match!")
                    else:
                        success, msg = register_user(new_username.strip(), new_password.strip(), role)
                        if success:
                            st.success(msg)
                        else:
                            st.error(msg)


if not st.session_state.get("authenticated", False):
    render_auth_page()
    st.stop()

# Auto refresh if package is installed
try:
    from streamlit_autorefresh import st_autorefresh

    st_autorefresh(interval=5000, key="datarefresh")
except ImportError:
    pass


# --- DATA QUERIES ---
def get_all_users() -> pd.DataFrame:
    with get_db_connection() as conn:
        return pd.read_sql("SELECT id, name, role, status FROM users", conn)


def get_all_tasks() -> pd.DataFrame:
    with get_db_connection() as conn:
        return pd.read_sql("SELECT * FROM tasks", conn)


def get_all_meetings() -> pd.DataFrame:
    with get_db_connection() as conn:
        return pd.read_sql("SELECT * FROM meetings ORDER BY meeting_date ASC, meeting_time ASC", conn)


def delete_user(name: str):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM users WHERE name = ?", (name,))
        conn.execute("UPDATE tasks SET assignee = 'Unassigned' WHERE assignee = ?", (name,))


def add_task(title: str, assignee: str, priority: str, deadline: str):
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO tasks (title, assignee, priority, status, deadline) VALUES (?, ?, ?, 'To-do', ?)",
            (title, assignee, priority, str(deadline)),
        )


def update_task_status(task_id: int, new_status: str):
    with get_db_connection() as conn:
        conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))


def delete_task(task_id: int):
    with get_db_connection() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def add_meeting(title, meeting_date, meeting_time, location, minutes, file_name, file_path, created_by):
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO meetings (title, meeting_date, meeting_time, location, minutes, file_name, file_path, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, meeting_date, meeting_time, location, minutes, file_name, file_path, created_by),
        )


def update_meeting(meeting_id, title, meeting_date, meeting_time, location, minutes, file_name=None, file_path=None):
    with get_db_connection() as conn:
        if file_name and file_path:
            conn.execute(
                """
                UPDATE meetings 
                SET title = ?, meeting_date = ?, meeting_time = ?, location = ?, minutes = ?, file_name = ?, file_path = ?
                WHERE id = ?
                """,
                (title, meeting_date, meeting_time, location, minutes, file_name, file_path, meeting_id),
            )
        else:
            conn.execute(
                """
                UPDATE meetings 
                SET title = ?, meeting_date = ?, meeting_time = ?, location = ?, minutes = ?
                WHERE id = ?
                """,
                (title, meeting_date, meeting_time, location, minutes, meeting_id),
            )


def delete_meeting(meeting_id: int):
    with get_db_connection() as conn:
        row = conn.execute("SELECT file_path FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if row and row["file_path"] and os.path.exists(row["file_path"]):
            try:
                os.remove(row["file_path"])
            except OSError:
                pass
        conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))


# --- PERMISSIONS & SIDEBAR ---
if "editing_meeting_id" not in st.session_state:
    st.session_state.editing_meeting_id = None

current_role = st.session_state.get("current_role", "Member")
current_user = st.session_state.get("current_user", "")
is_admin = current_role == "Admin"
can_manage = current_role in ["Admin", "Manager"]

st.sidebar.title("🏢 Workspace")
st.sidebar.write(f"👤 User: **{current_user}** ({current_role})")

if st.sidebar.button("🚪 Sign Out"):
    st.session_state.clear()
    st.rerun()

st.sidebar.divider()

menu = st.sidebar.radio(
    "Navigation:",
    [
        "📋 Tasks",
        "📅 Calendar",
        "🤝 Meetings",
        "👤 Team",
        "📊 Analytics",
    ],
)

df_users = get_all_users()
df_tasks = get_all_tasks()
df_meetings = get_all_meetings()


# --- REUSABLE EDIT MEETING FORM ---
def render_meeting_edit_form(meeting_row):
    with st.form(key=f"form_edit_meeting_{meeting_row['id']}"):
        st.info(f"✏️ Editing: **{meeting_row['title']}**")
        edit_title = st.text_input("Meeting Title:", value=meeting_row["title"])

        col1, col2 = st.columns(2)
        with col1:
            try:
                init_d = datetime.strptime(meeting_row["meeting_date"], "%Y-%m-%d").date()
            except ValueError:
                init_d = date.today()
            edit_date = st.date_input("Date:", value=init_d)

        with col2:
            try:
                init_t = datetime.strptime(meeting_row["meeting_time"], "%H:%M").time()
            except ValueError:
                init_t = time(9, 0)
            edit_time = st.time_input("Time:", value=init_t)

        edit_location = st.text_input("Location / Link:", value=meeting_row["location"] or "")
        edit_minutes = st.text_area(
            "Minutes & Notes:",
            value=meeting_row["minutes"] or "",
            height=150,
            placeholder="Record discussions, outcomes, and action items...",
        )

        edit_file = st.file_uploader(
            "Attach or replace document:",
            type=["pdf", "docx", "xlsx", "pptx", "png", "jpg", "txt"],
            key=f"file_edit_{meeting_row['id']}",
        )

        col_save, col_cancel = st.columns(2)
        btn_save = col_save.form_submit_button("Save Changes", type="primary", use_container_width=True)
        btn_cancel = col_cancel.form_submit_button("Cancel", use_container_width=True)

        if btn_save:
            f_name, f_path = None, None
            if edit_file:
                f_name = edit_file.name
                time_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
                f_path = os.path.join(UPLOAD_DIR, f"{time_tag}_{f_name}")
                with open(f_path, "wb") as f:
                    f.write(edit_file.getbuffer())

            update_meeting(
                meeting_row["id"],
                edit_title.strip(),
                edit_date.isoformat(),
                edit_time.strftime("%H:%M"),
                edit_location.strip(),
                edit_minutes.strip(),
                f_name,
                f_path,
            )
            st.session_state.editing_meeting_id = None
            st.rerun()

        if btn_cancel:
            st.session_state.editing_meeting_id = None
            st.rerun()


# =====================================================================
# 1. TASK MANAGEMENT
# =====================================================================
if menu == "📋 Tasks":
    st.title("📋 Tasks Management")

    with st.expander("➕ Create New Task"):
        with st.form("new_task_form"):
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input("Task Title:")
                user_list = df_users["name"].tolist() if not df_users.empty else ["Unassigned"]
                assignee = st.selectbox("Assignee:", user_list)
            with col2:
                priority = st.selectbox("Priority:", ["Low", "Medium", "High", "Urgent"])
                task_deadline = st.date_input("Deadline:", value=date.today())

            if st.form_submit_button("Save Task"):
                if title.strip():
                    add_task(title.strip(), assignee, priority, task_deadline.isoformat())
                    st.rerun()
                else:
                    st.error("Please enter a task title!")

    st.subheader("Kanban Board")
    col_todo, col_inprog, col_done = st.columns(3)

    with col_todo:
        st.info("📌 TO-DO")
        todo_tasks = df_tasks[df_tasks["status"] == "To-do"]
        for _, t in todo_tasks.iterrows():
            st.markdown(f"**{t['title']}**\n- 👤 {t['assignee']}\n- 🚨 {t['priority']}\n- 📅 Due: {t.get('deadline') or 'N/A'}")
            b1, b2 = st.columns([2, 1])
            if b1.button("Start ➡️", key=f"start_{t['id']}", use_container_width=True):
                update_task_status(t["id"], "In Progress")
                st.rerun()
            if can_manage and b2.button("🗑️", key=f"del_todo_{t['id']}"):
                delete_task(t["id"])
                st.rerun()
            st.divider()

    with col_inprog:
        st.warning("⏳ IN PROGRESS")
        inprog_tasks = df_tasks[df_tasks["status"] == "In Progress"]
        for _, t in inprog_tasks.iterrows():
            st.markdown(f"**{t['title']}**\n- 👤 {t['assignee']}\n- 🚨 {t['priority']}\n- 📅 Due: {t.get('deadline') or 'N/A'}")
            b1, b2 = st.columns([2, 1])
            if b1.button("Complete ✅", key=f"done_{t['id']}", use_container_width=True):
                update_task_status(t["id"], "Done")
                st.rerun()
            if can_manage and b2.button("🗑️", key=f"del_inprog_{t['id']}"):
                delete_task(t["id"])
                st.rerun()
            st.divider()

    with col_done:
        st.success("🎉 DONE")
        done_tasks = df_tasks[df_tasks["status"] == "Done"]
        for _, t in done_tasks.iterrows():
            st.markdown(f"**~{t['title']}~**\n- 👤 {t['assignee']}\n- 📅 Due: {t.get('deadline') or 'N/A'}")
            if can_manage and st.button("🗑️ Delete", key=f"del_done_{t['id']}"):
                delete_task(t["id"])
                st.rerun()
            st.divider()

# =====================================================================
# 2. CALENDAR
# =====================================================================
elif menu == "📅 Calendar":
    st.title("📅 Calendar & Schedule")

    if "cal_year" not in st.session_state:
        st.session_state.cal_year = date.today().year
    if "cal_month" not in st.session_state:
        st.session_state.cal_month = date.today().month
    if "selected_cal_date" not in st.session_state:
        st.session_state.selected_cal_date = date.today().isoformat()

    c_prev, c_next, c_label, c_today = st.columns([1, 1, 3, 2])

    if c_prev.button("◀️ Prev"):
        st.session_state.cal_month -= 1
        if st.session_state.cal_month < 1:
            st.session_state.cal_month = 12
            st.session_state.cal_year -= 1
        st.rerun()

    if c_next.button("Next ▶️"):
        st.session_state.cal_month += 1
        if st.session_state.cal_month > 12:
            st.session_state.cal_month = 1
            st.session_state.cal_year += 1
        st.rerun()

    month_name = calendar.month_name[st.session_state.cal_month]
    c_label.subheader(f"🗓️ {month_name} {st.session_state.cal_year}")

    if c_today.button("Today 🎯"):
        st.session_state.cal_year = date.today().year
        st.session_state.cal_month = date.today().month
        st.session_state.selected_cal_date = date.today().isoformat()
        st.rerun()

    # Fixed header row
    week_headers = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    header_cols = st.columns(7)
    for idx, day_name in enumerate(week_headers):
        header_cols[idx].markdown(
            f"<p style='text-align: center; font-weight: bold; margin-bottom: 5px;'>{day_name}</p>",
            unsafe_allow_html=True,
        )

    month_days = calendar.Calendar(firstweekday=6).monthdayscalendar(
        st.session_state.cal_year, st.session_state.cal_month
    )

    for week_idx, week in enumerate(month_days):
        cols = st.columns(7)
        for col_idx, d in enumerate(week):
            with cols[col_idx]:
                if d == 0:
                    st.button(" ", key=f"empty_{week_idx}_{col_idx}", disabled=True, use_container_width=True)
                else:
                    cur_str = f"{st.session_state.cal_year:04d}-{st.session_state.cal_month:02d}-{d:02d}"
                    t_count = len(df_tasks[df_tasks["deadline"] == cur_str]) if not df_tasks.empty else 0
                    m_count = len(df_meetings[df_meetings["meeting_date"] == cur_str]) if not df_meetings.empty else 0

                    badges = []
                    if t_count > 0:
                        badges.append(f"📌{t_count}")
                    if m_count > 0:
                        badges.append(f"👥{m_count}")

                    label = f"{d} " + " ".join(badges) if badges else str(d)
                    is_selected = (cur_str == st.session_state.selected_cal_date)
                    btn_type = "primary" if is_selected or badges else "secondary"

                    if st.button(label, key=f"cal_{cur_str}", use_container_width=True, type=btn_type):
                        st.session_state.selected_cal_date = cur_str
                        st.session_state.editing_meeting_id = None
                        st.rerun()

    st.divider()

    sel_date_obj = datetime.strptime(st.session_state.selected_cal_date, "%Y-%m-%d").date()
    st.subheader(f"Schedule for: {sel_date_obj.strftime('%A, %b %d, %Y')}")

    tab_meet, tab_task = st.tabs(["👥 Meetings", "📌 Tasks Due"])

    with tab_meet:
        meetings_today = (
            df_meetings[df_meetings["meeting_date"] == st.session_state.selected_cal_date]
            if not df_meetings.empty else pd.DataFrame()
        )
        if not meetings_today.empty:
            for _, m in meetings_today.iterrows():
                if st.session_state.editing_meeting_id == m["id"]:
                    render_meeting_edit_form(m)
                else:
                    with st.expander(f"⏰ {m['meeting_time']} - {m['title']}", expanded=True):
                        st.markdown(f"- 📍 **Location:** `{m['location'] or 'Not specified'}`\n- 👤 **Organizer:** `{m['created_by']}`")
                        if m["minutes"]:
                            st.markdown(f"**Minutes:**\n> {m['minutes']}")

                        if m["file_path"] and os.path.exists(m["file_path"]) and m["file_name"]:
                            with open(m["file_path"], "rb") as f:
                                st.download_button(
                                    f"📥 Download: {m['file_name']}",
                                    data=f.read(),
                                    file_name=m["file_name"],
                                    key=f"dl_cal_{m['id']}",
                                )

                        if current_user == m["created_by"] or can_manage or is_admin:
                            c1, c2 = st.columns([1, 4])
                            if c1.button("✏️ Edit", key=f"edit_cal_{m['id']}"):
                                st.session_state.editing_meeting_id = m["id"]
                                st.rerun()
                            if c2.button("🗑️ Delete", key=f"del_cal_m_{m['id']}"):
                                delete_meeting(m["id"])
                                st.rerun()
        else:
            st.info("No meetings scheduled for this date.")

    with tab_task:
        tasks_today = (
            df_tasks[df_tasks["deadline"] == st.session_state.selected_cal_date]
            if not df_tasks.empty else pd.DataFrame()
        )
        if not tasks_today.empty:
            for _, task in tasks_today.iterrows():
                c_info, c_del = st.columns([5, 1])
                c_info.markdown(
                    f"**{task['title']}** | Assignee: `{task['assignee']}` | Priority: `{task['priority']}` | Status: **{task['status']}**"
                )
                if can_manage and c_del.button("🗑️", key=f"del_task_cal_{task['id']}"):
                    delete_task(task["id"])
                    st.rerun()
                st.divider()
        else:
            st.info("No tasks due on this date.")

# =====================================================================
# 3. MEETING MANAGEMENT
# =====================================================================
elif menu == "🤝 Meetings":
    st.title("🤝 Meetings & Minutes")

    with st.expander("➕ Schedule New Meeting"):
        with st.form("new_meeting_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                meet_title = st.text_input("Meeting Title *:")
                meet_date = st.date_input("Date:", value=date.today())
                meet_time = st.time_input("Start Time:", value=time(9, 0))
            with col2:
                meet_location = st.text_input("Location / Link:", placeholder="e.g. Room A / Zoom")
                uploaded_file = st.file_uploader("Meeting Material (optional):", type=["pdf", "docx", "xlsx", "pptx", "png", "jpg", "txt"])

            meet_minutes = st.text_area("Meeting Minutes (optional):", placeholder="Enter notes or leave blank for now...")

            if st.form_submit_button("Schedule Meeting", use_container_width=True):
                if meet_title.strip():
                    f_name, f_path = "", ""
                    if uploaded_file:
                        f_name = uploaded_file.name
                        time_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
                        f_path = os.path.join(UPLOAD_DIR, f"{time_tag}_{f_name}")
                        with open(f_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())

                    add_meeting(
                        meet_title.strip(),
                        meet_date.isoformat(),
                        meet_time.strftime("%H:%M"),
                        meet_location.strip(),
                        meet_minutes.strip(),
                        f_name,
                        f_path,
                        current_user,
                    )
                    st.rerun()
                else:
                    st.error("Please provide a meeting title!")

    st.subheader("Scheduled Meetings")
    if not df_meetings.empty:
        for _, m in df_meetings.iterrows():
            if st.session_state.editing_meeting_id == m["id"]:
                render_meeting_edit_form(m)
            else:
                c1, c2 = st.columns([5, 1.5])
                with c1:
                    st.markdown(f"### 📅 {m['title']}\n- ⏰ `{m['meeting_date']}` at `{m['meeting_time']}`\n- 📍 `{m['location'] or 'Not specified'}` | 👤 Organizer: `{m['created_by']}`")
                    if m["minutes"]:
                        st.markdown(f"**Minutes:**\n> {m['minutes']}")

                    if m["file_path"] and os.path.exists(m["file_path"]) and m["file_name"]:
                        with open(m["file_path"], "rb") as f:
                            st.download_button(f"📥 Download: {m['file_name']}", data=f.read(), file_name=m["file_name"], key=f"dl_list_{m['id']}")

                with c2:
                    if current_user == m["created_by"] or can_manage or is_admin:
                        if st.button("✏️ Edit / Minutes", key=f"edit_list_{m['id']}", use_container_width=True):
                            st.session_state.editing_meeting_id = m["id"]
                            st.rerun()

                        if st.button("🗑️ Delete", key=f"del_meet_list_{m['id']}", use_container_width=True):
                            delete_meeting(m["id"])
                            st.rerun()
                st.divider()
    else:
        st.info("No meetings found.")

# =====================================================================
# 4. TEAM & MEMBERS
# =====================================================================
elif menu == "👤 Team":
    st.title("👤 Team & Members")
    if is_admin:
        with st.expander("🗑️ Delete Member (Admin Only)"):
            if not df_users.empty:
                removable = [u for u in df_users["name"].tolist() if u != current_user]
                if removable:
                    user_to_delete = st.selectbox("Select member:", removable)
                    if st.button("Delete Member", type="primary"):
                        delete_user(user_to_delete)
                        st.rerun()
                else:
                    st.info("No other removable users found.")
    st.dataframe(df_users, use_container_width=True)

# =====================================================================
# 5. ANALYTICS
# =====================================================================
elif menu == "📊 Analytics":
    st.title("📊 Performance & Analytics")
    if not df_tasks.empty:
        m1, m2, m3 = st.columns(3)
        m1.metric("Total Tasks", len(df_tasks))
        m2.metric("Completed Tasks", len(df_tasks[df_tasks["status"] == "Done"]))
        m3.metric("Total Meetings", len(df_meetings) if not df_meetings.empty else 0)
        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(px.pie(df_tasks, names="status", title="Task Status Ratio", hole=0.4), use_container_width=True)
        with col2:
            st.plotly_chart(px.bar(df_tasks, x="assignee", color="status", title="Tasks Assigned per Member"), use_container_width=True)
    else:
        st.info("No task data available for reports.")
