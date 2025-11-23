from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
import os
import logging
from fastapi.security.api_key import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from time import time
from datetime import datetime, timedelta
import asyncio

from database import SessionLocal, engine
from models import Base  # Ensure models are imported so tables are created
from models import Node as NodeModel
from schemas import DeviceRegister, NodeStatusUpdate, FaultReport, ResponseSchema, Device as DeviceSchema, Node, Fault as FaultSchema
import crud
from fcm_utils import send_fault_notification
from notification_utils import send_fault_notification as send_email_notification


# Create tables on startup (Alembic-ready models; for now use create_all)
Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# Optional API key auth
API_KEY = os.getenv("API_KEY", "")
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def require_api_key(api_key: str = Security(api_key_header)):
    if API_KEY:
        if not api_key or api_key != API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return True


app = FastAPI(title="Pole Fault Monitoring API", version="1.0.0")

# Logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger(__name__)


# CORS - configurable via env
default_cors = "http://172.16.221.164:8000,http://10.0.2.2:8000,http://localhost:8000"
cors_origins = os.getenv("CORS_ALLOW_ORIGINS", default_cors)
allow_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for uploads
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


# Simple request logging middleware
class RequestLoggerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time()
        response = await call_next(request)
        duration_ms = int((time() - start) * 1000)
        logger.info("%s %s -> %s (%d ms)", request.method, request.url.path, response.status_code, duration_ms)
        return response

app.add_middleware(RequestLoggerMiddleware)


# Heartbeat/offline monitor settings (no app/UI changes required)
HEARTBEAT_MAX_AGE_SECONDS = int(os.getenv("HEARTBEAT_MAX_AGE_SECONDS", "300"))  # 5 minutes
HEARTBEAT_CHECK_INTERVAL_SECONDS = int(os.getenv("HEARTBEAT_CHECK_INTERVAL_SECONDS", "60"))  # 1 minute

async def heartbeat_monitor_task():
    while True:
        try:
            threshold = datetime.utcnow() - timedelta(seconds=HEARTBEAT_MAX_AGE_SECONDS)
            db = SessionLocal()
            try:
                stale_nodes = db.query(NodeModel).filter(NodeModel.last_updated < threshold, NodeModel.status != 'faulty').all()
                if stale_nodes:
                    for node in stale_nodes:
                        node.status = 'faulty'
                        node.last_updated = datetime.utcnow()
                    db.commit()
                    try:
                        staff_tokens = crud.get_staff_fcm_tokens(db)
                        for node in stale_nodes:
                            send_fault_notification(staff_tokens, node.id, 100)
                    except Exception:
                        logger.exception("Failed to send FCM for offline nodes")
            finally:
                db.close()
        except Exception:
            logger.exception("Heartbeat monitor iteration failed")
        await asyncio.sleep(HEARTBEAT_CHECK_INTERVAL_SECONDS)

