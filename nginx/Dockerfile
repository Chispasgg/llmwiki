FROM alpine:latest
RUN apk add --no-cache nginx && \
    mkdir -p /run/nginx && \
    rm -f /etc/nginx/http.d/default.conf
COPY default.conf /etc/nginx/http.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
