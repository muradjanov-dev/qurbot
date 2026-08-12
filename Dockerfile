# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder

WORKDIR /build
RUN pip install --no-cache-dir --upgrade pip

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir --prefix=/install .


FROM python:3.12-slim AS runtime

RUN groupadd --gid 1000 qurbot && \
    useradd --uid 1000 --gid qurbot --create-home --shell /usr/sbin/nologin qurbot

COPY --from=builder /install /usr/local

WORKDIR /app
COPY app ./app

USER qurbot

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
