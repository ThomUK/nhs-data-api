# API image: the code plus one month's data bundle (built by `nda bundle`). See docs/deploy.md.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_NO_CACHE=1
RUN pip install --no-cache-dir uv==0.5.4

WORKDIR /app
# Dependencies first, so the layer is reused when only code or data change
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY catalogue ./catalogue
RUN uv sync --frozen --no-dev

# Data last: it changes every release
COPY bundle ./data/processed

RUN useradd --system --uid 10001 --no-create-home api
USER api
ENV NDA_DATA_DIR=/app/data PATH=/app/.venv/bin:$PATH
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
# Only reachable through nginx on the host (port bound to 127.0.0.1), so trust its headers
CMD ["uvicorn", "nhs_data_api.api.app:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", "--forwarded-allow-ips", "*"]
