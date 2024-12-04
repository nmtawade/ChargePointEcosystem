# Use the official Python image from the Docker Hub
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

COPY . /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
# COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy project
# COPY . .

# Expose the port the app runs on
EXPOSE 8080

# Command to run the app with gunicorn
#CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]

CMD ["python", "app.py"]
