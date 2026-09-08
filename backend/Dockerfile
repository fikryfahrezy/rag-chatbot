FROM python:3.13.15-slim-bookworm
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
COPY app ./app
RUN uv sync --frozen --no-dev --no-editable
RUN mkdir -p /data/uploads
EXPOSE 8000
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
