# App layer on top of the pinned runtime base.
FROM scipal-base:py312

WORKDIR /app

COPY . .
RUN pip install --no-cache-dir "psycopg-pool>=3.2"
RUN mkdir -p data documents documents_xml logs

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=3)"

CMD ["python", "api_server.py"]
