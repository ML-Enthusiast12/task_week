import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# -------------------- CONFIGURATION --------------------
API_KEY = "eyJhbGciOiJIUzI1NiJ9.eyJ0aWQiOjUzNjcxMTM2NCwiYWFpIjoxMSwidWlkIjo3ODEyNjAzOSwiaWFkIjoiMjAyNS0wNy0wOVQwNjoxMjoxMi4wMDBaIiwicGVyIjoibWU6d3JpdGUiLCJhY3RpZCI6Mjg1MTUzNDksInJnbiI6InVzZTEifQ.7xlG-veqLRWWL5RqmmJ5Ve4dxVlhnv0Z43CGktBnmp8"
BOARD_ID = "9148781915"
STATUS_COLUMN_ID = "color_mkqyyxxc"
DUE_DATE_COLUMN_ID = "date_mkqyf70p"
CREATE_DATE_COLUMN_ID = "date_mkqyvac7"
DONE_STATUSES = ["Done"]

# -------------------- MONDAY API FETCH --------------------
def fetch_monday_data():
    all_items = []
    cursor = None
    while True:
        cursor_part = f', cursor: "{cursor}"' if cursor else ""
        query = f"""
        {{
          boards(ids: [{BOARD_ID}]) {{
            items_page(limit: 100{cursor_part}) {{
              cursor
              items {{
                name
                column_values(ids: ["{STATUS_COLUMN_ID}", "{DUE_DATE_COLUMN_ID}", "{CREATE_DATE_COLUMN_ID}"]) {{
                  id
                  text
                }}
              }}
            }}
          }}
        }}
        """
        headers = {"Authorization": API_KEY}
        response = requests.post("https://api.monday.com/v2", json={"query": query}, headers=headers, timeout=30)
        if response.status_code != 200:
            st.error(f"❌ API request failed: {response.status_code}")
            st.write("Debug: API response:", response.text)
            return {}
        json_data = response.json()
        if "errors" in json_data:
            st.error("❌ Monday API errors:")
            st.json(json_data["errors"])
            return {}
        items = json_data["data"]["boards"][0]["items_page"]["items"]
        all_items.extend(items)
        cursor = json_data["data"]["boards"][0]["items_page"].get("cursor")
        if not cursor:
            break
    return {"data": {"boards": [{"items_page": {"items": all_items}}]}}

# -------------------- DATA CLEANING --------------------
def process_data(raw_data):
    if "data" not in raw_data or not raw_data["data"]["boards"][0]["items_page"]["items"]:
        st.warning("⚠️ No valid data found.")
        return pd.DataFrame()
    tasks = []
    for item in raw_data["data"]["boards"][0]["items_page"]["items"]:
        task = {"name": item.get("name", "Unknown"), "create_date": None, "status": None, "due_date": None}
        for col in item.get("column_values", []):
            if col.get("id") == STATUS_COLUMN_ID:
                task["status"] = col.get("text", "Unknown")
            elif col.get("id") == DUE_DATE_COLUMN_ID:
                task["due_date"] = col.get("text", "")
            elif col.get("id") == CREATE_DATE_COLUMN_ID:
                task["create_date"] = col.get("text", "")
        tasks.append(task)
    df = pd.DataFrame(tasks)
    df["create_date"] = pd.to_datetime(df["create_date"], errors="coerce", utc=True)
    df["due_date"] = pd.to_datetime(df["due_date"], errors="coerce", utc=True)
    return df

# -------------------- METRIC CALCULATION --------------------
def calculate_metrics(df):
    today = pd.Timestamp(datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0), tz='UTC')
    past_30_days = today - timedelta(days=30)
    past_15_days = today - timedelta(days=15)
    df = df[df["create_date"] >= past_30_days]
    df_current = df[df["create_date"] >= past_15_days]
    df_prev = df[(df["create_date"] < past_15_days) & (df["create_date"] >= past_30_days)]

    current_velocity = df_current[df_current["status"].isin(DONE_STATUSES)].shape[0]
    prev_velocity = df_prev[df_prev["status"].isin(DONE_STATUSES)].shape[0]
    velocity_delta = calc_delta(prev_velocity, current_velocity)

    overdue_current = df_current[(df_current["due_date"] < today) & (~df_current["status"].isin(DONE_STATUSES))].shape[0]
    overdue_prev = df_prev[(df_prev["due_date"] < past_15_days) & (~df_prev["status"].isin(DONE_STATUSES))].shape[0]
    overdue_delta = calc_delta(overdue_prev, overdue_current)

    st.write(f"Debug: Current Velocity={current_velocity}, Prev Velocity={prev_velocity}")
    st.write(f"Debug: Current Overdue={overdue_current}, Prev Overdue={overdue_prev}")

    # Return prev overdue to use in coloring logic
    return current_velocity, velocity_delta, overdue_current, overdue_delta, overdue_prev

def calc_delta(previous, current):
    if previous == 0:
        return 100 if current > 0 else 0
    return round(((current - previous) / previous) * 100, 2)

# -------------------- STREAMLIT UI --------------------
def main():
    st.set_page_config(layout="wide")
    st.title("📊 Team Performance Dashboard (Last 30 Days)")
    st.markdown("""
    **Color Coding:**
    - **Velocity**: Green if % change is positive (more tasks completed), Red if negative.
    - **Overdue**: Red if overdue increased, Green if overdue decreased or no change.
    """)
    with st.spinner("Fetching data from Monday.com..."):
        raw_data = fetch_monday_data()
        df = process_data(raw_data)
        if df.empty:
            st.warning("No data to show.")
            return
        v_now, v_delta, o_now, o_delta, o_prev = calculate_metrics(df)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            """
            <div style="border: 2px solid black; padding: 10px;">
                <h3 style="text-align: center;">✅ Velocity (Completed Tasks)</h3>
                <p style="text-align: center; font-size: 24px;">{}</p>
                <p style="text-align: center; font-size: 18px; color: {};">{}%</p>
            </div>
            """.format(v_now, "green" if v_delta >= 0 else "red", v_delta),
            unsafe_allow_html=True
        )
    with col2:
        # Correct overdue coloring logic:
        if o_now > o_prev:
            overdue_color = "red"
        else:
            overdue_color = "green"
        st.markdown(
            """
            <div style="border: 2px solid black; padding: 10px;">
                <h3 style="text-align: center;">❌ Overdue Tasks</h3>
                <p style="text-align: center; font-size: 24px;">{}</p>
                <p style="text-align: center; font-size: 18px; color: {};">{}%</p>
            </div>
            """.format(o_now, overdue_color, o_delta),
            unsafe_allow_html=True
        )
    with st.expander("📋 Task Data"):
        st.dataframe(df)

if __name__ == "__main__":
    main()
