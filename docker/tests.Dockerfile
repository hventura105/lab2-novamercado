FROM python:3.12.12-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /workspace
COPY api/requirements.txt /workspace/api/requirements.txt
COPY requirements-test.txt /workspace/requirements-test.txt
RUN pip install --no-cache-dir -r requirements-test.txt && useradd --uid 10001 --create-home tester && chown 10001:10001 /workspace
COPY --chown=10001:10001 . /workspace
RUN mkdir -p /workspace/data/entrada /workspace/evidence/private && chown -R 10001:10001 /workspace/data /workspace/evidence
USER 10001:10001
CMD ["python", "-m", "pytest", "-m", "unit", "-p", "no:cacheprovider", "--junitxml=/workspace/evidence/private/pytest.xml"]
