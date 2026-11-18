# IPMG in a container: the CLI, IPMG Web, and the ping it needs.
#
# With no arguments it starts IPMG Web; the link, with its access token, is in
# the container's log:
#
#   docker run -d --name ipmg -p 127.0.0.1:8080:8080 -v ipmg-data:/data sameeralam3127/ipmg
#   docker logs ipmg
#
# With arguments it is the CLI, and the scan lands in the same history:
#
#   docker run --rm -v ipmg-data:/data sameeralam3127/ipmg --input 10.0.0.0/24
#
# Also published as ghcr.io/sameeralam3127/ipmg, the same image.
#
# Everything a scan writes (reports and the history database) goes to /data,
# so mount a volume there to keep it. See compose.yaml for IPMG Web.

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------- build
# Wheels are built in their own stage so the final image carries no compiler,
# pip cache, or source tree.
FROM python:${PYTHON_VERSION}-slim AS build

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
# With the web extra, so the image runs IPMG Web as well as the CLI.
RUN pip wheel --no-cache-dir --wheel-dir /wheels ".[web]"

# ---------------------------------------------------------------- runtime
FROM python:${PYTHON_VERSION}-slim

LABEL org.opencontainers.image.title="ipmg" \
      org.opencontainers.image.description="IP Management & Ping Monitoring: parallel ping sweeps, scan history, change detection, and IPMG Web" \
      org.opencontainers.image.source="https://github.com/sameeralam3127/ipmg" \
      org.opencontainers.image.licenses="MIT"

# ping, used without any added capability: the container runtime's
# unprivileged ICMP sockets (net.ipv4.ping_group_range, on by default in
# Docker and containerd) let the non-root user send echo requests. Giving ping
# a file capability instead would break it wherever NET_RAW is dropped, as in
# Kubernetes' restricted profile: the kernel refuses to run such a binary.
RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels "ipmg[web]" && rm -rf /wheels

# A fixed, unprivileged user. HOME=/data puts the history database at
# /data/.ipmg/dashboard.db, next to the reports, so one volume keeps both.
RUN useradd --uid 10001 --home-dir /data --create-home --shell /usr/sbin/nologin ipmg
USER 10001
WORKDIR /data
ENV HOME=/data \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]

EXPOSE 8080

# Arguments replace CMD, so "docker run IMAGE --input ..." runs a scan, and
# "docker run IMAGE --help" prints the help. With none, IPMG Web starts. It
# must listen on 0.0.0.0 inside the container or the published port reaches
# nothing; which host interfaces see it is decided by -p. Set IPMG_WEB_TOKEN
# to keep the link the same across restarts.
ENTRYPOINT ["ipmg"]
CMD ["web", "--host", "0.0.0.0", "--no-browser"]
