FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY company/backend/requirements.txt /app/requirements.txt

# Copy offline wheels from repo root
COPY docs/offline/wheels /wheels

# Offline install only
RUN python -m pip install --upgrade pip==24.2
RUN pip install --no-cache-dir --no-index --find-links /wheels -r /app/requirements.txt


# Copy backend source
COPY company/backend/app /app/app
COPY company/backend/alembic /app/alembic
COPY company/backend/alembic.ini /app/alembic.ini

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
