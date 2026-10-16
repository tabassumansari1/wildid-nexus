FROM python:3.12-slim

# Install system dependencies for OpenCV and video handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy Django project files
COPY . /app/

# Production environment variables
ENV DJANGO_DEBUG=0 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Collect static files into staticfiles/
RUN python manage.py collectstatic --noinput

# Ensure media upload and report directories exist
RUN mkdir -p /app/media/uploads /app/media/reports

EXPOSE 8000

# Apply migrations and launch Gunicorn with generous timeout for video processing
CMD python manage.py migrate && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 120
