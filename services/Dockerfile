FROM ghcr.io/astral-sh/uv:latest AS uv

FROM python:3.14-slim

COPY --from=uv /uv /uvx /bin/

WORKDIR /app

COPY api/requirements.txt ./requirements.txt
RUN uv pip install --system -r requirements.txt

# py-readability-metrics usa nltk.sent_tokenize. Si el recurso no está, el
# evaluador de legibilidad cae a la fórmula Fernández-Huerta determinista.
RUN python -m nltk.downloader punkt_tab || true

COPY api/ .
COPY reporting /services/reporting
COPY __init__.py /services/__init__.py

ENV PYTHONPATH=/app:/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]