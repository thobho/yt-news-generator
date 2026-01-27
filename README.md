# YT News Generator - Web Dashboard

Web application for generating YouTube Shorts news videos with AI-generated dialogue, images, and text-to-speech.

## Features

- Browse and manage video generation runs
- Generate dialogue from news topics using AI
- Create images with DALL-E
- Generate audio with ElevenLabs TTS
- Render videos with Remotion
- Upload directly to YouTube

## Requirements

### System Requirements

- **Python**: 3.10+
- **Node.js**: 18+
- **npm**: 9+
- **FFmpeg**: Required for video rendering (install via `brew install ffmpeg` on macOS)

### Environment Variables

The following environment variables must be set:

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key for GPT-4 dialogue generation and DALL-E images | Yes |
| `ELEVENLABS_API_KEY` | ElevenLabs API key for text-to-speech | Yes |
| `PERPLEXITY_API_KEY` | Perplexity AI API key for news research | Yes |
| `AUTH_PASSWORD` | Password for dashboard authentication | Yes |
| `HOST` | Server host (default: `0.0.0.0`) | No |
| `PORT` | Server port (default: `8000`) | No |

### Authentication

The dashboard requires password authentication to protect all API endpoints.

**Setup:**
```bash
# Set a strong password
export AUTH_PASSWORD="your-secure-password"
```

**How it works:**
- All `/api/*` endpoints require authentication (except `/api/auth/*`)
- Session is stored in an HTTP-only cookie (24-hour expiration)
- Login page is shown automatically when not authenticated
- Use the "Logout" button in the dashboard header to end session

**Security features:**
- Constant-time password comparison (prevents timing attacks)
- HTTP-only cookies (prevents XSS token theft)
- SameSite=Strict cookies (prevents CSRF)
- Sessions stored in memory (cleared on server restart)

### Google OAuth Credentials (for YouTube Upload)

To enable YouTube upload functionality:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the **YouTube Data API v3**
4. Create OAuth 2.0 credentials (Desktop application type)
5. Download the credentials JSON file
6. Save it as `credentials/client_secrets.json`

On first YouTube upload, you'll be prompted to authorize the application in your browser.

## Installation

### Quick Start (Production)

```bash
# Set environment variables
export OPENAI_API_KEY="your-openai-key"
export ELEVENLABS_API_KEY="your-elevenlabs-key"
export PERPLEXITY_API_KEY="your-perplexity-key"

# Run the application
./run.sh
```

The script will:
1. Check all required dependencies and environment variables
2. Create Python virtual environment if needed
3. Install Python and Node.js dependencies
4. Build the frontend for production
5. Start the server

### Manual Setup

#### 1. Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r webapp/backend/requirements.txt
```

#### 2. Node.js Dependencies

```bash
# Remotion (video rendering)
cd remotion && npm install && cd ..

# Frontend
cd webapp/frontend && npm install && cd ..
```

#### 3. Build Frontend

```bash
cd webapp/frontend
npm run build
cd ../..

