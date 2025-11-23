from sqlalchemy.orm import Session
from sqlalchemy import desc
from models import Device, Node, Fault
from schemas import DeviceRegister, FaultReport, NodeStatusUpdate
from datetime import datetime

# Device

def register_or_update_device(db: Session, payload: DeviceRegister):
    device = db.query(Device).filter(Device.fcm_token == payload.fcm_token).first()
    if device:
        device.role = payload.role
    else:
        device = Device(fcm_token=payload.fcm_token, role=payload.role)
        db.add(device)
    db.commit()
    db.refresh(device)
    return device

# Node

def get_all_nodes(db: Session):
    return db.query(Node).order_by(desc(Node.last_updated), desc(Node.id)).all()

def update_node_status(db: Session, payload: NodeStatusUpdate):
    node = db.query(Node).filter(Node.id == payload.node_id).first()
    if not node:
        # Create new node if it doesn't exist
        if payload.latitude is not None and payload.longitude is not None:
            node = Node(
                id=payload.node_id,
                latitude=payload.latitude,
                longitude=payload.longitude,
                status=payload.status,
                last_updated=datetime.utcnow()
            )
            db.add(node)
        else:
            # Create node with default location (0,0) if no location provided
            node = Node(
                id=payload.node_id,
                latitude=0.0,
                longitude=0.0,
                status=payload.status,
                last_updated=datetime.utcnow()
            )
            db.add(node)
    else:
        # Update existing node
        node.status = payload.status
        node.last_updated = datetime.utcnow()
        
        # Update location only if provided
        if payload.latitude is not None and payload.longitude is not None:
            node.latitude = payload.latitude
            node.longitude = payload.longitude
    
    db.commit()
    db.refresh(node)
    return node

# Fault

def create_fault(db: Session, payload: FaultReport):
    fault = Fault(
        node_id=payload.node_id,
        description=payload.description,
        confidence=payload.confidence,
        image_url=payload.image_url
    )
    db.add(fault)
    # Also update node status to 'faulty'
    node = db.query(Node).filter(Node.id == payload.node_id).first()
    if node:
        node.status = 'faulty'
        node.last_updated = datetime.utcnow()
    db.commit()
    db.refresh(fault)
    return fault

def get_all_faults(db: Session):
    return db.query(Fault).order_by(desc(Fault.reported_at), desc(Fault.id)).all()

def get_staff_fcm_tokens(db: Session):
    return [d.fcm_token for d in db.query(Device).filter(Device.role == 'staff').all()]

def get_stats(db: Session):
    total_nodes = db.query(Node).count()
    active_faults_count = db.query(Node).filter(Node.status == 'faulty').count()
    fault_percentage = (active_faults_count / total_nodes * 100) if total_nodes > 0 else 0
    return {
        "active_faults_count": active_faults_count,
        "total_nodes": total_nodes,
        "fault_percentage": round(fault_percentage, 2)
    }
