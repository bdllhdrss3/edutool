FROM python:3.11-slim

WORKDIR /app
# OpenCV's wheel needs these runtime libraries; no Poppler/Tesseract executables are used.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
	&& rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY . .

EXPOSE 8000
CMD ["sh", "-c", "python -m alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
