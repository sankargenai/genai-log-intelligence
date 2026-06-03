import streamlit as st
import pandas as pd
from groq import Groq
import chromadb
import hashlib
import sqlite3
import json
import io
from datetime import datetime

# ── Database setup ──
def init_db():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE,
                  password TEXT,
                  role TEXT,
                  created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS activity_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT,
                  action TEXT,
                  timestamp TEXT)''')
    # Create default admin if not exists
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES (NULL,'admin','admin123','admin',?)",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
    conn.commit()
    conn.close()

def log_activity(username, action):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("INSERT INTO activity_log VALUES (NULL,?,?,?)",
              (username, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT id, username, role, created_at FROM users")
    users = c.fetchall()
    conn.close()
    return users

def get_activity_log():
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT username, action, timestamp FROM activity_log ORDER BY timestamp DESC LIMIT 50")
    logs = c.fetchall()
    conn.close()
    return logs

def create_user(username, password, role):
    try:
        conn = sqlite3.connect("users.db")
        c = conn.cursor()
        c.execute("INSERT INTO users VALUES (NULL,?,?,?,?)",
                  (username, password, role,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def delete_user(username):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE username=?", (username,))
    conn.commit()
    conn.close()

def verify_login(username, password):
    conn = sqlite3.connect("users.db")
    c = conn.cursor()
    c.execute("SELECT role FROM users WHERE username=? AND password=?",
              (username, password))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

# ── File reader ──
def read_file(uploaded_file):
    file_name = uploaded_file.name.lower()
    try:
        if file_name.endswith(".csv"):
            return pd.read_csv(uploaded_file)
        elif file_name.endswith((".xlsx", ".xls")):
            return pd.read_excel(uploaded_file)
        elif file_name.endswith(".json"):
            data = json.load(uploaded_file)
            if isinstance(data, list):
                return pd.DataFrame(data)
            elif isinstance(data, dict):
                return pd.DataFrame([data])
        elif file_name.endswith(".txt"):
            content = uploaded_file.read().decode("utf-8")
            lines = content.strip().split("\n")
            return pd.DataFrame({"message": lines,
                                  "severity": "INFO",
                                  "source": "txt",
                                  "application": "unknown",
                                  "error_code": "N/A",
                                  "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                  "root_cause": "N/A",
                                  "recommendation": "N/A"})
    except Exception as e:
        st.error(f"❌ Error reading file: {str(e)}")
        return None

# ── ChromaDB setup ──
@st.cache_resource
def init_chromadb():
    client = chromadb.Client()
    collection = client.get_or_create_collection("log_incidents")
    return collection

# ── Initialize ──
init_db()
collection = init_chromadb()

st.set_page_config(page_title="GenAI Log Intelligence",
                   page_icon="🔍", layout="wide")

# ── Session state ──
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "role" not in st.session_state:
    st.session_state.role = ""

# ══════════════════════════════════════════
# LOGIN PAGE
# ══════════════════════════════════════════
def login_page():
    st.title("🔍 GenAI Log Intelligence Assistant")
    st.caption("Please login to continue")
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("### 🔐 Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login", type="primary", use_container_width=True):
            if username and password:
                role = verify_login(username, password)
                if role:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = role
                    log_activity(username, "Logged in")
                    st.rerun()
                else:
                    st.error("❌ Invalid username or password")
            else:
                st.warning("⚠️ Please enter username and password")

        st.markdown("---")
        st.caption("Default admin — username: admin | password: admin123")

# ══════════════════════════════════════════
# ADMIN PAGE
# ══════════════════════════════════════════
def admin_page():
    st.title("⚙️ Admin Panel")
    st.caption(f"Logged in as: {st.session_state.username} | Role: Admin")

    if st.button("🚪 Logout"):
        log_activity(st.session_state.username, "Logged out")
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.rerun()

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["👥 Users", "➕ Create User", "📋 Activity Log"])

    # ── Tab 1: View Users ──
    with tab1:
        st.markdown("### All Users")
        users = get_all_users()
        if users:
            df_users = pd.DataFrame(users,
                                    columns=["ID", "Username", "Role", "Created At"])
            st.dataframe(df_users, use_container_width=True)

            st.markdown("### Delete User")
            usernames = [u[1] for u in users if u[1] != "admin"]
            if usernames:
                user_to_delete = st.selectbox("Select user to delete", usernames)
                if st.button("🗑️ Delete User", type="primary"):
                    delete_user(user_to_delete)
                    log_activity(st.session_state.username,
                                 f"Deleted user: {user_to_delete}")
                    st.success(f"✅ User {user_to_delete} deleted!")
                    st.rerun()
            else:
                st.info("No users to delete")

    # ── Tab 2: Create User ──
    with tab2:
        st.markdown("### Create New User")
        new_username = st.text_input("New Username")
        new_password = st.text_input("New Password", type="password")
        new_role = st.selectbox("Role", ["user", "admin"])

        if st.button("➕ Create User", type="primary"):
            if new_username and new_password:
                success = create_user(new_username, new_password, new_role)
                if success:
                    log_activity(st.session_state.username,
                                 f"Created user: {new_username} role: {new_role}")
                    st.success(f"✅ User {new_username} created successfully!")
                else:
                    st.error("❌ Username already exists!")
            else:
                st.warning("⚠️ Please fill all fields")

    # ── Tab 3: Activity Log ──
    with tab3:
        st.markdown("### Recent Activity")
        activity = get_activity_log()
        if activity:
            df_activity = pd.DataFrame(activity,
                                       columns=["Username", "Action", "Timestamp"])
            st.dataframe(df_activity, use_container_width=True)
        else:
            st.info("No activity yet")

# ══════════════════════════════════════════
# ANALYSIS PAGE
# ══════════════════════════════════════════
def analysis_page():
    st.title("🔍 GenAI Log Intelligence Assistant")
    st.caption(f"Logged in as: {st.session_state.username} | "
               f"Upload your log file → AI finds similar past incidents → Smart root cause analysis")

    # ── Sidebar ──
    with st.sidebar:
        st.header("⚙️ Settings")
        api_key = st.text_input("Groq API Key", type="password",
                                help="Get your free key at console.groq.com")
        st.markdown("---")
        st.header("🔎 Filters")
        severity_filter = st.multiselect("Severity",
                                         ["ERROR", "CRITICAL", "WARNING", "INFO"],
                                         default=["ERROR", "CRITICAL"])
        source_filter = st.multiselect("Source",
                                       ["spark", "azure", "aws", "gcp",
                                        "databricks", "sql", "python"])
        max_rows = st.slider("Max rows to analyze", 5, 50, 10)
        st.markdown("---")
        st.header("🧠 RAG Memory")
        rag_status = st.empty()
        st.markdown("---")
        if st.button("🚪 Logout"):
            log_activity(st.session_state.username, "Logged out")
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.role = ""
            st.rerun()

    # ── File Upload ──
    st.markdown("### 📂 Upload Your Log File")
    st.caption("Supported formats: CSV, Excel (.xlsx, .xls), JSON, TXT")
    uploaded_file = st.file_uploader("Upload file",
                                     type=["csv", "xlsx", "xls", "json", "txt"])

    if uploaded_file:
        df = read_file(uploaded_file)

        if df is not None:
            log_activity(st.session_state.username,
                         f"Uploaded file: {uploaded_file.name}")
            st.success(f"✅ Loaded {len(df):,} records from {uploaded_file.name}")

            # ── Load into ChromaDB ──
            if collection.count() == 0:
                with st.spinner("🧠 Loading incidents into RAG memory..."):
                    documents = []
                    ids = []
                    metadatas = []

                    for idx, row in df.iterrows():
                        msg = str(row.get("message", ""))
                        app = str(row.get("application", "unknown"))
                        src = str(row.get("source", "unknown"))
                        err = str(row.get("error_code", "N/A"))
                        rc = str(row.get("root_cause", "N/A"))
                        rec = str(row.get("recommendation", "N/A"))

                        doc = (f"Error: {msg} | App: {app} | "
                               f"Source: {src} | Code: {err} | "
                               f"Root Cause: {rc} | Fix: {rec}")

                        unique_id = f"log_{idx}_{hashlib.md5(doc.encode()).hexdigest()}"
                        documents.append(doc)
                        ids.append(unique_id)
                        metadatas.append({
                            "severity": str(row.get("severity", "INFO")),
                            "application": app,
                            "source": src,
                            "error_code": err
                        })

                    collection.add(
                        documents=documents,
                        ids=ids,
                        metadatas=metadatas
                    )
                st.success("✅ RAG memory loaded!")
            else:
                rag_status.success(f"🧠 {collection.count()} incidents in memory")

            # ── Apply filters ──
            filtered = df.copy()
            if "severity" in df.columns and severity_filter:
                filtered = filtered[filtered["severity"].isin(severity_filter)]
            if "source" in df.columns and source_filter:
                filtered = filtered[filtered["source"].isin(source_filter)]

            # ── Quick stats ──
            st.markdown("### 📊 Quick Overview")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Records", len(df))
            col2.metric("Errors",
                        len(df[df["severity"] == "ERROR"])
                        if "severity" in df.columns else "N/A")
            col3.metric("Critical",
                        len(df[df["severity"] == "CRITICAL"])
                        if "severity" in df.columns else "N/A")
            col4.metric("After Filter", len(filtered))

            # ── Show table ──
            st.markdown("### 📋 Filtered Data")
            st.dataframe(filtered.head(max_rows), use_container_width=True)

            # ── AI Analysis ──
            st.markdown("### 🤖 AI Analysis with RAG")

            if not api_key:
                st.warning("⚠️ Please enter your Groq API key in the sidebar.")
            else:
                if st.button("🚀 Analyze with AI + RAG", type="primary"):
                    sample = filtered.head(max_rows)

                    with st.spinner("🔍 Searching RAG memory..."):
                        query_text = " ".join([
                            str(row.get("message", ""))
                            for _, row in sample.iterrows()
                        ])
                        results = collection.query(
                            query_texts=[query_text],
                            n_results=5
                        )
                        similar_incidents = results['documents'][0]
                        similar_text = "\n".join(
                            [f"- {doc}" for doc in similar_incidents])

                    st.info(f"🧠 RAG found {len(similar_incidents)} similar past incidents")

                    log_text = ""
                    for _, row in sample.iterrows():
                        log_text += " | ".join(
                            [f"{col}: {row[col]}" for col in df.columns]) + "\n"

                    prompt = f"""You are a senior data engineering expert.

CURRENT LOG ERRORS:
{log_text}

SIMILAR PAST INCIDENTS FROM MEMORY:
{similar_text}

Provide:
1. Overall Summary
2. Top Issues
3. Root Causes
4. Recommendations
5. Priority Order

Be specific and beginner friendly."""

                    with st.spinner("🤖 AI is analyzing..."):
                        try:
                            client = Groq(api_key=api_key)
                            response = client.chat.completions.create(
                                model="llama-3.3-70b-versatile",
                                max_tokens=2000,
                                messages=[{"role": "user", "content": prompt}]
                            )
                            analysis = response.choices[0].message.content
                            log_activity(st.session_state.username,
                                         "Ran AI analysis")
                            st.markdown("#### 📝 AI Analysis Result")
                            st.markdown(analysis)
                            st.download_button("⬇️ Download Analysis",
                                               data=analysis,
                                               file_name="log_analysis.txt",
                                               mime="text/plain")
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")

            # ── Ask question ──
            st.markdown("### 💬 Ask a Question")
            question = st.text_input(
                "Example: Which application has the most errors?")
            if question and api_key:
                if st.button("Ask", type="secondary"):
                    with st.spinner("🔍 Searching memory..."):
                        rag_results = collection.query(
                            query_texts=[question], n_results=3)
                        rag_context = "\n".join(
                            [f"- {doc}"
                             for doc in rag_results['documents'][0]])

                    with st.spinner("🤖 Thinking..."):
                        try:
                            client = Groq(api_key=api_key)
                            response = client.chat.completions.create(
                                model="llama-3.3-70b-versatile",
                                max_tokens=1000,
                                messages=[{"role": "user",
                                           "content": f"""
Current data:
{filtered.head(max_rows).to_csv(index=False)}

Past incidents:
{rag_context}

Question: {question}"""}]
                            )
                            log_activity(st.session_state.username,
                                         f"Asked: {question}")
                            st.markdown(response.choices[0].message.content)
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
    else:
        st.info("👆 Upload your log file above to get started")

# ══════════════════════════════════════════
# MAIN ROUTER
# ══════════════════════════════════════════
if not st.session_state.logged_in:
    login_page()
elif st.session_state.role == "admin":
    page = st.sidebar.radio("Navigation",
                            ["📊 Analysis", "⚙️ Admin Panel"])
    if page == "⚙️ Admin Panel":
        admin_page()
    else:
        analysis_page()
else:
    analysis_page()