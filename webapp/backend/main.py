from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import runs, workflow

app = FastAPI(
    title="YT News Generator Dashboard",
    description="API for browsing and managing video generation runs",
    version="1.0.0",
)

# Configure CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(runs.router)
app.include_router(workflow.router)


@app.get("/")
async def root():
    return {"message": "YT News Generator Dashboard API"}


@app.get("/health")
async def health():
    return {"status": "ok"}
