FROM python:3.11-slim

WORKDIR /app

# Copy requirements file with pinned versions
COPY backend/requirements.txt /app/requirements.txt

# Install dependencies from requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend /app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
