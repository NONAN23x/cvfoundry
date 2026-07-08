FROM ubuntu:24.04@sha256:4fbb8e6a8395de5a7550b33509421a2bafbc0aab6c06ba2cef9ebffbc7092d90

ENV DEBIAN_FRONTEND=noninteractive PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-uno libreoffice-writer poppler-utils fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY . /workspace
RUN chmod +x /workspace/jobs-tailor /workspace/assets/generate-resume.sh

ENTRYPOINT ["/workspace/jobs-tailor"]
