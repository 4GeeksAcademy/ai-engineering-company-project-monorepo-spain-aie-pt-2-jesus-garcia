FROM ghcr.io/astral-sh/uv:latest AS uv

FROM python:3.14-slim

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

COPY api/requirements.txt ./requirements.txt
RUN uv pip install --system -r requirements.txt

COPY api/ .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]