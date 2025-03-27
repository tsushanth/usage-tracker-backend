# Use lightweight base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install dependencies including Firestore
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app code
COPY . .

# Expose port for Cloud Run
EXPOSE 8080

# Set environment variable for Google credentials if needed (optional)
# ENV GOOGLE_APPLICATION_CREDENTIALS="/app/your-service-account.json"

# Run the FastAPI app with Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
