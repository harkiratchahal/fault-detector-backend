from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    fcm_token = Column(String, nullable=False)
    role = Column(String, nullable=False)  # citizen or staff
    created_at = Column(DateTime, default=datetime.utcnow)

class Node(Base):
    __tablename__ = "nodes"
    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    status = Column(String, default="normal")  # normal or faulty
    last_updated = Column(DateTime, default=datetime.utcnow)
    faults = relationship("Fault", back_populates="node")

class Fault(Base):
    __tablename__ = "faults"
    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    description = Column(Text, nullable=False)
    confidence = Column(Float, nullable=False)
    image_url = Column(String, nullable=True)
    reported_at = Column(DateTime, default=datetime.utcnow)
    node = relationship("Node", back_populates="faults")
