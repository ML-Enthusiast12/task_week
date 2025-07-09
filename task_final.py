import os
port = int(os.environ.get("PORT", 8080))
os.system(f"streamlit run task_final.py --server.port={port} --server.address=0.0.0.0")

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from dateutil import parser
import json

# Streamlit page configuration
st.set_page_config(page_title="Actions Dashboard", layout="wide")

# Hardcoded Monday.com API setup
API_TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJ0aWQiOjUzNjcxMTM2NCwiYWFpIjoxMSwidWlkIjo3ODEyNjAzOSwiaWFkIjoiMjAyNS0wNy0wOVQwNjoxMjoxMi4wMDBaIiwicGVyIjoibWU6d3JpdGUiLCJhY3RpZCI6Mjg1MTUzNDksInJnbiI6InVzZTEifQ.7xlG-veqLRWWL5RqmmJ5Ve4dxVlhnv0Z43CGktBnmp8"
BOARD_ID = "9148781915"  # Replace with your actual Monday.com Board ID
API_URL = "https://api.monday.com/v2"

# Headers for API requests
headers = {
    "Authorization": "Bearer " + API_TOKEN,
    "Content-Type": "application/json"
}

# Function to fetch data from Monday.com with pagination
@st.cache_data
def fetch_monday_data():
    if not API_TOKEN or not BOARD_ID or BOARD_ID == "YOUR_BOARD_ID_HERE":
        st.error("Please update the hardcoded API token and Board ID in the code with valid values.")
        return [], None
    
    all_items = []
    cursor = None
    
    while True:
        query = """
        query ($boardId: [ID!]!, $cursor: String) {
            boards(ids: $boardId) {
                id
                name
                columns {
                    id
                    title
                }
                items_page(limit: 500, cursor: $cursor) {
                    cursor
                    items {
                        id
                        name
                        created_at
                        column_values {
                            id
                            value
                        }
                    }
                }
            }
        }
        """
        
        variables = {"boardId": [BOARD_ID], "cursor": cursor}
        
        try:
            response = requests.post(API_URL, json={'query': query, 'variables': variables}, headers=headers)
            response.raise_for_status()
            data = response.json()
            if 'errors' in data:
                st.error(f"Monday.com API errors: {data['errors']}")
                return [], None
            board_data = data['data']['boards'][0] if data['data']['boards'] else None
            if not board_data:
                break
            
            items_page = board_data['items_page']
            all_items.extend(items_page['items'])
            cursor = items_page['cursor']
            
            if not cursor:
                break
        except requests.exceptions.RequestException as e:
            st.error(f"Error fetching data from Monday.com: {str(e)}")
            if hasattr(response, 'text') and response.text:
                st.error(f"Response details: {response.text}")
            return [], None
    
    # if board_data:
    #     st.write("Available Columns:", {col['title']: col['id'] for col in board_data['columns']})
    return all_items, board_data['columns'] if board_data else None

# Function to process Monday.com data
def process_data(items, columns):
    tasks = []
    column_map = {col['title']: col['id'] for col in columns}
    status_id = column_map.get("Status")
    create_date_id = column_map.get("Create Date")
    due_date_id = column_map.get("Due Date")
    
    if not status_id:
        st.warning("Could not find 'Status' column. Please check your board configuration.")
        return pd.DataFrame()
    if not create_date_id:
        st.warning("Could not find 'Create Date' column. Please check your board configuration.")
        return pd.DataFrame()
    if not due_date_id:
        st.warning("Could not find 'Due Date' column. Please check your board configuration.")
        return pd.DataFrame()
    
    for item in items:
        task = {
            'name': item['name'],
            'created_at': None,
            'status': None,
            'due_date': None
        }
        
        for column in item['column_values']:
            if column['id'] == status_id:
                if column['value']:
                    try:
                        status_data = json.loads(column['value'])
                        index_value = status_data.get('index')
                        if index_value is not None:
                            if isinstance(index_value, (int, str)):
                                status_map = {0: 'Done', 1: 'Outstanding', 2: 'Overdue'}
                                task['status'] = status_map.get(int(index_value), 'Overdue')
                            else:
                                task['status'] = str(index_value)
                        else:
                            task['status'] = status_data.get('label', status_data.get('text', 'Overdue'))
                    except json.JSONDecodeError:
                        task['status'] = 'Overdue'
            if column['id'] == create_date_id:
                if column['value']:
                    try:
                        date_data = json.loads(column['value'])
                        task['created_at'] = parser.parse(date_data.get('date', '')).date() if isinstance(date_data, dict) else parser.parse(column['value'].strip('"')).date()
                    except (json.JSONDecodeError, ValueError):
                        task['created_at'] = parser.parse(column['value'].strip('"')).date() if column['value'] else None
                else:
                    task['created_at'] = parser.parse(item['created_at']).date()
            if column['id'] == due_date_id:
                if column['value']:
                    try:
                        date_data = json.loads(column['value'])
                        task['due_date'] = parser.parse(date_data.get('date', '')).date() if isinstance(date_data, dict) else parser.parse(column['value'].strip('"')).date()
                    except (json.JSONDecodeError, ValueError):
                        task['due_date'] = parser.parse(column['value'].strip('"')).date() if column['value'] else None
        
        if task['created_at'] is None:
            task['created_at'] = parser.parse(item['created_at']).date()
        
        tasks.append(task)
    
    return pd.DataFrame(tasks)

