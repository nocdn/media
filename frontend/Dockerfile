# -------- runtime stage --------
FROM nginx:alpine AS runtime

# Replace default nginx site with our custom config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy pre-built static assets (build locally to avoid Docker esbuild conflicts)
COPY dist /usr/share/nginx/html

# Expose HTTP port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]