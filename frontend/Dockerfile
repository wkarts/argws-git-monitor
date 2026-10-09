ARG NODE_BASE=node:24-alpine
ARG NGINX_BASE=nginx:1.27-alpine
FROM ${NODE_BASE} AS build

WORKDIR /app

ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY package.json ./
RUN npm install --no-audit --no-fund

COPY . .
RUN npm run build

FROM ${NGINX_BASE} AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
RUN nginx -t
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O - http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1
