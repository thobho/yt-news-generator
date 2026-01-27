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
├── requirements.txt          # Python dependencies (core)
├── credentials/              # OAuth credentials (gitignored)
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