# Copy to backend static folder
mkdir -p webapp/backend/static
cp -r webapp/frontend/dist/* webapp/backend/static/
```

## Running

### Production Mode

```bash
./run.sh
```

Or manually:

```bash
source venv/bin/activate
uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000
```

Access the dashboard at `http://localhost:8000`

### Development Mode

Run backend and frontend separately for hot-reloading:

**Terminal 1 - Backend:**
```bash
source venv/bin/activate
cd webapp/backend
uvicorn main:app --reload --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd webapp/frontend
npm run dev
```

Access the dashboard at `http://localhost:5173`

## Project Structure

```
yt-centric-generator/
├── run.sh                    # Production runner script
├── deploy-ec2.sh             # Deploy to new EC2 instance
├── sync-ec2.sh               # Sync changes to existing EC2
├── requirements.txt          # Python dependencies (core)
├── credentials/              # SSH keys & OAuth (gitignored)
│   └── client_secrets.json   # Google OAuth for YouTube
├── data/
│   ├── dialogue-prompt/      # Dialogue generation prompts
│   └── media/                # Static media assets
├── output/                   # Generated video runs
├── remotion/                 # Video rendering (React/Remotion)
├── src/                      # Core Python scripts
│   ├── generate_audio.py     # ElevenLabs TTS
│   ├── generate_dialogue.py  # GPT-4 dialogue
│   ├── generate_images.py    # DALL-E images
│   ├── generate_video.py     # Remotion rendering
│   ├── perplexity_search.py  # News research
│   └── upload_youtube.py     # YouTube upload
└── webapp/
    ├── backend/              # FastAPI backend
    │   ├── main.py
    │   ├── routes/
    │   ├── services/
    │   └── requirements.txt
    └── frontend/             # React frontend
        ├── src/
        └── package.json
```

## API Endpoints

### Authentication (Public)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/status` | GET | Check authentication status |
| `/api/auth/login` | POST | Login with password |
| `/api/auth/logout` | POST | Logout and clear session |

### Protected Endpoints (Require Authentication)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/runs` | GET | List all runs |
| `/api/runs/{id}` | GET | Get run details |
| `/api/workflow/create-seed` | POST | Create new run |
| `/api/workflow/{id}/generate-dialogue` | POST | Generate dialogue |
| `/api/workflow/{id}/generate-audio` | POST | Generate audio + images |
| `/api/workflow/{id}/generate-video` | POST | Render video |
| `/api/workflow/{id}/upload-youtube` | POST | Upload to YouTube |
| `/api/settings` | GET/PUT | Global settings |
| `/health` | GET | Health check |

## Troubleshooting

### FFmpeg not found
```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

### Permission denied on run.sh
```bash
chmod +x run.sh
```

### Port already in use
```bash
# Use a different port
PORT=3000 ./run.sh
```

### YouTube upload fails
- Ensure `credentials/client_secrets.json` exists
- Delete `credentials/token.json` to re-authenticate
- Check YouTube Data API is enabled in Google Cloud Console

## EC2 Deployment

Deploy the application to AWS EC2 for production use.

### Prerequisites

1. **AWS CLI** installed and configured
2. **AWS credentials** set as environment variables:
   ```bash
   export AWS_ACCESS_KEY_ID=your_access_key
   export AWS_SECRET_ACCESS_KEY=your_secret_key
   export AWS_DEFAULT_REGION=us-east-1  # optional
   ```
3. **SSH key pair** in `credentials/yt-news-generator-key.pem`

### First-Time Deployment

```bash
# Deploy new EC2 instance
./deploy-ec2.sh
```

This script will:
1. Launch a t4g.nano instance (Ubuntu 22.04 ARM64)
2. Create security group (ports 22, 8000)
3. Wait for SSH to be ready
4. Install Node.js 18 and Python dependencies
5. Copy project files via rsync
6. Set up Python venv and install requirements
7. Create `.env` template
8. Start the webapp server

**Output:**
```
Instance ID: i-xxxxxxxxx
Public IP:   x.x.x.x
Webapp: http://x.x.x.x:8000
Password: admin123
```

### Syncing Changes

After making local changes, sync to the existing instance:

```bash
# Sync to default IP (saved from last deploy)
./sync-ec2.sh

# Or specify IP explicitly
./sync-ec2.sh 100.53.141.50
```

This script will:
1. Copy changed files via rsync (excludes node_modules, venv, .git)
2. Restart the uvicorn server

### Updating API Keys

```bash
# SSH into the instance
ssh -i credentials/yt-news-generator-key.pem ubuntu@<PUBLIC_IP>

# Edit environment file
nano /home/ubuntu/yt-news-generator/.env

# Restart the server
pkill uvicorn
cd /home/ubuntu/yt-news-generator
source .env && source venv/bin/activate
nohup python -m uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000 > /tmp/webapp.log 2>&1 &
```

### Deployment Scripts

| Script | Purpose |
|--------|---------|
| `deploy-ec2.sh` | Create new EC2 instance from scratch |
| `sync-ec2.sh` | Sync local changes to existing instance |

### Supported Regions

- us-east-1 (default)
- us-east-2
- us-west-1
- us-west-2
- eu-west-1
- eu-central-1
