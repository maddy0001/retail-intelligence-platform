"""
main.py — the FastAPI application.

Run from the retail-intelligence-platform/ folder:

    venv/bin/uvicorn backend.app.main:app --port 8100

On start-up it makes sure every index exists, seeds the admin/demo accounts,
and starts the two background workers (Change Stream -> WebSocket, and the
simulated order fulfilment). If the React app has been built
(frontend/dist), it is served from the same port, so one URL runs the store.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError

from schema.create_indexes import create_indexes
from .db import get_db
from .routers import admin, auth, catalog, shopping, system
from .seed import seed_users
from .services.fulfillment import FulfillmentWorker
from .services.intelligence import traffic_simulator
from .services.realtime import ChangeStreamWorker, manager
from .settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("retail.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = get_db()
    create_indexes(db, verbose=False)
    created = seed_users(db)
    if created:
        log.info("Seeded accounts: %s", ", ".join(created))
    manager.loop = asyncio.get_running_loop()
    workers = []
    if settings.background:
        stream = ChangeStreamWorker(db)
        stream.start()
        system.state["change_stream"] = stream
        workers = [stream, FulfillmentWorker(db, settings.fulfillment_step_seconds)]
        workers[1].start()
    yield
    traffic_simulator.stop()
    for w in workers:
        w.stop()


app = FastAPI(
    title="Real-Time Retail Intelligence Platform — API",
    version="2.0.0",
    description="Online store on MongoDB: search, cart, transactional checkout, live order tracking, "
                "segment-based offers, recommendations and behavioural risk alerts.",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for module in (auth, catalog, shopping, admin, system):
    app.include_router(module.router)


@app.exception_handler(PyMongoError)
async def mongo_unavailable(request: Request, exc: PyMongoError):
    log.error("MongoDB error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": "The database is unavailable right now. Try again shortly."})


# ---- serve the built React app (frontend/dist) on the same port --------------
DIST = settings.frontend_dist
if (DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa(full_path: str):
    if full_path.startswith(("api/", "ws")):
        raise HTTPException(404, "Not found")
    candidate = DIST / full_path
    if full_path and candidate.is_file() and DIST in candidate.resolve().parents:
        return FileResponse(candidate)
    index = DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    return JSONResponse({"detail": "Front end not built yet. Run `npm run build` in frontend/, "
                                   "or use the Vite dev server on port 5190."}, status_code=404)
