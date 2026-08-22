FROM python:3.12-slim-bookworm

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/* \
    && JAVA_HOME_DIR="$(dirname "$(dirname "$(readlink -f "$(command -v java)")")")" \
    && ln -sfn "$JAVA_HOME_DIR" /usr/lib/jvm/jre

ENV JAVA_HOME=/usr/lib/jvm/jre
ENV PATH="${JAVA_HOME}/bin:${PATH}"
ENV AUTH_MODE=disabled
ENV DATA_DIR=/data
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir . \
    && mkdir -p /data

VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
