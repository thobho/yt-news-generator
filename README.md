# YT News Generator - Web Dashboard

Web application for generating YouTube Shorts news videos with AI-generated dialogue, images, and text-to-speech.

## Features

- Browse and manage video generation runs
- Generate dialogue from news topics using AI
- Create images with DALL-E
- Generate audio with ElevenLabs or Chatterbox TTS
- Render videos with Remotion
- Upload directly to YouTube with scheduling

## Requirements

### System Requirements

- **Python**: 3.10+
- **Node.js**: 18+
- **npm**: 9+
- **FFmpeg**: Required for video rendering (install via `brew install ffmpeg` on macOS)
- **AWS CLI**: Required for syncing S3 data locally (`brew install awscli` on macOS)

### Environment Variables

The following environment variables must be set:

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENROUTER_API_KEY` | OpenRouter API key for all LLM chat completions (dialogue, image prompts, metadata, news selection) | Yes |
| `OPENAI_API_KEY` | OpenAI API key for DALL-E image generation and Whisper transcription | Yes |
| `ELEVENLABS_API_KEY` | ElevenLabs API key for text-to-speech | Yes |
| `PERPLEXITY_API_KEY` | Perplexity AI API key for news research | Yes |
| `AUTH_PASSWORD` | Password for dashboard authentication | Yes |
| `HOST` | Server host (default: `0.0.0.0`) | No |
| `PORT` | Server port (default: `8000`) | No |
| `STORAGE_BACKEND` | `local` or `s3` (auto-detected: `local` on macOS, `s3` on Linux) | No |
| `S3_BUCKET` | S3 bucket name (default: `yt-news-generator`) | No |
| `S3_REGION` | AWS region (default: `us-east-1`) | No |
| `RUNPOD_API_KEY` | RunPod API key for Chatterbox TTS | No |
| `RUNPOD_ENDPOINT_ID` | RunPod serverless endpoint ID | No |

### Authentication

The dashboard requires password authentication to protect all API endpoints.

**Setup:**
```bash
export AUTH_PASSWORD="your-secure-password"
```

**How it works:**
- All `/api/*` endpoints require authentication (except `/api/auth/*`)
- Session is stored in an HTTP-only cookie (24-hour expiration)
- Login page is shown automatically when not authenticated

### Google OAuth Credentials (for YouTube Upload)

To enable YouTube upload functionality:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable the **YouTube Data API v3**
4. Create OAuth 2.0 credentials (Desktop application type)
5. Download the credentials JSON file
6. Save it as `credentials/client_secrets.json`

On first YouTube upload, you'll be prompted to authorize the application in your browser.

## Local Development

### 1. Sync S3 data

Download prompts, media, and settings from S3 to local `storage/` directory:

```bash
# Data only (prompts, media, settings)
./scripts/dump-s3.sh

# Include generated runs (can be large)
./scripts/dump-s3.sh --with-runs
```

This creates the `storage/` directory that mirrors the S3 bucket structure:

```
storage/
├── data/
│   ├── prompts/          # Dialogue, image, research, yt-metadata prompts
│   ├── media/            # Channel logo and static assets
│   └── settings.json     # App configuration
└── output/               # Generated runs (with --with-runs)
    └── run_YYYY-MM-DD_HH-MM-SS/
```

### 2. Set environment variables

```bash
export OPENROUTER_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
export ELEVENLABS_API_KEY="your-key"
export PERPLEXITY_API_KEY="your-key"
export AUTH_PASSWORD="your-password"
```

### 3. Run development servers

```bash
# Local storage (default) - reads from storage/ directory
./scripts/dev.sh

# S3 storage - reads/writes directly to S3 (requires AWS credentials)
./scripts/dev.sh --s3
```

This starts:
- Backend on `http://localhost:8000` (with hot-reload)
- Frontend on `http://localhost:5173` (with HMR)

By default the dev script uses `STORAGE_BACKEND=local` so data is read from `storage/`. Use `--s3` to work directly against S3 (useful for testing production data or when local sync is stale).

## Production

### Quick Start

```bash
export OPENROUTER_API_KEY="your-openrouter-key"
export OPENAI_API_KEY="your-openai-key"
export ELEVENLABS_API_KEY="your-elevenlabs-key"
export PERPLEXITY_API_KEY="your-perplexity-key"

./run.sh
```

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
cd remotion && npm install && cd ..
cd webapp/frontend && npm install && cd ..
```

#### 3. Build Frontend

```bash
cd webapp/frontend
npm run build
cd ../..

mkdir -p webapp/backend/static
cp -r webapp/frontend/dist/* webapp/backend/static/
```

#### 4. Run

```bash
uvicorn webapp.backend.main:app --host 0.0.0.0 --port 8000
```

Access the dashboard at `http://localhost:8000`

## Storage

The app uses a storage abstraction layer that supports local filesystem and S3.

| Mode | Config | Data Path | Runs Path |
|------|--------|-----------|-----------|
| Local | `STORAGE_BACKEND=local` | `storage/data/` | `storage/output/` |
| S3 | `STORAGE_BACKEND=s3` | `s3://{bucket}/data/` | `s3://{bucket}/output/` |

**Auto-detection**: macOS defaults to `local`, Linux defaults to `s3`.

Prompts are managed through the webapp Settings UI and stored in `prompts/` within the data storage.

## Project Structure

```
yt-centric-generator/
├── scripts/
│   ├── dev.sh                # Local development runner
│   ├── dump-s3.sh            # Sync S3 data to local storage
│   ├── deploy-ec2.sh         # Deploy to new EC2 instance
│   └── run.sh                # Production runner
├── requirements.txt          # Python dependencies (core)
├── credentials/              # SSH keys & OAuth (gitignored)
├── storage/                  # Local storage mirror of S3 (gitignored)
│   ├── data/                 # Prompts, media, settings
│   └── output/               # Generated runs
├── remotion/                 # Video rendering (React/Remotion)
├── webapp/
│   ├── backend/              # FastAPI backend
│   │   ├── main.py
│   │   ├── core/             # Logging, storage abstraction
│   │   ├── generation/       # Dialogue, images, audio, metadata, video
│   │   ├── news/             # Perplexity & news source integrations
│   │   ├── routes/           # API route handlers
│   │   ├── services/         # Pipeline, scheduler, OpenRouter, settings
│   │   └── requirements.txt
│   └── frontend/             # React frontend
│       ├── src/
│       └── package.json
└── .github/
    └── workflows/
        └── deploy.yml        # CD: deploy to EC2 on push to main
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
| `/api/workflow/{id}/generate-audio` | POST | Generate audio + timeline |
| `/api/workflow/{id}/generate-images` | POST | Generate images |
| `/api/workflow/{id}/generate-video` | POST | Render video + YT metadata |
| `/api/workflow/{id}/upload-youtube` | POST | Upload to YouTube |
| `/api/workflow/{id}/youtube` | DELETE | Remove from YouTube |
| `/api/settings` | GET/PUT | Global settings |
| `/api/prompts` | GET | List all prompts |
| `/health` | GET | Health check |

## Deployment

Production deployment uses GitHub Actions CD. On push to `main`, the workflow:

1. Builds the frontend
2. Syncs files to EC2 via rsync
3. Copies credentials from GitHub Secrets
4. Installs dependencies and restarts uvicorn

### GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `EC2_SSH_KEY` | SSH private key for EC2 |
| `EC2_HOST` | EC2 instance IP address |
| `ENV_PRODUCTION` | Production `.env` file contents |
| `YT_CLIENT_SECRETS` | Google OAuth client secrets JSON |
| `YT_TOKEN` | Google OAuth token JSON |

### First-Time EC2 Setup

```bash
./scripts/deploy-ec2.sh
```

### Troubleshooting

**FFmpeg not found:**
```bash
brew install ffmpeg        # macOS
sudo apt install ffmpeg    # Ubuntu
```

**YouTube upload fails with `invalid_grant: Token has been expired or revoked`:**

The OAuth2 refresh token has expired. This happens every **7 days** if the Google Cloud app is in "Testing" mode (publish the app to avoid this).

1. Delete the old token and re-authenticate (opens browser):
   ```bash
   rm credentials/token.json
   source venv/bin/activate
   python3 -c "import sys; sys.path.insert(0, 'src'); from upload_youtube import authenticate; authenticate(); print('Done')"
   ```
2. Update the `YT_TOKEN` GitHub secret with the new token:
   ```bash
   cat credentials/token.json
   ```
   Copy the output → GitHub repo **Settings** > **Secrets and variables** > **Actions** > edit `YT_TOKEN` → paste → **Update secret**
3. Also update `YT_CLIENT_SECRETS` if you regenerated the OAuth client:
   ```bash
   cat credentials/client_secrets.json
   ```

**Other YouTube upload issues:**
- Ensure `credentials/client_secrets.json` exists and is a **Desktop** app type (not Web)
- Check YouTube Data API v3 is enabled in Google Cloud Console
- To stop token expiry: Google Cloud Console > OAuth consent screen > **Publish App**


## Costs management
1. https://fal.ai/dashboard/usage-billing/credits
2. https://console.runpod.io/user/billing
2. https://elevenlabs.io/app/developers/usage
3. https://platform.openai.com/usage
4. https://openrouter.ai/activity
5. https://claude.ai/settings/billing
6. https://accounts.hetzner.com/invoice
7. https://us-east-1.console.aws.amazon.com/costmanagement/home?region=us-east-1#/home