# Function to prepare data for visualization
# Function to prepare data for visualization
def prepare_chart_data(df, start_date, end_date, filter_type, selected_values):
    # Ensure created_at is in Timestamp format
    df['created_at'] = pd.to_datetime(df['created_at'])
    
    # Filter by date range
    df = df[(df['created_at'] >= pd.Timestamp(start_date)) & (df['created_at'] <= pd.Timestamp(end_date))]
    
    if filter_type == "Week":
        weeks = pd.date_range(start=start_date, end=end_date, freq='W-MON')
        week_labels = [w.strftime('%Y-%m-%d') for w in weeks]
        # Filter tasks for selected weeks using Timestamp comparisons
        filtered_df = df[df['created_at'].apply(lambda x: any(
            x >= pd.Timestamp(w) and x <= pd.Timestamp(w) + timedelta(days=6) 
            for w in weeks if w.strftime('%Y-%m-%d') in selected_values
        ))]
    else:  # Month
        months = pd.date_range(start=start_date, end=end_date, freq='MS').strftime('%Y-%m').tolist()
        filtered_df = df[df['created_at'].dt.strftime('%Y-%m').isin(selected_values)] if selected_values != ["All"] else df
    
    # Initialize data structures
    outstanding = []
    done = []
    overdue = []
    net_outstanding = []
    
    if filter_type == "Week":
        for week in weeks:
            week_end = pd.Timestamp(week) + timedelta(days=6)
            week_tasks = filtered_df[(filtered_df['created_at'] >= pd.Timestamp(week)) & (filtered_df['created_at'] <= week_end)]
            week_outstanding = len(week_tasks[week_tasks['status'].isin(['Outstanding', 'Overdue'])])
            week_done = len(week_tasks[week_tasks['status'] == 'Done'])
            week_overdue = len(week_tasks[week_tasks['status'] == 'Overdue'])
            outstanding.append(week_outstanding)
            done.append(week_done)
            overdue.append(week_overdue)
            net_outstanding.append(week_outstanding - week_done)
    else:  # Month
        for month in selected_values if selected_values != ["All"] else months:
            month_df = filtered_df[filtered_df['created_at'].dt.strftime('%Y-%m') == month]
            month_outstanding = len(month_df[month_df['status'].isin(['Outstanding', 'Overdue'])])
            month_done = len(month_df[month_df['status'] == 'Done'])
            month_overdue = len(month_df[month_df['status'] == 'Overdue'])
            outstanding.append(month_outstanding)
            done.append(month_done)
            overdue.append(month_overdue)
            net_outstanding.append(month_outstanding - month_done)
        week_labels = selected_values if selected_values != ["All"] else months
    
    return week_labels, outstanding, done, overdue, net_outstanding
# Main dashboard
def main():
    st.title("Actions By Week Dashboard")
    
    # Date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("Start Date", value=datetime.now() - timedelta(weeks=8))
    with col2:
        end_date = st.date_input("End Date", value=datetime.now())
    
    # Filter type selection
    filter_type = st.radio("Filter by:", ["Week", "Month"])
    
    # Fetch and process data
    items, columns = fetch_monday_data()
    if items and columns:
        df = process_data(items, columns)
        
        if not df.empty:
            # Prepare filter options
            if filter_type == "Week":
                weeks = pd.date_range(start=start_date, end=end_date, freq='W-MON')
                week_options = [w.strftime('%Y-%m-%d') for w in weeks]
                selected_weeks = st.multiselect("Select Weeks:", week_options, default=week_options)
            else:  # Month
                months = pd.date_range(start=start_date, end=end_date, freq='MS').strftime('%Y-%m').tolist()
                selected_months = st.multiselect("Select Months:", ["All"] + months, default=["All"])
            
            # Prepare chart data
            week_labels, outstanding, done, overdue, net_outstanding = prepare_chart_data(df, start_date, end_date, filter_type, selected_weeks if filter_type == "Week" else selected_months)
            
            # Create stacked bar chart with lines
            fig = go.Figure()
            
            # Stacked bars
            fig.add_trace(go.Bar(
                x=week_labels,
                y=outstanding,
                name="Outstanding",
                marker_color='orange'
            ))
            fig.add_trace(go.Bar(
                x=week_labels,
                y=done,
                name="Done",
                marker_color='green'
            ))
            
            # Line A: Net Outstanding
            fig.add_trace(go.Scatter(
                x=week_labels,
                y=net_outstanding,
                name="Net Outstanding",
                line=dict(color='blue', width=2)
            ))
            
            # Line B: Overdue
            fig.add_trace(go.Scatter(
                x=week_labels,
                y=overdue,
                name="Overdue",
                line=dict(color='red', width=2)
            ))
            
            # Update layout
            fig.update_layout(
                title="Actions By Week/Month",
                xaxis_title="Week/Month Starting",
                yaxis_title="Number of Tasks",
                barmode='stack',
                template='plotly_white',
                height=600
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("No valid task data processed. Check column names or data.")
    else:
        st.warning("No data retrieved from Monday.com. Please check the hardcoded API token, Board ID, or column configuration.")

if __name__ == "__main__":
    main()


