from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, calendar, canvas, sync, workload, planner, setup, tasks, estimate, constraints, chat

app = FastAPI(
    title="Student AI Assistant",
    description="Help students visualize workload and plan study time",
    version="0.1.0",
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router)
app.include_router(calendar.router)
app.include_router(canvas.router)
app.include_router(sync.router)
app.include_router(workload.router)
app.include_router(planner.router)
app.include_router(setup.router)
app.include_router(tasks.router)
app.include_router(estimate.router)
app.include_router(constraints.router)
app.include_router(chat.router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}
