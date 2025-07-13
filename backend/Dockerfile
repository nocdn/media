FROM python:3.12-slim

# Install system dependencies required for video processing
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies first (leverages Docker layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Expose backend port
EXPOSE 9420

# Run FastAPI with hot-reload disabled (prod)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9420"] 