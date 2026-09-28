#!/bin/bash
# Instala Docker Engine + Docker Compose + Buildx en Amazon Linux 2023.
# Úsalo como "User data" al lanzar cada EC2 (se ejecuta solo al arrancar)
# o córrelo a mano con: sudo bash install-docker.sh
set -e
dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user

PLUGINS=/usr/local/lib/docker/cli-plugins
mkdir -p $PLUGINS
curl -fsSL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 -o $PLUGINS/docker-compose
BUILDX=$(curl -fsSL https://api.github.com/repos/docker/buildx/releases/latest | grep '"tag_name"' | cut -d'"' -f4)
curl -fsSL "https://github.com/docker/buildx/releases/download/${BUILDX}/buildx-${BUILDX}.linux-amd64" -o $PLUGINS/docker-buildx
chmod +x $PLUGINS/docker-compose $PLUGINS/docker-buildx
