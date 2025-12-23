# SaveSmart – MVP Prototype (Streamlit)
# -------------------------------------------------------------
# ฟีเจอร์หลัก:
# - ตั้งค่าโปรไฟล์รายได้ (รายวัน/สัปดาห์/เดือน/ปี), ชั่วโมงทำงาน/วัน, วันทำงาน/สัปดาห์/เดือน
# - เพิ่มรายการที่อยากซื้อ: ชื่อ, ราคา, หมวด, ความจำเป็น (1-5), emoji หรือ อัปโหลดรูป, กำหนดวันเป้าหมาย (optional)
# - คำนวณชั่วโมงที่ต้องทำงาน (hours_needed), เทียบเป็นวันทำงาน, % ของรายได้ต่อเดือน
# - สร้างแผนเก็บเงิน (คำนวณยอดที่ต้องเก็บต่อสัปดาห์/เดือนจาก target_date)
# - บันทึกยอดออมจริง (manual deposit) + progress bar ต่อรายเป้าหมาย
# - Snooze/เตือน (บันทึก reminder และแจ้งเตือนในแอปเมื่อครบกำหนด)
# - จัดลำดับความสำคัญด้วย priority_score และ badge Cheap/Moderate/Expensive
# - ส่งออก CSV (goals, savings)
# -------------------------------------------------------------

import os
import io
import math
import sqlite3
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List

import pandas as pd
import streamlit as st

# -----------------------------
# PATHS & CONSTANTS
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "savesmart.db")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

APP_TITLE = "SaveSmart – ชั่วโมงงานแลกของที่อยากได้"
CURRENCY_DEFAULT = "THB"

