# Plotra Platform - Production Deployment Guide

## Quick Start

### 1. Configure Environment Variables

Copy `.env.example` to `.env` and update the values:

```bash
cp .env.example .env
```

### 2. Build and Start Services

```bash
docker-compose -f docker-compose.yml up -d --build
```

### 3. Verify Deployment

- Frontend: http://188.166.28.64
- API: http://188.166.28.64:8000/api/v2
- Health: http://188.166.28.64:8000/health

## Services

- **PostgreSQL**: Port 5432 (internal)
- **Backend API**: Port 8000 (exposed)
- **Dashboard (Nginx)**: Port 80 (exposed)

## Maintenance

### View logs
```bash
docker-compose logs -f backend
```

### Restart services
```bash
docker-compose restart backend
```

### Update deployment
```bash
git pull
docker-compose up -d --build
```

## CORS Configuration

The CORS origins are configured in `backend/config.yaml`:
- http://188.166.28.64
- http://188.166.28.64:8080
- http://188.166.28.64:8000
- http://plotra.eu
- http://plotra.eu:8080
- https://plotra.eu
- https://api.plotra.eu
- https://dev.plotra.eu
- http://mail.plotra.eu
- https://mail.plotra.eu
- http://localhost:3000
- http://localhost:8080
- http://127.0.0.1:8080
- http://localhost:8081