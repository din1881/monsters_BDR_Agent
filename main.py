from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Initialize FastAPI with root_path for Vercel
app = FastAPI(root_path="/api")

# Update CORS middleware for Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add health check endpoint for Vercel
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# ... rest of your existing code ... 