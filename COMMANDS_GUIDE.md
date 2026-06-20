# OpenAQ ML Production Project - Commands Guide

A comprehensive guide to common commands and use cases for developing and managing the OpenAQ ML production environment.

---

## Table of Contents

1. [Docker Compose Commands](#docker-compose-commands)
2. [API Commands](#api-commands)
3. [Development Workflows](#development-workflows)
4. [Access Services](#access-services)
5. [Troubleshooting](#troubleshooting)
6. [Environment Variables](#environment-variables)

---

## Docker Compose Commands

### Start All Services

```bash
docker compose up -d
```

**Use case**: Start the entire stack (API, Database, Airflow, Webapp, pgAdmin) in background mode.

**Includes**:
- PostgreSQL Database
- FastAPI (Uvicorn)
- Airflow (Scheduler, DAG Processor, API Server)
- Streamlit Webapp
- pgAdmin

---

### Start Specific Services

```bash
# Start only API
docker compose up -d api

# Start only Database
docker compose up -d db

# Start only Airflow
docker compose up -d airflow-scheduler

# Start only Webapp
docker compose up -d webapp
```

**Use case**: When you only need specific services without running the full stack.

---

### Rebuild Images (Fix Missing Dependencies)

```bash
docker compose up --build -d
```

**Use case**: When you've updated `requirements.txt` or Dockerfiles. This forces Docker to rebuild images instead of using cached layers.

**⚠️ Important**: Always use `--build` when dependencies change!

---

### View Logs

```bash
# All services
docker compose logs

# Specific service
docker compose logs api
docker compose logs db
docker compose logs airflow-scheduler

# Last 50 lines
docker compose logs api --tail=50

# Follow logs in real-time
docker compose logs -f api

# Timestamp included
docker compose logs -t api
```

**Use case**: Debugging issues, monitoring startup, checking for errors.

---

### Check Running Containers

```bash
docker compose ps
```

**Output columns**:
- `STATUS`: Running, Exited, Waiting, or Healthy
- `PORTS`: Exposed ports (e.g., 0.0.0.0:8000->8000/tcp)

---

### Stop Services

```bash
# Stop all services (keeps data)
docker compose stop

# Stop specific service
docker compose stop api

# Stop and remove containers
docker compose down

# Stop, remove containers, and delete volumes
docker compose down -v
```

**Use case**: 
- `stop`: Temporary pause without losing data
- `down`: Clean shutdown
- `down -v`: Full cleanup (careful - deletes database data!)

---

### Clean Up Docker

```bash
# Remove unused containers, images, networks
docker compose down
docker system prune -f

# Full cleanup (includes dangling images)
docker system prune -a --volumes -f
```

**Use case**: Free up disk space, resolve corrupted Docker state, fix caching issues.

---

## API Commands

### Run API Locally (Without Docker)

```bash
# Activate virtual environment
source /home/malo/home/AIS2/openaq-ml-production-project/.venv/bin/activate

# Navigate to API directory
cd /home/malo/home/AIS2/openaq-ml-production-project/api

# Run with auto-reload (development)
uvicorn main:app --reload

# Run without reload (production)
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Options**:
- `--reload`: Auto-restart when files change (dev only)
- `--host 0.0.0.0`: Listen on all network interfaces
- `--port 8000`: Specify port (default: 8000)
- `--workers 4`: Use multiple workers (production)

**Use case**: Local development, testing changes quickly without Docker overhead.

---

### Test API Health

```bash
# Simple health check
curl http://localhost:8000/health

# Database health check
curl http://localhost:8000/health/db

# Pretty print response
curl -s http://localhost:8000/health | jq .
```

**Use case**: Verify API is responding and connected to database.

---

## Development Workflows

### Setting Up Local Development

```bash
# 1. Navigate to project
cd /home/malo/home/AIS2/openaq-ml-production-project

# 2. Create/activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -r api/requirements.txt
pip install -r airflow/requirements.txt

# 4. Load environment variables
export $(cat .env | xargs)

# 5. Start database only
docker compose up -d db

# 6. Run API locally
cd api && uvicorn main:app --reload
```

---

### After Changing requirements.txt

```bash
# Option 1: Rebuild Docker image
docker compose down
docker compose up --build -d

# Option 2: Update local development environment
pip install -r api/requirements.txt
```

**Use case**: New Python packages added, dependencies updated.

---

### Fix Port Conflicts

```bash
# Find process using port 8000
sudo lsof -i :8000
# OR
sudo netstat -tlnp | grep 8000

# Kill process
sudo fuser -k 8000/tcp

# OR kill specific PID
kill -9 <PID>
```

**Use case**: "Address already in use" error when starting services.

---

### Full Environment Reset

```bash
# Stop everything
docker compose down -v

# Clean Docker
docker system prune -f

# Remove pycache
find . -type d -name __pycache__ -exec rm -r {} +

# Start fresh
docker compose up --build -d
```

**Use case**: Corrupted state, persistent errors, fresh start.

---

## Access Services

### Local Access (Direct)

| Service | URL | Purpose |
|---------|-----|---------|
| **API Docs** | `http://localhost:8000/docs` | Swagger UI - test endpoints |
| **API ReDoc** | `http://localhost:8000/redoc` | Alternative API documentation |
| **Airflow** | `http://localhost:8080` | Airflow DAG management (admin/admin) |
| **pgAdmin** | `http://localhost:5050` | Database GUI (admin@admin.com/admin123) |
| **Streamlit** | `http://localhost:8501` | Webapp dashboard |

---

### Remote SSH Access (Proxmox VM + Tailscale)

#### 1. Using Remote SSH Extension

```bash
# In VS Code Remote Explorer:
# 1. Click "+" → Add SSH Target
# 2. Enter: ssh user@your-tailscale-ip
# 3. Connect
# 4. Open Forwarded Ports section
# 5. Forward port: 8000
```

Then access locally:
- `http://localhost:8000/docs`
- `http://localhost:8080` (Airflow)
- etc.

---

#### 2. Manual SSH Tunneling

```bash
# Forward multiple ports
ssh -L 8000:localhost:8000 \
    -L 8080:localhost:8080 \
    -L 5050:localhost:5050 \
    user@your-tailscale-ip

# Then access via localhost
curl http://localhost:8000/health
```

---

#### 3. Add to SSH Config

Create `~/.ssh/config`:
```
Host proxmox-vm
  HostName 100.x.x.x
  User malo
  IdentityFile ~/.ssh/id_rsa
```

Then:
```bash
ssh proxmox-vm
```

---

## Troubleshooting

### API Won't Start

**Error**: `ModuleNotFoundError: No module named 'joblib'`

**Solution**:
```bash
# Rebuild Docker without cache
docker compose down
docker compose up --build -d api
```

---

### Port Already in Use

**Error**: `failed to bind host port 0.0.0.0:8000/tcp: address already in use`

**Solution**:
```bash
# Kill process using port
sudo fuser -k 8000/tcp

# OR find and kill specific process
sudo lsof -i :8000
kill -9 <PID>

# Then restart
docker compose up -d
```

---

### Database Connection Failed

**Error**: `sqlalchemy.exc.ArgumentError: Expected string or URL object, got None`

**Solution**:
```bash
# Check if .env is loaded
echo $DATABASE_URL

# Set manually
export DATABASE_URL="postgresql://openaq_user:123456789@localhost:5432/openaq_db"

# Or ensure Docker uses .env
docker compose restart api
```

---

### Can't Connect to Database from API

**Solution**:
```bash
# 1. Verify database is running
docker compose logs db

# 2. Verify database is healthy
docker compose ps  # Check STATUS column

# 3. Check connection string in .env
cat .env | grep DATABASE_URL

# 4. Test connection manually (inside container)
docker compose exec api psql $DATABASE_URL -c "SELECT 1"
```

---

### Docker Cache Issues

**Solution**:
```bash
# Clear build cache
docker builder prune -a

# Rebuild without cache
docker compose up --build --no-cache -d
```

---

### API Container Keeps Exiting

**Check logs**:
```bash
docker compose logs api --tail=100
```

**Common fixes**:
```bash
# Rebuild
docker compose up --build -d api

# Check for syntax errors in Python files
python -m py_compile api/main.py

# Restart
docker compose restart api
```

---

## Environment Variables

### Key Variables in `.env`

```env
# Database
POSTGRES_USER=openaq_user
POSTGRES_PASSWORD=123456789
POSTGRES_DB=openaq_db
DATABASE_URL=postgresql://openaq_user:123456789@db:5432/openaq_db

# API
API_HOST=0.0.0.0
API_PORT=8000

# Webapp
STREAMLIT_SERVER_PORT=8501
API_BASE_URL=http://api:8000

# Airflow
AIRFLOW_UID=501
AIRFLOW_PORT=8080
AIRFLOW_USER=admin
AIRFLOW_PASSWORD=admin
```

### Load Environment Variables

```bash
# Load for current session
export $(cat .env | xargs)

# Verify
echo $DATABASE_URL
echo $API_PORT
```

---

## Common Workflows

### Development Workflow

```bash
# 1. Stop old containers
docker compose down

# 2. Make code changes in api/main.py

# 3. Rebuild and restart
docker compose up --build -d api

# 4. Monitor logs
docker compose logs -f api

# 5. Test API
curl http://localhost:8000/docs
```

---

### Database Debugging

```bash
# Access database directly
docker compose exec db psql -U openaq_user -d openaq_db

# Common SQL commands
\dt                                    # List tables
SELECT * FROM your_table LIMIT 5;     # View data
\q                                     # Exit
```

---

### Airflow DAG Testing

```bash
# View DAG lists
docker compose logs -f airflow-scheduler

# Access Airflow UI
# http://localhost:8080
# Username: admin
# Password: admin
```

---

## Quick Reference

| Task | Command |
|------|---------|
| Start everything | `docker compose up -d` |
| View logs | `docker compose logs -f api` |
| Restart service | `docker compose restart api` |
| Rebuild images | `docker compose up --build -d` |
| Stop everything | `docker compose down` |
| Test API | `curl http://localhost:8000/health` |
| Access docs | Browser: `http://localhost:8000/docs` |
| Reset everything | `docker compose down -v && docker system prune -a -f` |

---

## Additional Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Uvicorn Docs**: https://www.uvicorn.org/
- **Docker Compose Docs**: https://docs.docker.com/compose/
- **Airflow Docs**: https://airflow.apache.org/
- **PostgreSQL Docs**: https://www.postgresql.org/docs/

---

**Last Updated**: March 25, 2026
