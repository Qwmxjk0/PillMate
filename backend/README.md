# PillMate Backend API

A FastAPI backend application with Server-Sent Events (SSE) support for real-time communication.

## Features

- FastAPI framework with automatic API documentation
- Server-Sent Events (SSE) for real-time streaming
- CORS support for frontend integration
- Health check endpoint
- Customizable SSE streams with duration and interval controls

## Installation

### Option 1: Local Development

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

### Option 2: Docker (Recommended)

1. Build and run with Docker Compose:
```bash
docker-compose up --build
```

2. Run in background:
```bash
docker-compose up -d --build
```

## Running the Application

### Local Development
```bash
python main.py
```

### Docker Development
```bash
# Build and run
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Production with Docker
```bash
# Production build
docker-compose -f docker-compose.yml up -d --build

# With nginx reverse proxy
docker-compose up -d
```

The API will be available at:
- **API**: http://localhost:8000
- **Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## API Endpoints

### Root Endpoint
- **GET** `/` - API information and available endpoints

### Health Check
- **GET** `/health` - Health status check

### Server-Sent Events
- **GET** `/events` - Continuous SSE stream (sends events every 2 seconds)
- **GET** `/events/custom?duration=30&interval=1.0` - Custom SSE stream with configurable parameters

## SSE Usage Examples

### Basic SSE Stream
```javascript
const eventSource = new EventSource('http://localhost:8000/events');

eventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
};

eventSource.onerror = function(event) {
    console.error('SSE error:', event);
};
```

### Custom SSE Stream
```javascript
const eventSource = new EventSource('http://localhost:8000/events/custom?duration=60&interval=0.5');

eventSource.addEventListener('custom', function(event) {
    const data = JSON.parse(event.data);
    console.log('Custom event:', data);
});
```

## API Documentation

Once the server is running, visit http://localhost:8000/docs for interactive API documentation powered by Swagger UI.

## Project Structure

```
backend/
├── main.py              # FastAPI application
├── requirements.txt     # Python dependencies
├── Dockerfile          # Docker configuration
├── docker-compose.yml  # Docker Compose configuration
├── nginx.conf          # Nginx reverse proxy config
├── .dockerignore       # Docker ignore file
└── README.md           # This file
```

## Docker Services

### PillMate Backend
- **Container**: `pillmate-backend`
- **Port**: 8000
- **Health Check**: Built-in endpoint monitoring
- **Restart Policy**: `unless-stopped`

### Nginx Reverse Proxy (Optional)
- **Container**: `pillmate-nginx`
- **Ports**: 80, 443
- **Features**: Rate limiting, CORS headers, SSE optimization
- **Dependencies**: Requires backend service

## Development

The application includes:
- Automatic reloading in development mode
- CORS middleware for cross-origin requests
- Proper SSE headers for browser compatibility
- Error handling and client disconnection detection
- Configurable event streams

## Production Considerations

- Configure CORS origins properly for production
- Set up proper logging and monitoring
- Consider using a reverse proxy (nginx) for production
- Implement authentication and rate limiting as needed
