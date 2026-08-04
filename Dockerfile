FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY esgagents ./esgagents
COPY skills ./skills
COPY template_v1 ./template_v1

ARG ESG_BUILD_GIT_SHA=unknown

RUN python -m pip install --no-cache-dir . \
    && python -m esgagents.provenance build \
        --root /app \
        --output /app/build_provenance.json \
        --git-sha "$ESG_BUILD_GIT_SHA" \
    && mkdir -p /app/data/outputs /app/data/cache /app/data/inputs

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "esgagents.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