# -----------------------------
# DB UTILITIES
# -----------------------------

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # โปรไฟล์ผู้ใช้ (MVP ใช้ผู้ใช้เดียว id = 1)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            currency TEXT,
            income_amount REAL,
            income_period TEXT,   -- daily/weekly/monthly/yearly
            hours_per_day REAL,
            work_days_per_week REAL,
            work_days_per_month REAL,
            fixed_expenses REAL,
            created_at TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            title TEXT,
            price REAL,
            emoji TEXT,
            image_path TEXT,
            category TEXT,
            necessity INTEGER,          -- 1..5
            created_at TEXT,
            target_date TEXT,
            status TEXT DEFAULT 'active' -- active, snoozed, achieved, deleted
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS savings (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            goal_id INTEGER,
            amount REAL,
            note TEXT,
            ts TEXT
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            goal_id INTEGER,
            remind_at TEXT,
            recurring TEXT,   -- none/daily/weekly/monthly
            enabled INTEGER
        )
        """
    )

    # สร้างโปรไฟล์ default หากยังไม่มี
    cur.execute("SELECT COUNT(*) AS c FROM users")
    if cur.fetchone()["c"] == 0:
        cur.execute(
            """
            INSERT INTO users (id, username, currency, income_amount, income_period, hours_per_day, work_days_per_week, work_days_per_month, fixed_expenses, created_at)
            VALUES (1, 'you', ?, 10005.0, 'monthly', 10.0, 5.0, 22.0, 0.0, ?)
            """,
            (CURRENCY_DEFAULT, datetime.utcnow().isoformat()),
        )

    conn.commit()
    conn.close()


# -----------------------------
# PROFILE / CALC FUNCTIONS
# -----------------------------

def get_user() -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    return row


def update_user(**kwargs):
    conn = get_conn()
    cur = conn.cursor()
    sets = []
    vals = []
    for k, v in kwargs.items():
        sets.append(f"{k} = ?")
        vals.append(v)
    vals.append(1)
    cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = ?", vals)
    conn.commit()
    conn.close()


def hourly_rate(user: Dict[str, Any]) -> Optional[float]:
    """คำนวณอัตรารายได้ต่อชั่วโมงจากโปรไฟล์ผู้ใช้"""
    if not user:
        return None
    amt = user.get("income_amount") or 0
    period = (user.get("income_period") or "").lower()
    hpd = user.get("hours_per_day") or 8
    wdpw = user.get("work_days_per_week") or 5
    wdpm = user.get("work_days_per_month") or 22

    try:
        if period == "daily":
            total_hours = hpd
        elif period == "weekly":
            total_hours = hpd * wdpw
        elif period == "monthly":
            total_hours = hpd * wdpm
        elif period == "yearly":
            total_hours = hpd * wdpw * 52
        else:
            return None
        if total_hours <= 0:
            return None
        return float(amt) / float(total_hours)
    except Exception:
        return None


def calc_hours_needed(price: float, hr: float) -> float:
    if hr is None or hr <= 0:
        return float("nan")
    return price / hr


def calc_days_needed(hours_needed: float, hours_per_day: float) -> float:
    if hours_per_day <= 0:
        return float("nan")
    return hours_needed / hours_per_day


def percent_of_monthly_income(price: float, user: Dict[str, Any]) -> Optional[float]:
    amt = user.get("income_amount") or 0
    period = (user.get("income_period") or "").lower()
    # แปลงรายได้ให้เป็นรายเดือนเพื่อคำนวณ %
    if period == "monthly":
        monthly = amt
    elif period == "weekly":
        monthly = amt * 52 / 12
    elif period == "daily":
        monthly = amt * (user.get("work_days_per_month") or 22)
    elif period == "yearly":
        monthly = amt / 12
    else:
        return None
    if monthly <= 0:
        return None
    return price / monthly * 100.0


def priority_score(necessity: int, hours_needed: float) -> float:
    # ยิ่งจำเป็นสูง และชั่วโมงที่ต้องใช้ต่ำ → คะแนนสูง
    necessity = max(1, min(int(necessity or 1), 5))
    if math.isnan(hours_needed) or hours_needed < 0:
        return 0.0
    score = necessity * (1.0 / (1.0 + hours_needed)) * 100.0
    return round(score, 2)


def affordability_badge(hours_needed: float) -> str:
    try:
        if hours_needed <= 8:
            return "Cheap"
        elif hours_needed <= 40:
            return "Moderate"
        else:
            return "Expensive"
    except Exception:
        return "Unknown"


def savings_plan(price: float, target_date: Optional[date]) -> Dict[str, Any]:
    if not target_date:
        return {"has_plan": False}
    today = date.today()
    days = (target_date - today).days
    if days <= 0:
        return {"has_plan": False}
    monthly_needed = price / (days / 30.0)
    weekly_needed = price / (days / 7.0)
    return {
        "has_plan": True,
        "days_until": days,
        "monthly_needed": monthly_needed,
        "weekly_needed": weekly_needed,
    }


# -----------------------------
# GOALS / SAVINGS / REMINDERS CRUD
# -----------------------------

def add_goal(user_id: int, title: str, price: float, emoji: str, image_path: str,
             category: str, necessity: int, target_date: Optional[date]):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO goals (user_id, title, price, emoji, image_path, category, necessity, created_at, target_date, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """,
        (
            user_id, title, float(price or 0), (emoji or ""), (image_path or ""),
            (category or "Other"), int(necessity or 1), datetime.utcnow().isoformat(),
            target_date.isoformat() if target_date else None,
        ),
    )
    conn.commit()
    conn.close()


