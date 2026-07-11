FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90
COPY --from=ghcr.io/astral-sh/uv:0.11.27 /uv /uvx /bin/

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/usr/lib/python3/dist-packages \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/tmp/cvfoundry-venv

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-uno libreoffice-writer poppler-utils fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY . /workspace
RUN chmod +x /workspace/jobs-tailor \
    && uv sync --frozen

ARG CVFOUNDRY_SOURCE_SHA256=unknown
LABEL org.opencontainers.image.revision="${CVFOUNDRY_SOURCE_SHA256}"

ENTRYPOINT ["/tmp/cvfoundry-venv/bin/jobs-tailor"]
