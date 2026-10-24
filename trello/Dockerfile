# SDKs exist only in the disposable builder; credentials are supplied at runtime.
FROM rust:1.99.1-alpine3.24@sha256:b1d5dd5a22a09404d3e798c0cf051b689077360374eb505fa5bb93c479693d87 AS rust-sdk

FROM python:3.15.1-alpine3.24@sha256:54448f67d7c31c39e5cdd3ea2d6382395ce142806c284425f8e897d78a0465b3 AS native-sdk
RUN apk upgrade --no-cache && apk add --no-cache build-base linux-headers bluez-dev perl pkgconf libffi-dev openssl
COPY --from=rust-sdk /usr/local/rustup /usr/local/rustup
COPY --from=rust-sdk /usr/local/cargo /usr/local/cargo
ENV RUSTUP_HOME=/usr/local/rustup CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH OPENSSL_DIR=/opt/mcphub-native OPENSSL_NO_VENDOR=1 OPENSSL_STATIC=0 \
    RUSTFLAGS="-C link-arg=-Wl,-rpath,/opt/mcphub-native/lib" CARGO_BUILD_JOBS=2 \
    MATURIN_NO_INSTALL_RUST=1 MATURIN_PEP517_ARGS="--locked --compatibility linux --auditwheel skip"
WORKDIR /native-build
COPY native-client-runtime.json ./
COPY scripts/build_native_runtime.py scripts/build_python_tls.py ./scripts/
RUN MCPHUB_DISPOSABLE_BUILD_SDK=1 python scripts/build_native_runtime.py \
    && MCPHUB_DISPOSABLE_BUILD_SDK=1 python scripts/build_python_tls.py

FROM native-sdk AS dependencies
COPY requirements-native-build.lock requirements-image.lock ./
COPY scripts/lock_built_wheels.py ./scripts/
RUN pip install --no-cache-dir --only-binary=:all: --require-hashes -r requirements-native-build.lock \
    && pip wheel --no-cache-dir --no-deps --no-build-isolation --require-hashes \
      --no-binary=cryptography --wheel-dir /wheelhouse -r requirements-image.lock \
    && python -I scripts/lock_built_wheels.py

FROM python:3.15.1-alpine3.24@sha256:54448f67d7c31c39e5cdd3ea2d6382395ce142806c284425f8e897d78a0465b3
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8 \
    USE_CLAUDE_APP=true TRELLO_READ_ONLY=true TRELLO_MCP_DB_PATH=/data/trello_cache.db \
    VIRTUAL_ENV=/app/.venv PATH=/app/.venv/bin:$PATH HOME=/home/trello
RUN apk upgrade --no-cache
COPY --from=native-sdk /native-output /tmp/mcphub-native
RUN apk --keys-dir /tmp/mcphub-native/keys --no-network add \
      /tmp/mcphub-native/mcphub-openssl.apk /tmp/mcphub-native/mcphub-sqlite.apk \
    && rm -rf /tmp/mcphub-native
COPY --from=native-sdk /python-tls-runtime/lib-dynload/ /usr/local/lib/python3.15/lib-dynload/
COPY --from=native-sdk /python-tls-runtime/provenance.json /python-tls-runtime/CPython-LICENSE /usr/share/doc/mcphub-python-tls/
WORKDIR /app/trello
COPY --from=dependencies /wheelhouse /tmp/mcphub-wheelhouse
RUN /usr/local/bin/python -m venv --without-pip /app/.venv \
    && /usr/local/bin/python -m pip --python /app/.venv/bin/python install --no-cache-dir --no-index \
      --find-links=/tmp/mcphub-wheelhouse --require-hashes -r /tmp/mcphub-wheelhouse/installed.lock \
    && /usr/local/bin/python -m pip --python /app/.venv/bin/python check \
    && mkdir -p /usr/share/doc/mcphub-wheels \
    && cp /tmp/mcphub-wheelhouse/installed.lock /tmp/mcphub-wheelhouse/build-wheels.json \
      /tmp/mcphub-wheelhouse/build-toolchain.json /usr/share/doc/mcphub-wheels/ \
    && rm -rf /tmp/mcphub-wheelhouse \
    && /usr/local/bin/python -m pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.15/ensurepip
COPY . .
RUN addgroup -S -g 10001 trello && adduser -S -D -u 10001 -G trello trello \
    && mkdir -p /data && chown 10001:10001 /data
USER 10001:10001
CMD ["python", "main.py"]