def update_goal_status(goal_id: int, status: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE goals SET status = ? WHERE id = ?", (status, goal_id))
    conn.commit()
    conn.close()


def delete_goal(goal_id: int):
    update_goal_status(goal_id, "deleted")


def get_goals(user_id: int, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    if status_filter and status_filter != "all":
        cur.execute("SELECT * FROM goals WHERE user_id = ? AND status = ? ORDER BY id DESC", (user_id, status_filter))
    else:
        cur.execute("SELECT * FROM goals WHERE user_id = ? AND status != 'deleted' ORDER BY id DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def savings_total(goal_id: int) -> float:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(amount), 0) AS s FROM savings WHERE goal_id = ?", (goal_id,))
    s = cur.fetchone()["s"] or 0.0
    conn.close()
    return float(s)


def add_saving(user_id: int, goal_id: int, amount: float, note: str = ""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO savings (user_id, goal_id, amount, note, ts) VALUES (?, ?, ?, ?, ?)",
        (user_id, goal_id, float(amount or 0), note or "", datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def set_reminder(user_id: int, goal_id: int, remind_at: datetime, recurring: str = "none", enabled: int = 1):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reminders (user_id, goal_id, remind_at, recurring, enabled) VALUES (?, ?, ?, ?, ?)",
        (user_id, goal_id, remind_at.isoformat(), recurring, int(enabled)),
    )
    conn.commit()
    conn.close()


def snooze_reminder(reminder_id: int, delta_days: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
    r = cur.fetchone()
    if r:
        new_time = datetime.fromisoformat(r["remind_at"]) + timedelta(days=delta_days)
        cur.execute("UPDATE reminders SET remind_at = ?, enabled = 1 WHERE id = ?", (new_time.isoformat(), reminder_id))
        conn.commit()
    conn.close()


def due_reminders(user_id: int) -> List[Dict[str, Any]]:
    now_iso = datetime.utcnow().isoformat()
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT r.*, g.title AS goal_title FROM reminders r JOIN goals g ON r.goal_id = g.id WHERE r.user_id = ? AND r.enabled = 1 AND r.remind_at <= ?",
        (user_id, now_iso),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def disable_reminder(reminder_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE reminders SET enabled = 0 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()


# -----------------------------
# HELPERS / EXPORTS
# -----------------------------

def save_uploaded_image(uploaded_file) -> Optional[str]:
    if not uploaded_file:
        return None
    filename = f"{int(datetime.utcnow().timestamp())}_{uploaded_file.name}"
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


def export_table_csv(query: str, params: tuple = ()) -> bytes:
    conn = get_conn()
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df.to_csv(index=False).encode("utf-8-sig")


# -----------------------------
# STREAMLIT UI
# -----------------------------

st.set_page_config(page_title=APP_TITLE, page_icon="⏱️", layout="wide")
st.title(APP_TITLE)

# Init DB
init_db()
USER_ID = 1
user = get_user()

# Top-level notification check (in-app)
for r in due_reminders(USER_ID):
    with st.chat_message("assistant"):
        st.markdown(f"**🔔 เตือนเป้าหมาย:** `{r['goal_title']}` ถึงกำหนดพิจารณาแล้ว")
        cols = st.columns(3)
        with cols[0]:
            if st.button("ดูรายการ", key=f"see_{r['id']}"):
                st.session_state["focus_goal_id"] = r["goal_id"]
        with cols[1]:
            if st.button("Snooze 7 วัน", key=f"s7_{r['id']}"):
                snooze_reminder(r["id"], 7)
                st.rerun()
        with cols[2]:
            if st.button("ปิดการเตือนนี้", key=f"dis_{r['id']}"):
                disable_reminder(r["id"])
                st.rerun()

# Sidebar – Profile Settings
with st.sidebar:
    st.header("โปรไฟล์รายได้ / การทำงาน")
    with st.form("profile_form"):
        colA, colB = st.columns(2)
        with colA:
            currency = st.text_input("สกุลเงิน", value=user.get("currency") or CURRENCY_DEFAULT)
            income_period = st.selectbox("รอบรายได้", ["daily", "weekly", "monthly", "yearly"], index=["daily","weekly","monthly","yearly"].index(user.get("income_period") or "monthly"))
            income_amount = st.number_input("จำนวนรายได้ต่อรอบ", min_value=0.0, value=float(user.get("income_amount") or 0.0), step=100.0)
        with colB:
            hours_per_day = st.number_input("ชั่วโมงทำงานต่อวัน", min_value=0.0, value=float(user.get("hours_per_day") or 8.0), step=0.5)
            work_days_per_week = st.number_input("วันทำงาน/สัปดาห์", min_value=0.0, value=float(user.get("work_days_per_week") or 5.0), step=0.5)
            work_days_per_month = st.number_input("วันทำงาน/เดือน", min_value=0.0, value=float(user.get("work_days_per_month") or 22.0), step=0.5)
        fixed_expenses = st.number_input("ค่าใช้จ่ายคงที่ต่อเดือน (ถ้ามี)", min_value=0.0, value=float(user.get("fixed_expenses") or 0.0), step=100.0)
        submitted = st.form_submit_button("บันทึกโปรไฟล์")
    if submitted:
        update_user(
            currency=currency,
            income_period=income_period,
            income_amount=income_amount,
            hours_per_day=hours_per_day,
            work_days_per_week=work_days_per_week,
            work_days_per_month=work_days_per_month,
            fixed_expenses=fixed_expenses,
        )
        st.success("บันทึกแล้ว ✅")
        st.rerun()

    # Show hourly rate quick view
    hr = hourly_rate(get_user())
    st.markdown("---")
    st.subheader("อัตรารายได้ต่อชั่วโมง")
    if hr:
        st.metric("ประมาณการ (ต่อชั่วโมง)", f"{hr:,.2f} {user.get('currency') or CURRENCY_DEFAULT}")
    else:
        st.info("กรอกโปรไฟล์ให้ครบเพื่อคำนวณอัตราต่อชั่วโมง")

    st.markdown("---")
    st.subheader("นำออกข้อมูล (CSV)")
    goals_csv = export_table_csv("SELECT * FROM goals WHERE status != 'deleted' AND user_id = ?", (USER_ID,))
    st.download_button("Export Goals CSV", data=goals_csv, file_name="goals.csv", mime="text/csv")
    savings_csv = export_table_csv("SELECT * FROM savings WHERE user_id = ?", (USER_ID,))
    st.download_button("Export Savings CSV", data=savings_csv, file_name="savings.csv", mime="text/csv")

# Dashboard quick stats
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.caption("รายได้/รอบ")
    st.metric("Income", f"{(user.get('income_amount') or 0):,.0f} {user.get('currency') or CURRENCY_DEFAULT}")
with col2:
    st.caption("ชั่วโมง/วัน")
    st.metric("Hours/Day", f"{(user.get('hours_per_day') or 0):.1f}")
with col3:
    st.caption("วัน/เดือน")
    st.metric("Work days/mo", f"{(user.get('work_days_per_month') or 0):.1f}")
with col4:
    st.caption("อัตราต่อชั่วโมง")
    st.metric("Hourly rate", f"{(hr or 0):,.2f} {user.get('currency') or CURRENCY_DEFAULT}")

st.markdown("---")

# Quick Add Goal
st.subheader("➕ เพิ่มรายการที่อยากได้ (ไว)")
with st.form("quick_add", clear_on_submit=True):
    c1, c2, c3 = st.columns([2,1,1])
    with c1:
        title = st.text_input("ชื่อสินค้า/เป้าหมาย", placeholder="เช่น AirPods Pro, รองเท้าวิ่ง…")
        category = st.selectbox("หมวด", ["Electronics","Shoes","Gadget","Furniture","Home","Vehicle","Kitchen","Photography","Education","Accessories","Other"], index=0)
    with c2:
        price = st.number_input("ราคา", min_value=0.0, step=10.0)
        necessity = st.slider("ความจำเป็น", 1, 5, 3)
    with c3:
        emoji = st.text_input("Emoji (ใส่ได้ถ้าไม่อัปโหลดรูป)", value="")
        image_file = st.file_uploader("อัปโหลดรูป (optional)", type=["png","jpg","jpeg","webp"], accept_multiple_files=False)
    tcol1, tcol2 = st.columns(2)
    with tcol1:
        target = st.date_input("กำหนดวันเป้าหมาย (optional)", value=None, format="YYYY-MM-DD")
    with tcol2:
        st.caption("กดคำนวณเพื่อดูชั่วโมงที่ต้องใช้ก่อนบันทึกก็ได้")
        calc_btn = st.form_submit_button("คำนวณอย่างเดียว")
        add_btn = st.form_submit_button("เพิ่มรายการนี้ ✅")

    img_path = None
    if image_file is not None:
        img_path = save_uploaded_image(image_file)

    if calc_btn and hr and price:
        hn = calc_hours_needed(price, hr)
        dn = calc_days_needed(hn, user.get("hours_per_day") or 8)
        st.info(f"ต้องใช้ ~ {hn:.1f} ชม. (≈ {dn:.1f} วันงาน)")

    if add_btn:
        if not title or (not emoji and not img_path):
            st.error("กรอกชื่อ และใส่ emoji หรืออัปโหลดรูป อย่างน้อยหนึ่งอย่าง")
        else:
            add_goal(USER_ID, title, price, emoji, img_path, category, necessity, target if isinstance(target, date) else None)
            st.success("เพิ่มรายการแล้ว ✅")
            st.rerun()

st.markdown("---")

# Goals List & Controls
st.subheader("🎯 รายการเป้าหมายของฉัน")
filter_col1, filter_col2, filter_col3 = st.columns(3)
with filter_col1:
    status_filter = st.selectbox("สถานะ", ["all","active","snoozed","achieved"], index=0)
with filter_col2:
    sort_by = st.selectbox("เรียงโดย", ["ล่าสุด","priority สูง→ต่ำ","ชั่วโมงน้อย→มาก","ราคา น้อย→มาก","% ของรายได้ สูง→ต่ำ"], index=0)
with filter_col3:
    show_details_default = st.checkbox("แสดงรายละเอียดเชิงลึก", value=True)

goals = get_goals(USER_ID, status_filter=None if status_filter == "all" else status_filter)

# prepare enriched rows
rows = []
for g in goals:
    h = hourly_rate(user)
    hn = calc_hours_needed(g["price"], h) if h else float("nan")
    dn = calc_days_needed(hn, user.get("hours_per_day") or 8) if h else float("nan")
    pct = percent_of_monthly_income(g["price"], user)
    badge = affordability_badge(hn) if not math.isnan(hn) else "Unknown"
    score = priority_score(g.get("necessity") or 1, hn)
    saved = savings_total(g["id"]) if g["status"] != "deleted" else 0.0
    progress = min(1.0, (saved / g["price"]) if g["price"] else 0.0)

    rows.append({
        **g,
        "hourly_rate": h,
        "hours_needed": hn,
        "days_needed": dn,
        "%_of_month": pct,
        "badge": badge,
        "priority": score,
        "saved": saved,
        "progress": progress,
    })

# sorting
if sort_by == "priority สูง→ต่ำ":
    rows.sort(key=lambda x: (x["priority"] or 0), reverse=True)
elif sort_by == "ชั่วโมงน้อย→มาก":
    rows.sort(key=lambda x: (x["hours_needed"] or float('inf')))
elif sort_by == "ราคา น้อย→มาก":
    rows.sort(key=lambda x: (x["price"] or float('inf')))
elif sort_by == "% ของรายได้ สูง→ต่ำ":
    rows.sort(key=lambda x: (x["%_of_month"] or 0), reverse=True)
else:
    # ล่าสุด
    rows.sort(key=lambda x: x["id"], reverse=True)

# render cards
if not rows:
    st.info("ยังไม่มีรายการ ลองเพิ่มรายการแรกได้ด้านบน ⤴")

for r in rows:
    with st.container(border=True):
        top_cols = st.columns([0.7, 2.2, 1.1, 1.1, 1.2])
        # image / emoji
        with top_cols[0]:
            if r.get("image_path") and os.path.exists(r["image_path"]):
                st.image(r["image_path"], caption=r.get("emoji") or "", use_container_width=True)
            else:
                st.markdown(f"<div style='font-size:48px; line-height:1.0'>{r.get('emoji') or '🛒'}</div>", unsafe_allow_html=True)
        with top_cols[1]:
            st.markdown(f"**{r['title']}**  ")
            st.caption(f"หมวด: {r.get('category') or 'Other'} | ความจำเป็น: {r.get('necessity')}/5 | สร้างเมื่อ: {r.get('created_at')[:10]}")
            if r.get("target_date"):
                st.caption(f"เป้าหมายภายใน: {r['target_date']}")
        with top_cols[2]:
            st.metric("ราคา", f"{r['price']:,.0f} {user.get('currency') or CURRENCY_DEFAULT}")
        with top_cols[3]:
            if not math.isnan(r['hours_needed']):
                st.metric("ชั่วโมงที่ต้องใช้", f"{r['hours_needed']:.1f} ชม.")
            else:
                st.metric("ชั่วโมงที่ต้องใช้", "-")
        with top_cols[4]:
            badge_text = r.get("badge") or "-"
            st.metric("ความคุ้มค่า", badge_text)

        # progress
        st.progress(r["progress"], text=f"ออมแล้ว {r['saved']:,.0f}/{r['price']:,.0f} ({r['progress']*100:.1f}%)")

        if show_details_default:
            with st.expander("รายละเอียดเชิงลึก & ตัวช่วยตัดสินใจ"):
                d1, d2, d3, d4 = st.columns(4)
                with d1:
                    if not math.isnan(r['days_needed']):
                        st.metric("เทียบเป็นวันงาน", f"{r['days_needed']:.1f} วัน")
                    else:
                        st.metric("เทียบเป็นวันงาน", "-")
                with d2:
                    pct = r.get("%_of_month")
                    st.metric("% ของรายได้/เดือน", f"{pct:.1f}%" if pct else "-")
                with d3:
                    st.metric("priority score", f"{r['priority']:.1f}")
                with d4:
                    plan = savings_plan(r["price"], date.fromisoformat(r["target_date"]) if r.get("target_date") else None)
                    if plan.get("has_plan"):
                        st.metric("ต้องเก็บ/เดือน", f"{plan['monthly_needed']:,.0f}")
                    else:
                        st.metric("ต้องเก็บ/เดือน", "-")

                # actions
                ac1, ac2, ac3, ac4, ac5 = st.columns(5)
                with ac1:
                    if st.button("ซื้อเลย (Mark Achieved)", key=f"buy_{r['id']}"):
                        update_goal_status(r["id"], "achieved")
                        st.success("บันทึกเป็น Achieved แล้ว")
                        st.rerun()
                with ac2:
                    if st.button("เริ่มแผนออม", key=f"plan_{r['id']}"):
                        # ตั้งเตือนรายสัปดาห์เริ่มจากพรุ่งนี้
                        set_reminder(USER_ID, r["id"], datetime.utcnow() + timedelta(days=7), recurring="weekly", enabled=1)
                        st.toast("ตั้งเตือนรายสัปดาห์แล้ว ✅")
                with ac3:
                    if st.button("Snooze 10 วัน", key=f"sn10_{r['id']}"):
                        set_reminder(USER_ID, r["id"], datetime.utcnow() + timedelta(days=10), recurring="none", enabled=1)
                        update_goal_status(r["id"], "snoozed")
                        st.toast("เลื่อนไปอีก 10 วัน")
                with ac4:
                    if st.button("ลบรายการ", key=f"del_{r['id']}"):
                        delete_goal(r["id"])
                        st.warning("ลบแล้ว (เก็บในฐานข้อมูลเป็น deleted)")
                        st.rerun()
                with ac5:
                    st.write("")

                st.markdown("**บันทึกยอดออม (Manual Deposit)**")
                with st.form(f"dep_{r['id']}", clear_on_submit=True):
                    dep_col1, dep_col2 = st.columns([1,2])
                    with dep_col1:
                        dep_amt = st.number_input("จำนวนเงิน", min_value=0.0, step=50.0, key=f"amt_{r['id']}")
                    with dep_col2:
                        dep_note = st.text_input("หมายเหตุ", key=f"note_{r['id']}", placeholder="เช่น โอนเข้าบัญชีออม…")
                    dep_submit = st.form_submit_button("บันทึกการออม")
                if dep_submit:
                    if dep_amt and dep_amt > 0:
                        add_saving(USER_ID, r["id"], dep_amt, dep_note)
                        st.success("บันทึกยอดออมแล้ว ✅")
                        st.rerun()
                    else:
                        st.error("กรอกจำนวนเงินมากกว่า 0")

        # Quick chips
        chip1, chip2, chip3 = st.columns(3)
        with chip1:
            st.caption("คำแนะนำ: ถ้าเก็บได้ 500/เดือน จะถึงใน ~ {:.1f} เดือน".format((r['price'] - r['saved'])/500 if (r['price']-r['saved'])>0 else 0))
        with chip2:
            if r.get("%_of_month") and r["%_of_month"] > 30:
                st.warning("⚠️ เกิน 30% ของรายได้/เดือน ควรพิจารณา")
            else:
                st.info("🙂 ระดับปลอดภัยสำหรับกระแสเงินสด")
        with chip3:
            st.caption("Badge: {}".format(r.get("badge") or "-"))

# Footer
st.markdown("---")
st.caption("© SaveSmart MVP – สร้างเพื่อทดลองแนวคิดการตัดสินใจซื้อด้วยการแปลงราคาเป็นชั่วโมงงาน | โปรดสำรองข้อมูลก่อนลบรายการ | สำหรับทดสอบเท่านั้น")
