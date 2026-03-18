# Docker Setup Guide for EcomAgent

## Prerequisites
- Docker Desktop installed ([Download here](https://www.docker.com/products/docker-desktop))
- Docker Compose (included with Docker Desktop)

## Building the Docker Image

```bash
# Navigate to project directory
cd "c:\Users\saatw\gemini agent"

# Build the Docker image
docker build -t ecomagent:latest .
```

## Running with Docker Compose

```bash
# Start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

## Running Individual Docker Container

```bash
# Run the container
docker run -d \
  --name ecomagent \
  -p 5000:5000 \
  --env-file .env \
  ecomagent:latest

# View logs
docker logs -f ecomagent

# Stop the container
docker stop ecomagent
docker rm ecomagent
```

## Accessing the Application

Once running, access the EcomAgent at:
- **Web UI**: http://localhost:5000
- **API**: http://localhost:5000/status

## Environment Variables

The `.env` file will be automatically loaded. Required variables:
- `GROQ_API_KEY` - Groq API key for AI extraction
- `SHOPIFY_STORE_URL` - Your Shopify store URL
- `SHOPIFY_ACCESS_TOKEN` - Your Shopify API access token

## Health Check

The container includes an automatic health check that verifies the Flask app is running every 30 seconds.

## Troubleshooting

**Container fails to start:**
```bash
docker logs ecomagent
```

**Rebuild without cache:**
```bash
docker-compose build --no-cache
```

**Remove all containers and rebuild:**
```bash
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

## Production Deployment

For production, replace the Flask development server with a production WSGI server (Gunicorn):

1. Update `requirements.txt` to include `gunicorn`
2. Change the Dockerfile CMD to:
   ```dockerfile
   CMD ["gunicorn", "--bind", "0.0.0.0:5000", "src.app:app"]
   ```
3. Rebuild and deploy

## Performance Tips

- Use volume mounts for development to avoid rebuilds
- Run with `--restart=unless-stopped` for auto-restart on failure
- Use health checks to ensure container stability
- Consider using a load balancer for multiple instances
