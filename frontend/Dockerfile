# ── Stage 1: build React app ──────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci --prefer-offline

COPY . .
RUN npm run build

# ── Stage 2: serve with nginx + reverse proxy to API ─────────────────────────
FROM nginx:1.27-alpine

RUN rm /etc/nginx/conf.d/default.conf

COPY --from=builder /app/dist /usr/share/nginx/html
# nginx.conf is passed in via the build context root (docker-compose sets context: .)
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
