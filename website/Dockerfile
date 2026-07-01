FROM node:22-alpine AS builder

LABEL stage=builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci && npm cache clean --force
COPY . .
RUN npm run build

FROM nginx:stable-alpine

LABEL org.opencontainers.image.title="AI Cost Analyzer - Frontend"
LABEL org.opencontainers.image.description="Frontend for AI Cost Analyzer"
LABEL org.opencontainers.image.source="https://github.com/anomalyco/Ai-cost-analyzer"

RUN rm -rf /usr/share/nginx/html/* \
    && mkdir -p /var/cache/nginx /tmp/nginx \
    && chown -R 101:101 /var/cache/nginx /tmp/nginx

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-main.conf /etc/nginx/nginx.conf
COPY --from=builder /app/dist/ /usr/share/nginx/html/

USER 101

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
