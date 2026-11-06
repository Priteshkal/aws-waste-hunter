FROM python:3.13-slim

# Hash-pinned dependencies first, then the package itself without resolving anything.
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes --no-deps -r requirements.lock
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps . && useradd --create-home scanner

USER scanner
# Credentials come from the environment or a mounted ~/.aws; nothing is baked into the image.
ENTRYPOINT ["aws-waste-hunter"]
