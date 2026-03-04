from sqlmodel import SQLModel, Field, Field
from sqlalchemy import Column, String, Integer, Float, DateTime, Enum as SQLEnum, Text, Index
from datetime import datetime
from typing import Optional
from enum import Enum


class OrderStatus(str, Enum):
    OPEN = "open"
    ACCEPTED = "accepted"
    ARRIVED = "arrived"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class Property(SQLModel, table=True):
    """房源"""
    __tablename__ = "properties"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=200)
    address: str = Field(max_length=500)
    street: Optional[str] = Field(default=None, max_length=200)
    city: Optional[str] = Field(default=None, max_length=100)
    province: Optional[str] = Field(default=None, max_length=100)
    house_number: Optional[str] = Field(default=None, max_length=50)
    postal_code: Optional[str] = Field(default=None, max_length=20)
    
    # PostGIS 坐標
    latitude: Optional[float] = Field(default=None)
    longitude: Optional[float] = Field(default=None)
    
    bedrooms: int = Field(default=1)
    bathrooms: int = Field(default=1)
    floor: Optional[int] = Field(default=None)
    area: Optional[float] = Field(default=None)  # 面積
    
    host_id: Optional[int] = Field(default=None, foreign_key="users.id")
    host_phone: Optional[str] = Field(default=None, max_length=50)
    
    cleaning_time_minutes: int = Field(default=60)
    cleaning_checklist: Optional[str] = Field(default=None)  # JSON
    notes: Optional[str] = Field(default=None)
    
    status: str = Field(default="active")  # active/inactive
    created_at: Optional[datetime] = Field(default=None)
    
    # 空間索引 (PostGIS)
    __table_args__ = (
        Index('idx_property_geo', 'latitude', 'longitude'),
    )


class Order(SQLModel, table=True):
    """訂單"""
    __tablename__ = "orders"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    property_id: int = Field(foreign_key="properties.id")
    
    host_id: Optional[int] = Field(default=None, foreign_key="users.id")
    host_name: Optional[str] = Field(default=None, max_length=100)
    host_phone: Optional[str] = Field(default=None, max_length=50)
    
    # 清潔工
    cleaner_id: Optional[int] = Field(default=None, foreign_key="cleaners.id")
    cleaner_name: Optional[str] = Field(default=None, max_length=100)
    
    price: float = Field(default=0)
    
    # 時間
    checkout_time: Optional[datetime] = Field(default=None)
    assigned_at: Optional[datetime] = Field(default=None)
    arrived_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    
    # 狀態
    status: OrderStatus = Field(default=OrderStatus.OPEN)
    
    # 樂觀鎖版本號
    version: int = Field(default=0)
    
    # 備註
    text_notes: Optional[str] = Field(default=None)
    voice_url: Optional[str] = Field(default=None)
    completion_photos: Optional[str] = Field(default=None)  # JSON array
    
    accepted_by_host: bool = Field(default=False)
    
    created_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)
    
    __table_args__ = (
        Index('idx_order_status', 'status'),
        Index('idx_order_cleaner', 'cleaner_id'),
    )


class Cleaner(SQLModel, table=True):
    """清潔工"""
    __tablename__ = "cleaners"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    phone: str = Field(unique=True, max_length=50)
    email: Optional[str] = Field(default=None, max_length=200)
    password_hash: str
    
    # 邀請碼
    code: Optional[str] = Field(default=None, max_length=20)
    
    # 位置
    latitude: Optional[float] = Field(default=None)
    longitude: Optional[float] = Field(default=None)
    last_location_update: Optional[datetime] = Field(default=None)
    
    # 統計
    rating: float = Field(default=5.0)
    total_jobs: int = Field(default=0)
    accepted_jobs: int = Field(default=0)
    
    # 狀態
    status: str = Field(default="offline")  # online/offline/busy
    
    # 邀請碼
    code: Optional[str] = Field(default=None, max_length=20)
    
    created_at: Optional[datetime] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)
    
    __table_args__ = (
        Index('idx_cleaner_status', 'status'),
    )


class User(SQLModel, table=True):
    """用戶 (房東)"""
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    phone: str = Field(unique=True, max_length=50)
    email: Optional[str] = Field(default=None, max_length=200)
    password_hash: str
    
    # 邀請碼
    code: Optional[str] = Field(default=None, max_length=20)
    
    created_at: Optional[datetime] = Field(default=None)
