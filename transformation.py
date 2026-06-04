import streamlit as st
import pandas as pd
from groq import Groq
import json
from datetime import datetime
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from supabase import create_client

# ── Supabase setup ──
@st.cache_resource
def init_supabase():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

# ── Simple Vector Search ──
class SimpleVectorStore:
    def __init__(self):
        self.documents = []
        self.vectorizer = TfidfVectorizer()
        self.matrix = None

    def add(self, documents):
        self.documents = documents
        self.matrix = self.vectorizer.fit_transform(documents)

    def query(self, query_text, n=5):
        if not self.documents:
            return []
        query_vec = self.vectorizer.transform([query_text])
        scores = cosine_similarity(query_vec, self.matrix)[0]
        top_indices = np.argsort(scores)[-n:][::-1]
        return [self.documents[i] for i in top_indices]

    def count(self):
        return len(self.documents)

# ── Database functions ──
def log_activity(supabase, username, action):
    try:
        supabase.table("activity_log").insert({
            "username": username,
            "action": action,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }).execute()
    except:
        pass

def get_all_users(supabase):
    try:
        result = supabase.table("users").select("id, username, role, created_at").execute()
        return result.data
    except:
        return []

def get_activity_log(supabase):
    try:
        result = supabase.table("activity_log").select("username, action, timestamp").order("timestamp", desc=True).limit(50).execute()
        return result.data
    except:
        return []

def create_user(supabase, username, password, role):
    try:
        supabase.table("users").insert({
            "username": username,
            "password": password,
            "role": role,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }).execute()
        return True
    except:
        return False

def delete_user(supabase, username):
    try:
        supabase.table("users").delete().eq("username", username).execute()
        return True
    except:
        return False

def verify_login(supabase, username, password):
    try:
        result = supabase.table("users").select("role").eq("username", username).eq("password", password).execute()
        if result.data:
            return result.data[0]["role"]
        return None
    except:
        return None

def ensure_admin(supabase):
    try:
        result = supabase.table("users").select("id").eq("username", "admin").execute()
        if not result.data:
            supabase.table("users").insert({
                "username": "admin",
                "password": "admin123",
                "role": "admin",
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }).execute()
    except:
        pass

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
            return pd.DataFrame({
                "message": lines,
                "severity": "INFO",
                "source": "txt",
                "application": "unknown",
                "error_code": "N/A",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "root_cause": "N/A",
                "recommendation": "N/A"
            })
    except Exception as e:
        st.error(f"❌ Error reading file: {str(e)}")
        return None

# ── Initialize ──
st.set_page_config(page_title="GenAI Log Intelligence",
                   page_icon="🔍", layout="wide")

supabase = init_supabase()
ensure_admin(supabase)

@st.cache_resource
def get_vector_store():
    return SimpleVectorStore()

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
                role = verify_login(supabase, username, password)
                if role:
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.session_state.role = role
                    log_activity(supabase, username, "Logged in")
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
        log_activity(supabase, st.session_state.username, "Logged out")
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.role = ""
        st.rerun()
    st.markdown("---")
    tab1, tab2, tab3 = st.tabs(["👥 Users", "➕ Create User", "📋 Activity Log"])

    with tab1:
        st.markdown("### All Users")
        users = get_all_users(supabase)
        if users:
            df_users = pd.DataFrame(users)
            st.dataframe(df_users, use_container_width=True)
            st.markdown("### Delete User")
            usernames = [u["username"] for u in users if u["username"] != "admin"]
            if usernames:
                user_to_delete = st.selectbox("Select user to delete", usernames)
                if st.button("🗑️ Delete User", type="primary"):
                    delete_user(supabase, user_to_delete)
                    log_activity(supabase, st.session_state.username, f"Deleted user: {user_to_delete}")
                    st.success(f"✅ User {user_to_delete} deleted!")
                    st.rerun()
            else:
                st.info("No users to delete")
        else:
            st.info("No users found")

    with tab2:
        st.markdown("### Create New User")
        new_username = st.text_input("New Username")
        new_password = st.text_input("New Password", type="password")
        new_role = st.selectbox("Role", ["user", "admin"])
        if st.button("➕ Create User", type="primary"):
            if new_username and new_password:
                success = create_user(supabase, new_username, new_password, new_role)
                if success:
                    log_activity(supabase, st.session_state.username, f"Created user: {new_username}")
                    st.success(f"✅ User {new_username} created!")
                else:
                    st.error("❌ Username already exists!")
            else:
                st.warning("⚠️ Please fill all fields")

    with tab3:
        st.markdown("### Recent Activity")
        activity = get_activity_log(supabase)
        if activity:
            df_activity = pd.DataFrame(activity)
            st.dataframe(df_activity, use_container_width=True)
        else:
            st.info("No activity yet")

