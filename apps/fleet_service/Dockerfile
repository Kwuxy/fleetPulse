FROM python:3.14-slim AS builder
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade --user -r /code/requirements.txt

FROM python:3.14-slim
WORKDIR /code
COPY --from=builder /root/.local /root/.local
COPY app /code/app
COPY migrations /code/migrations
COPY alembic.ini /code/alembic.ini
ENV PATH=/root/.local/bin:$PATH

EXPOSE 8001
CMD ["fastapi", "run", "app/main.py", "--port", "8001"]