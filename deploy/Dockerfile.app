# App layer on top of the pinned runtime base.
FROM scipal-base:py312

# COPY merges into the base image; clean /app so deleted files do not linger.
RUN rm -rf /app && mkdir -p /app
WORKDIR /app

COPY . .
RUN pip install --no-cache-dir "psycopg-pool>=3.2" "gunicorn>=22.0"
RUN mkdir -p data documents documents_xml logs
COPY deploy/entrypoint.sh /usr/local/bin/scipal-entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/scipal-entrypoint.sh && chmod +x /usr/local/bin/scipal-entrypoint.sh

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=3)"

ENTRYPOINT ["/usr/local/bin/scipal-entrypoint.sh"]