# ══════════════════════════════════════════
# ANALYSIS PAGE
# ══════════════════════════════════════════
def analysis_page():
    st.title("🔍 GenAI Log Intelligence Assistant")
    st.caption(f"Logged in as: {st.session_state.username}")

    vector_store = get_vector_store()

    with st.sidebar:
        st.header("⚙️ Settings")
        api_key = st.text_input("Groq API Key", type="password")
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
        if vector_store.count() > 0:
            st.success(f"🧠 {vector_store.count()} incidents loaded")
        else:
            st.info("Upload a file to load RAG memory")
        st.markdown("---")
        if st.button("🚪 Logout"):
            log_activity(supabase, st.session_state.username, "Logged out")
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.session_state.role = ""
            st.rerun()

    st.markdown("### 📂 Upload Your Log File")
    st.caption("Supported: CSV, Excel (.xlsx, .xls), JSON, TXT")
    uploaded_file = st.file_uploader("Upload file",
                                     type=["csv", "xlsx", "xls", "json", "txt"])

    if uploaded_file:
        df = read_file(uploaded_file)
        if df is not None:
            log_activity(supabase, st.session_state.username,
                         f"Uploaded: {uploaded_file.name}")
            st.success(f"✅ Loaded {len(df):,} records from {uploaded_file.name}")

            if vector_store.count() == 0:
                with st.spinner("🧠 Loading into RAG memory..."):
                    documents = []
                    for idx, row in df.iterrows():
                        doc = (f"Error: {str(row.get('message',''))} | "
                               f"App: {str(row.get('application','unknown'))} | "
                               f"Source: {str(row.get('source','unknown'))} | "
                               f"Code: {str(row.get('error_code','N/A'))} | "
                               f"Root Cause: {str(row.get('root_cause','N/A'))} | "
                               f"Fix: {str(row.get('recommendation','N/A'))}")
                        documents.append(doc)
                    vector_store.add(documents)
                st.success(f"✅ RAG memory loaded — {vector_store.count()} incidents!")

            filtered = df.copy()
            if "severity" in df.columns and severity_filter:
                filtered = filtered[filtered["severity"].isin(severity_filter)]
            if "source" in df.columns and source_filter:
                filtered = filtered[filtered["source"].isin(source_filter)]

            st.markdown("### 📊 Quick Overview")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Records", len(df))
            col2.metric("Errors", len(df[df["severity"] == "ERROR"]) if "severity" in df.columns else "N/A")
            col3.metric("Critical", len(df[df["severity"] == "CRITICAL"]) if "severity" in df.columns else "N/A")
            col4.metric("After Filter", len(filtered))

            st.markdown("### 📋 Filtered Data")
            st.dataframe(filtered.head(max_rows), use_container_width=True)

            st.markdown("### 🤖 AI Analysis with RAG")
            if not api_key:
                st.warning("⚠️ Please enter your Groq API key in the sidebar.")
            else:
                if st.button("🚀 Analyze with AI + RAG", type="primary"):
                    sample = filtered.head(max_rows)
                    with st.spinner("🔍 Searching RAG memory..."):
                        query_text = " ".join([str(row.get("message", "")) for _, row in sample.iterrows()])
                        similar = vector_store.query(query_text, n=5)
                        similar_text = "\n".join([f"- {doc}" for doc in similar])

                    st.info(f"🧠 RAG found {len(similar)} similar past incidents")

                    log_text = ""
                    for _, row in sample.iterrows():
                        log_text += " | ".join([f"{col}: {row[col]}" for col in df.columns]) + "\n"

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
                            log_activity(supabase, st.session_state.username,
                                         "Ran AI analysis")
                            st.markdown("#### 📝 AI Analysis Result")
                            st.markdown(analysis)
                            st.download_button("⬇️ Download Analysis",
                                               data=analysis,
                                               file_name="log_analysis.txt",
                                               mime="text/plain")
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")

            st.markdown("### 💬 Ask a Question")
            question = st.text_input("Example: Which application has the most errors?")
            if question and api_key:
                if st.button("Ask", type="secondary"):
                    with st.spinner("🔍 Searching memory..."):
                        rag_context = "\n".join([f"- {doc}" for doc in vector_store.query(question, n=3)])
                    with st.spinner("🤖 Thinking..."):
                        try:
                            client = Groq(api_key=api_key)
                            response = client.chat.completions.create(
                                model="llama-3.3-70b-versatile",
                                max_tokens=1000,
                                messages=[{"role": "user", "content": f"""
Current data:
{filtered.head(max_rows).to_csv(index=False)}

Past incidents:
{rag_context}

Question: {question}"""}]
                            )
                            log_activity(supabase, st.session_state.username,
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
    page = st.sidebar.radio("Navigation", ["📊 Analysis", "⚙️ Admin Panel"])
    if page == "⚙️ Admin Panel":
        admin_page()
    else:
        analysis_page()
else:
    analysis_page()