@app.post("/api/v1/devices/register", response_model=ResponseSchema)
def register_device(payload: DeviceRegister, db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    device = crud.register_or_update_device(db, payload)
    return ResponseSchema(status="success", message="Device registered", data=DeviceSchema.model_validate(device) if hasattr(DeviceSchema, "model_validate") else DeviceSchema.from_orm(device))


@app.get("/api/v1/nodes", response_model=ResponseSchema)
def list_nodes(db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    nodes = crud.get_all_nodes(db)
    nodes_schema = [
        (Node.model_validate(n) if hasattr(Node, "model_validate") else Node.from_orm(n))
        for n in nodes
    ]
    return ResponseSchema(status="success", message="Nodes fetched", data=nodes_schema)


@app.post("/api/v1/nodes/update", response_model=ResponseSchema)
def update_node(payload: NodeStatusUpdate, db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    try:
        # First update the node status
        node = crud.update_node_status(db, payload)
        
        # Update location only if both latitude and longitude are provided
        if payload.latitude is not None and payload.longitude is not None:
            node.latitude = payload.latitude
            node.longitude = payload.longitude
            db.commit()
            db.refresh(node)
            
        logger.info(f"Node {payload.node_id} updated - Status: {payload.status}, Location: {payload.latitude},{payload.longitude}")
        
    except Exception as exc:
        logger.error(f"Failed to update node {payload.node_id}: {str(exc)}")
        raise HTTPException(status_code=404, detail=f"Node {payload.node_id} not found or update failed")
    
    node_schema = Node.model_validate(node) if hasattr(Node, "model_validate") else Node.from_orm(node)
    return ResponseSchema(status="success", message="Node updated", data=node_schema)


@app.post("/api/v1/faults/report", response_model=ResponseSchema)
def report_fault(payload: FaultReport, db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    # Validate node exists before creating fault
    node_exists = db.query(crud.Node).filter(crud.Node.id == payload.node_id).first() if hasattr(crud, "Node") else None
    if not node_exists:
        from models import Node as NodeModel
        node_exists = db.query(NodeModel).filter(NodeModel.id == payload.node_id).first()
    if not node_exists:
        raise HTTPException(status_code=404, detail="Node not found")

    fault = crud.create_fault(db, payload)

    # Send FCM push to staff devices
    try:
        staff_tokens = crud.get_staff_fcm_tokens(db)
        send_fault_notification(staff_tokens, payload.node_id, payload.confidence)
    except Exception:
        logger.exception("Failed to send FCM notification for node_id=%s", payload.node_id)

    # Send email notification
    try:
        fault_data = {
            "id": fault.id,
            "node_id": fault.node_id,
            "description": fault.description,
            "confidence": fault.confidence,
            "reported_at": fault.reported_at
        }
        email_sent = send_email_notification(fault_data)
        logger.info(f"Email notification sent for fault {fault.id}: {email_sent}")
    except Exception:
        logger.exception("Failed to send email notification for fault_id=%s", fault.id)

    fault_schema = FaultSchema.model_validate(fault) if hasattr(FaultSchema, "model_validate") else FaultSchema.from_orm(fault)
    return ResponseSchema(status="success", message="Fault reported", data=fault_schema)


@app.get("/api/v1/faults", response_model=ResponseSchema)
def list_faults(db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    faults = crud.get_all_faults(db)
    faults_schema = [
        (FaultSchema.model_validate(f) if hasattr(FaultSchema, "model_validate") else FaultSchema.from_orm(f))
        for f in faults
    ]
    return ResponseSchema(status="success", message="Faults fetched", data=faults_schema)


@app.get("/api/v1/stats", response_model=ResponseSchema)
def get_stats(db: Session = Depends(get_db), _: bool = Depends(require_api_key)):
    stats = crud.get_stats(db)
    return ResponseSchema(status="success", message="Stats computed", data=stats)


@app.get("/", response_model=ResponseSchema)
def root():
    return ResponseSchema(status="ok", message="Pole Fault Monitoring API is running", data=None)



# Simple image upload endpoint
@app.post("/api/v1/upload", response_model=ResponseSchema)
def upload_image(file: UploadFile = File(...), _: bool = Depends(require_api_key)):
    try:
        filename = file.filename or "upload.bin"
        # basic sanitization
        filename = os.path.basename(filename)
        save_path = os.path.join(UPLOAD_DIR, filename)
        # avoid overwrite
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(save_path):
            filename = f"{base}_{counter}{ext}"
            save_path = os.path.join(UPLOAD_DIR, filename)
            counter += 1
        with open(save_path, "wb") as f:
            f.write(file.file.read())
        public_url = f"/uploads/{filename}"
        return ResponseSchema(status="success", message="File uploaded", data={"url": public_url})
    except Exception as exc:
        logger.exception("Upload failed: %s", exc)
        raise HTTPException(status_code=500, detail="Upload failed")

@app.on_event("startup")
def seed_data_if_enabled():
    should_seed = os.getenv("SEED_SAMPLE_NODES", "false").lower() in ["1", "true", "yes"]
    if not should_seed:
        return
    db = SessionLocal()
    try:
        existing = db.query(NodeModel).count()
        if existing == 0:
            sample_nodes = [
                NodeModel(id=1, latitude=12.9716, longitude=77.5946, status="normal"),
                NodeModel(id=2, latitude=28.7041, longitude=77.1025, status="normal"),
                NodeModel(id=3, latitude=19.0760, longitude=72.8777, status="normal"),
            ]
            db.add_all(sample_nodes)
            db.commit()
    finally:
        db.close()

@app.on_event("startup")
def start_heartbeat_monitor():
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(heartbeat_monitor_task())
        logger.info("Heartbeat monitor started: max_age=%ss interval=%ss", HEARTBEAT_MAX_AGE_SECONDS, HEARTBEAT_CHECK_INTERVAL_SECONDS)
    except Exception:
        logger.exception("Failed to start heartbeat monitor task")

