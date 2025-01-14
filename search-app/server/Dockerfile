FROM python:3.11-slim

ENV ROOT_PATH="/"
ENV LOGURU_LEVEL="INFO"
ENV NUM_WORKERS=4

RUN apt-get update -y && apt-get install -y gcc

RUN pip install poetry==1.6.1
RUN poetry config virtualenvs.create false

WORKDIR /app

COPY ./pyproject.toml ./README.md ./poetry.lock* ./
COPY ./package[s] ./packages

RUN poetry install  --no-interaction --no-ansi --no-root

COPY ./ ./

RUN poetry install --no-interaction --no-ansi

EXPOSE 8080

CMD exec uvicorn app.server:app  \
  --host 0.0.0.0 --port 8080 \
  --workers $NUM_WORKERS --root-path $ROOT_PATH
