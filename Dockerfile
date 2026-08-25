# Same shape as mojimakrosi's image: editable install so PROJECT_ROOT=/app,
# start.sh migrates then serves on $PORT. Target: Railway.
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY alembic.ini serve.py start.sh ./
COPY alembic ./alembic

RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["./start.sh"]
