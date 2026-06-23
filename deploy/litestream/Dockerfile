# Variant image with Litestream baked in, for hosts without a persistent disk
# (e.g. Render free tier). Replicates the SQLite DB to S3/R2 continuously and
# restores it on cold start. Build from the repo root:
#
#   docker build -f deploy/litestream/Dockerfile -t ai-running-coach:litestream .
#
# Then set the LITESTREAM_* secrets (see deploy/litestream/litestream.yml).
FROM ai-running-coach:latest AS app

FROM app
USER root

# Install the Litestream binary (static, ~10 MB).
ARG LITESTREAM_VERSION=0.3.13
ADD https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-v${LITESTREAM_VERSION}-linux-amd64.tar.gz /tmp/litestream.tar.gz
RUN tar -C /usr/local/bin -xzf /tmp/litestream.tar.gz \
    && rm /tmp/litestream.tar.gz \
    && chmod +x /usr/local/bin/litestream

COPY deploy/litestream/litestream.yml /etc/litestream.yml
RUN chown appuser:appuser /etc/litestream.yml

USER appuser
ENTRYPOINT ["./docker-entrypoint.sh"]
