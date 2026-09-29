bash´´´
mkdir -p ~/npm && cd ~/npm

cat > docker-compose.yml <<'EOF'
services:
  npm:
    image: jc21/nginx-proxy-manager:latest
    container_name: nginx_proxy_manager
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "81:81"
    volumes:
      - npm_data:/data
      - npm_letsencrypt:/etc/letsencrypt

volumes:
  npm_data:
  npm_letsencrypt:
EOF

docker compose up -d
docker compose ps
´´´
