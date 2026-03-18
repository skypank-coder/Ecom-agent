# Use Microsoft Playwright official image
# This has ALL browser dependencies pre-installed
FROM mcr.microsoft.com/playwright/python:v1.58.0-jammy

# Set environment variables
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUTF8=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source code
COPY src/ ./src/
COPY templates/ ./templates/

# Expose port
EXPOSE 5000

# Run Flask app
CMD ["python", "src/app.py"]
