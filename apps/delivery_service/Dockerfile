FROM python:3.14-alpine AS builder
WORKDIR /code
COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade --user -r /code/requirements.txt

FROM python:3.14-alpine
WORKDIR /code
COPY --from=builder /root/.local /root/.local
COPY app /code/app
ENV PATH=/root/.local/bin:$PATH

EXPOSE 8002
CMD ["fastapi", "run", "app/main.py", "--port", "8002"]