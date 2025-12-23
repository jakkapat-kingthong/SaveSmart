import os
import io
import math
import sqlite3
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List

import pandas as pd
import streamlit as st


# -----------------------------
# APP CONFIG
# -----------------------------
APP_TITLE = "SaveSmart – Convert Work Hours into Smart Purchases"
CURRENCY_DEFAULT = "THB"

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="⏱️",
    layout="wide",
)
# -----------------------------
# THEME STATE (DEFAULT: DARK)
# -----------------------------
if "theme" not in st.session_state:
    st.session_state["theme"] = "dark"


# -----------------------------
# PATHS & STORAGE
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "savesmart.db")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
# -----------------------------
# DB UTILITIES
# -----------------------------
def dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            currency TEXT,
            income_amount REAL,
            income_period TEXT,
            hours_per_day REAL,
            work_days_per_week REAL,
            work_days_per_month REAL,
            fixed_expenses REAL,
            created_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            title TEXT,
            price REAL,
            emoji TEXT,
            image_path TEXT,
            category TEXT,
            necessity INTEGER,
            created_at TEXT,
            target_date TEXT,
            status TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS savings (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            goal_id INTEGER,
            amount REAL,
            note TEXT,
            ts TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            goal_id INTEGER,
            remind_at TEXT,
            recurring TEXT,
            enabled INTEGER
        )
    """)

    cur.execute("SELECT COUNT(*) AS c FROM users")
    if cur.fetchone()["c"] == 0:
        cur.execute("""
            INSERT INTO users VALUES
            (1, 'you', ?, 20000, 'monthly', 8, 5, 22, 0, ?)
        """, (CURRENCY_DEFAULT, datetime.utcnow().isoformat()))

    conn.commit()
    conn.close()
# -----------------------------
# PROFILE & CALCULATIONS
# -----------------------------
def get_user():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id=1")
    user = cur.fetchone()
    conn.close()
    return user


def hourly_rate(user):
    if not user:
        return None
    income = user["income_amount"]
    hpd = user["hours_per_day"]
    wdpm = user["work_days_per_month"]
    if hpd <= 0 or wdpm <= 0:
        return None
    return income / (hpd * wdpm)


def calc_hours_needed(price, hr):
    if not hr or hr <= 0:
        return float("nan")
    return price / hr


def calc_days_needed(hours, hours_per_day):
    if hours_per_day <= 0:
        return float("nan")
    return hours / hours_per_day


def percent_of_monthly_income(price, user):
    monthly = user["income_amount"]
    if monthly <= 0:
        return None
    return price / monthly * 100


def affordability_badge(hours):
    if hours <= 8:
        return "Cheap"
    elif hours <= 40:
        return "Moderate"
    return "Expensive"


# -----------------------------
# DECISION EXPLANATION ENGINE
# -----------------------------
def purchase_decision_explanation(hours_needed, percent_monthly, necessity):
    reasons = []

    if hours_needed <= 8:
        effort = "low"
        reasons.append("It requires only a small amount of working time.")
    elif hours_needed <= 40:
        effort = "medium"
        reasons.append("It requires a moderate amount of working time.")
    else:
        effort = "high"
        reasons.append("It requires a significant amount of working time.")

    if percent_monthly is not None:
        if percent_monthly <= 15:
            finance = "low"
            reasons.append("The cost represents a small portion of your monthly income.")
        elif percent_monthly <= 30:
            finance = "medium"
            reasons.append("The cost represents a noticeable portion of your monthly income.")
        else:
            finance = "high"
            reasons.append("The cost represents a large portion of your monthly income.")
    else:
        finance = "unknown"

    if necessity >= 4:
        need = "high"
        reasons.append("You marked this item as highly necessary.")
    elif necessity == 3:
        need = "medium"
        reasons.append("You marked this item as moderately necessary.")
    else:
        need = "low"
        reasons.append("You marked this item as low necessity.")

    if effort == "low" and finance == "low" and need == "high":
        rec = "Buy Now"
        summary = "This purchase has a low impact and aligns well with your priorities."
    elif effort == "high" or finance == "high":
        if need == "low":
            rec = "Not Recommended"
            summary = "This purchase has a high opportunity cost and is not essential."
        else:
            rec = "Consider Delaying"
            summary = "This purchase may be important, but delaying could reduce pressure."
    else:
        rec = "Consider Delaying"
        summary = "This purchase is feasible, but waiting may improve balance."

    return {
        "recommendation": rec,
        "explanation": summary + " " + " ".join(reasons)
    }
# -----------------------------
# CRUD OPERATIONS
# -----------------------------
def add_goal(title, price, emoji, category, necessity, target_date):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO goals
        (user_id, title, price, emoji, category, necessity, created_at, target_date, status)
        VALUES (1,?,?,?,?,?,?,?, 'active')
    """, (
        title, price, emoji, category, necessity,
        datetime.utcnow().isoformat(),
        target_date.isoformat() if target_date else None
    ))
    conn.commit()
    conn.close()


def get_goals():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM goals WHERE status != 'deleted'")
    rows = cur.fetchall()
    conn.close()
    return rows
# -----------------------------
# STREAMLIT UI
# -----------------------------
init_db()
user = get_user()
hr = hourly_rate(user)

st.title(APP_TITLE)

# Dark mode styles
if st.session_state["theme"] == "dark":
    st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #e6e6e6; }
    </style>
    """, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Appearance")
    theme = st.radio("Theme", ["Dark", "Light"], index=0)
    st.session_state["theme"] = theme.lower()

    st.markdown("### Income Profile")
    income = st.number_input("Monthly Income", value=user["income_amount"])
    hours = st.number_input("Hours per Day", value=user["hours_per_day"])
    days = st.number_input("Work Days per Month", value=user["work_days_per_month"])

st.metric("Hourly Rate", f"{hr:,.2f} THB")

st.markdown("## ➕ Add Goal")
with st.form("add_goal"):
    title = st.text_input("Item / Goal Name")
    price = st.number_input("Price", min_value=0.0)
    emoji = st.text_input("Emoji", value="🛒")
    category = st.selectbox("Category", ["Electronics", "Lifestyle", "Other"])
    necessity = st.slider("Necessity Level", 1, 5, 3)
    target = st.date_input("Target Date", value=None)
    submit = st.form_submit_button("Add Goal")

if submit:
    add_goal(title, price, emoji, category, necessity, target)
    st.success("Goal added")
    st.rerun()

st.markdown("## 🎯 Your Goals")
for g in get_goals():
    hours = calc_hours_needed(g["price"], hr)
    pct = percent_of_monthly_income(g["price"], user)

    with st.container(border=True):
        st.markdown(f"### {g['emoji']} {g['title']}")
        st.write(f"Price: {g['price']:,.0f} THB")
        st.write(f"Hours needed: {hours:.1f}")
        decision = purchase_decision_explanation(hours, pct, g["necessity"])
        st.info(f"**{decision['recommendation']}** — {decision['explanation']}")
