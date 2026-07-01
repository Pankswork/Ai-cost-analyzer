import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.db.session import engine, async_session, Base
from app.db.seeder import seed_database
from app.api import health, auth, tools, submissions, reviews, favorites, misc, analysis
from app.api.admin import tools as admin_tools
from prometheus_fastapi_instrumentator import Instrumentator


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_session() as session:
            await seed_database(session)
    except Exception as e:
        print(f"DB initialization failed: {e}")
    yield
    await engine.dispose()


app = FastAPI(
    title="BestFreeAIFor API",
    description="Backend for bestfreeaifor.com — AI tool directory + cost analysis",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:4321",
        "http://localhost:5173",
        "https://bestfreeaifor.com",
        "https://app.bestfreeaifor.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(tools.router, prefix="/api", tags=["tools"])
app.include_router(submissions.router, prefix="/api", tags=["submissions"])
app.include_router(reviews.router, prefix="/api", tags=["reviews"])
app.include_router(favorites.router, prefix="/api", tags=["favorites"])
app.include_router(misc.router, prefix="/api", tags=["misc"])
app.include_router(analysis.router, prefix="/api", tags=["analysis"])
app.include_router(admin_tools.router, prefix="/api", tags=["admin"])

dist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "dist")
if os.path.isdir(dist_dir):
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
