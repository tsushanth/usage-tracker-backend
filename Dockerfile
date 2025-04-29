# Use lightweight Python base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy dependency file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files including API key, main.py, etc.
COPY . .

# Set environment variable for GCP credentials
# Copy credentials and set environment variable
COPY summarizerproxy-799529fee5b2.json /app/summarizerproxy-799529fee5b2.json
ENV GOOGLE_APPLICATION_CREDENTIALS="/app/summarizerproxy-799529fee5b2.json"

# Expose FastAPI port
EXPOSE 8080

# Run the FastAPI app with Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
