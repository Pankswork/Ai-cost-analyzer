FROM node:22-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:stable-alpine

RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf \
    && mkdir -p /var/cache/nginx /tmp/nginx \
    && chown -R 101:101 /var/cache/nginx /tmp/nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-main.conf /etc/nginx/nginx.conf
COPY --from=builder /app/dist/ /usr/share/nginx/html/

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
