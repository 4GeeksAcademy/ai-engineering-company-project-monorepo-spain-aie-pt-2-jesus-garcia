FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY trackflow_mcp ./trackflow_mcp

EXPOSE 8001

CMD ["uvicorn", "trackflow_mcp.server:app", "--host", "0.0.0.0", "--port", "8001"]
