# Deploy

Local build:

```bash
docker compose build
docker compose up -d
```

VPS layout:

```text
/opt/hermess
  .env
  docker-compose.yml
  Dockerfile
  hermess_agent/
  new_miner_skill/
  docs.md
```

Server commands:

```bash
cd /opt/hermess
docker compose up -d --build
docker compose logs -f hermess
```

