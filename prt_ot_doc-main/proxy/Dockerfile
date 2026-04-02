FROM nginx:1.25-alpine
COPY proxy/nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q -O - http://localhost/healthz || exit 1
CMD ["nginx", "-g", "daemon off;"]
