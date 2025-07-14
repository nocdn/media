# -------- build stage --------
FROM oven/bun:1.1.13 AS builder

WORKDIR /app

# copying manifests and config first to leverage Docker cache.
# copy vite.config.js because the build script depends on it.
COPY package.json bun.lock vite.config.js ./
RUN bun install --frozen-lockfile

# Copy the rest of the source files
COPY . .

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