FROM python:3.11-slim

ARG ROOT_PATH="/"
ENV LOGURU_LEVEL="INFO"
ENV WORKER=4

RUN pip install poetry==1.6.1

RUN poetry config virtualenvs.create false

WORKDIR /app

COPY ./pyproject.toml ./README.md ./poetry.lock* ./

COPY ./package[s] ./packages

RUN poetry install  --no-interaction --no-ansi --no-root

COPY ./ ./

RUN poetry install --no-interaction --no-ansi

EXPOSE 8080

CMD exec uvicorn app.server:app --workers $WORKER --host 0.0.0.0 --port 8080 --root-path $ROOT_PATH
