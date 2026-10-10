FROM python:3.14-slim AS builder
WORKDIR /code

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /bin/
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_PYTHON_DOWNLOADS=never

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-default-groups

FROM builder AS builder_tooling
RUN uv sync --locked --no-default-groups --group tooling

FROM python:3.14-slim AS runtime
RUN useradd --create-home --uid 1000 appuser
WORKDIR /code
COPY --from=builder /opt/venv /opt/venv
COPY app ./app
ENV PATH=/opt/venv/bin:$PATH

USER appuser
CMD ["python", "-m", "app.main"]

FROM runtime AS tooling
COPY --from=builder_tooling /opt/venv /opt/venv
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./

FROM runtime AS app
