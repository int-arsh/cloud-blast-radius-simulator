# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm install --legacy-peer-deps

COPY . .
RUN npm run build

# Production serve stage using lightweight nginx
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Custom nginx configuration for SPA routing and API proxying
RUN echo 'server {' \
    '  listen 80;' \
    '  server_name localhost;' \
    '  location / {' \
    '    root /usr/share/nginx/html;' \
    '    index index.html;' \
    '    try_files $uri $uri/ /index.html;' \
    '  }' \
    '  location /api/ {' \
    '    proxy_pass http://backend:8000/api/;' \
    '    proxy_set_header Host $host;' \
    '    proxy_set_header X-Real-IP $remote_addr;' \
    '  }' \
    '}' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
