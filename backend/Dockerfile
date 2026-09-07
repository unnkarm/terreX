FROM python:3.11-slim

# GDAL/rasterio system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin libgdal-dev libpq-dev gcc g++ \
    && rm -rf /var/lib/apt/lists/*

ENV GDAL_VERSION=3.6.2
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
ARG INSTALL_ML=false
COPY requirements-ml.txt .
RUN if [ "$INSTALL_ML" = "true" ]; then pip install --no-cache-dir -r requirements-ml.txt; fi

COPY . .

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
