# Use an official Python runtime as a base image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port Streamlit uses (default is 8501)
EXPOSE 8501

# Command to run the Streamlit app
CMD ["streamlit", "run", "task_final.py", "--server.port=8501", "--server.address=0.0.0.0"]