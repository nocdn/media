# -------- build stage --------
FROM oven/bun:1.1.13 AS builder

WORKDIR /app

# Copy sources & install deps
COPY . .
RUN bun install --frozen-lockfile

# Build production assets
RUN bun run build

# -------- runtime stage --------
FROM nginx:alpine AS runtime

# Replace default nginx site with our custom config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built static assets from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose HTTP port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"] 