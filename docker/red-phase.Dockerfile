# Trusted red-phase test image. Build this before any model-generated code runs.
FROM python:3.12-slim
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONNOUSERSITE=1
COPY requirements.txt /tmp/genesis-requirements.txt
RUN python -m pip install --no-cache-dir -r /tmp/genesis-requirements.txt \
    && useradd --uid 10001 --create-home genesis
USER 10001:10001
WORKDIR /workspace
ENTRYPOINT ["python", "-B", "-m", "pytest"]
