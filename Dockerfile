FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure runtime data directory exists (Railway/Nixpacks volume mount target).
RUN mkdir -p /app/data

# Run the application
CMD ["python", "-m", "app.main"]
