"""
統計 API
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.response import success_response
from app.models.models import Order, Property, Cleaner

router = APIRouter()


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """系統統計"""
    
    # 訂單數
    orders_result = await db.execute(select(func.count(Order.id)))
    total_orders = orders_result.scalar()
    
    open_orders_result = await db.execute(
        select(func.count(Order.id)).where(Order.status == "OPEN")
    )
    open_orders = open_orders_result.scalar()
    
    completed_orders_result = await db.execute(
        select(func.count(Order.id)).where(Order.status == "COMPLETED")
    )
    completed_orders = completed_orders_result.scalar()
    
    # 房源數
    props_result = await db.execute(select(func.count(Property.id)))
    total_properties = props_result.scalar()
    
    # 清潔工人數
    cleaners_result = await db.execute(select(func.count(Cleaner.id)))
    total_cleaners = cleaners_result.scalar()
    
    online_cleaners_result = await db.execute(
        select(func.count(Cleaner.id)).where(Cleaner.status == "online")
    )
    online_cleaners = online_cleaners_result.scalar()
    
    # 總營收
    revenue_result = await db.execute(
        select(func.sum(Order.price)).where(Order.status == "COMPLETED")
    )
    total_revenue = revenue_result.scalar() or 0
    
    return success_response(data={
        "orders": {
            "total": total_orders,
            "open": open_orders,
            "completed": completed_orders
        },
        "properties": total_properties,
        "cleaners": {
            "total": total_cleaners,
            "online": online_cleaners
        },
        "revenue": total_revenue
    })
