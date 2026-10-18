# Animave render service — HyperFrames (Apache-2.0) + chrome-headless-shell + ffmpeg.
# Deployed as its own Railway service (root directory: render_service). It holds no
# secrets: the HTML it renders is model-written.
FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl unzip xz-utils ffmpeg \
    libgbm1 libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 libxdamage1 libxrandr2 \
    libcups2 libasound2 libpangocairo-1.0-0 libxshmfence1 libgtk-3-0 \
    fonts-liberation fonts-noto-color-emoji fonts-noto-cjk fonts-noto-core fonts-noto-extra \
    fonts-noto-ui-core fonts-freefont-ttf fonts-dejavu-core fontconfig \
    && rm -rf /var/lib/apt/lists/* && apt-get clean && fc-cache -fv

# Pinned chrome-headless-shell (deterministic BeginFrame capture), same as HyperFrames' own images.
RUN npx --yes @puppeteer/browsers install chrome-headless-shell@148.0.7778.167 --path /opt/puppeteer \
    && CHS="$(find /opt/puppeteer/chrome-headless-shell -name chrome-headless-shell -type f | head -n1)" \
    && mkdir -p /opt/chrome && ln -s "$CHS" /opt/chrome/chrome-headless-shell \
    && /opt/chrome/chrome-headless-shell --version

ENV HYPERFRAMES_CHROME_PATH=/opt/chrome/chrome-headless-shell \
    PRODUCER_HEADLESS_SHELL_PATH=/opt/chrome/chrome-headless-shell \
    PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    CONTAINER=true \
    DO_NOT_TRACK=1 \
    NODE_ENV=production

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY server.mjs ./

# Run as an unprivileged user.
RUN useradd -m -u 10001 render && mkdir -p /tmp/hf-home && chown -R render /tmp/hf-home
USER render

EXPOSE 8080
CMD ["node", "server.mjs"]
