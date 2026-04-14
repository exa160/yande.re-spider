FROM python:3.12-slim

WORKDIR /app

RUN pip install uv

COPY pyproject.toml .
RUN uv sync --no-dev

COPY backend/ ./backend/
COPY api/ ./api/
COPY frontend/dist/ ./frontend/dist/
COPY config/ ./config/

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
