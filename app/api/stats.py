"""
統計 API - 完整儀表板
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, extract
from datetime import datetime, timedelta
from typing import Optional
import json

from app.core.database import get_db
from app.core.response import success_response
from app.models.models import Order, Property, Cleaner

router = APIRouter()


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """系統統計 (基礎)"""
    
    # 訂單數
    total_orders = await db.scalar(select(func.count(Order.id))) or 0
    open_orders = await db.scalar(
        select(func.count(Order.id)).where(Order.status == "OPEN")
    ) or 0
    completed_orders = await db.scalar(
        select(func.count(Order.id)).where(Order.status == "COMPLETED")
    ) or 0
    
    # 房源數
    total_properties = await db.scalar(select(func.count(Property.id))) or 0
    
    # 清潔工人數
    total_cleaners = await db.scalar(select(func.count(Cleaner.id))) or 0
    online_cleaners = await db.scalar(
        select(func.count(Cleaner.id)).where(Cleaner.status == "online")
    ) or 0
    
    # 總營收
    total_revenue = await db.scalar(
        select(func.sum(Order.price)).where(Order.status == "COMPLETED")
    ) or 0
    
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
        "revenue": float(total_revenue)
    })


@router.get("/dashboard")
async def get_dashboard_stats(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db)
):
    """儀表板統計 (近 N 天)"""
    
    # 日期範圍
    start_date = datetime.now() - timedelta(days=days)
    
    # ===== 訂單趨勢 =====
    # 按日期統計訂單數
    daily_orders = await db.execute(
        select(
            func.date(Order.created_at).label('date'),
            func.count(Order.id).label('count')
        )
        .where(Order.created_at >= start_date)
        .group_by(func.date(Order.created_at))
        .order_by(func.date(Order.created_at))
    )
    order_trend = [{"date": str(r[0]), "count": r[1]} for r in daily_orders.fetchall()]
    
    # ===== 收入趨勢 =====
    daily_revenue = await db.execute(
        select(
            func.date(Order.completed_at).label('date'),
            func.sum(Order.price).label('revenue')
        )
        .where(and_(
            Order.completed_at >= start_date,
            Order.status == "COMPLETED"
        ))
        .group_by(func.date(Order.completed_at))
        .order_by(func.date(Order.completed_at))
    )
    revenue_trend = [
        {"date": str(r[0]), "revenue": float(r[1] or 0)} 
        for r in daily_revenue.fetchall()
    ]
    
    # ===== 訂單狀態分佈 =====
    status_dist = await db.execute(
        select(Order.status, func.count(Order.id))
        .group_by(Order.status)
    )
    status_distribution = [
        {"status": str(s[0]), "count": s[1]} 
        for s in status_dist.fetchall()
    ]
    
    # ===== 清潔員排行 (搶單數) =====
    cleaner_stats = await db.execute(
        select(
            Cleaner.id,
            Cleaner.name,
            Cleaner.total_jobs,
            Cleaner.accepted_jobs,
            Cleaner.rating
        )
        .where(Cleaner.total_jobs > 0)
        .order_by(Cleaner.total_jobs.desc())
        .limit(10)
    )
    top_cleaners = [
        {
            "id": r[0],
            "name": r[1],
            "total_jobs": r[2],
            "accepted_jobs": r[3],
            "rating": float(r[4] or 5.0)
        }
        for r in cleaner_stats.fetchall()
    ]
    
    # ===== 房源排行 (訂單數) =====
    property_stats = await db.execute(
        select(
            Property.id,
            Property.name,
            func.count(Order.id).label('order_count'),
            func.sum(Order.price).label('total_revenue')
        )
        .join(Order, Order.property_id == Property.id)
        .group_by(Property.id, Property.name)
        .order_by(func.count(Order.id).desc())
        .limit(10)
    )
    top_properties = [
        {
            "id": r[0],
            "name": r[1],
            "order_count": r[2],
            "total_revenue": float(r[3] or 0)
        }
        for r in property_stats.fetchall()
    ]
    
    # ===== 時段分析 =====
    hourly_stats = await db.execute(
        select(
            extract('hour', Order.checkout_time).label('hour'),
            func.count(Order.id).label('count')
        )
        .where(Order.checkout_time.isnot(None))
        .group_by(extract('hour', Order.checkout_time))
        .order_by('hour')
    )
    hourly_distribution = [
        {"hour": int(r[0] or 0), "count": r[1]}
        for r in hourly_stats.fetchall()
    ]
    
    # ===== 今日統計 =====
    today = datetime.now().date()
    today_start = datetime.combine(today, datetime.min.time())
    
    today_orders = await db.scalar(
        select(func.count(Order.id))
        .where(Order.created_at >= today_start)
    ) or 0
    
    today_completed = await db.scalar(
        select(func.count(Order.id))
        .where(and_(
            Order.completed_at >= today_start,
            Order.status == "COMPLETED"
        ))
    ) or 0
    
    today_revenue = await db.scalar(
        select(func.sum(Order.price))
        .where(and_(
            Order.completed_at >= today_start,
            Order.status == "COMPLETED"
        ))
    ) or 0
    
    # ===== 彙總 =====
    total_orders = await db.scalar(select(func.count(Order.id))) or 0
    total_revenue = await db.scalar(
        select(func.sum(Order.price)).where(Order.status == "COMPLETED")
    ) or 0
    avg_order_value = float(total_revenue) / total_orders if total_orders > 0 else 0
    
    return success_response(data={
        "summary": {
            "period_days": days,
            "total_orders": total_orders,
            "total_revenue": float(total_revenue),
            "avg_order_value": round(avg_order_value, 2)
        },
        "today": {
            "orders": today_orders,
            "completed": today_completed,
            "revenue": float(today_revenue)
        },
        "order_trend": order_trend,
        "revenue_trend": revenue_trend,
        "status_distribution": status_distribution,
        "top_cleaners": top_cleaners,
        "top_properties": top_properties,
        "hourly_distribution": hourly_distribution
    })


@router.get("/revenue")
async def get_revenue_stats(
    start_date: str = None,
    end_date: str = None,
    db: AsyncSession = Depends(get_db)
):
    """營收統計"""
    
    # 處理日期參數
    if start_date:
        start = datetime.fromisoformat(start_date)
    else:
        start = datetime.now() - timedelta(days=30)
    
    if end_date:
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now()
    
    # 總營收
    total = await db.scalar(
        select(func.sum(Order.price))
        .where(and_(
            Order.completed_at.between(start, end),
            Order.status == "COMPLETED"
        ))
    ) or 0
    
    # 按日統計
    daily = await db.execute(
        select(
            func.date(Order.completed_at).label('date'),
            func.count(Order.id).label('count'),
            func.sum(Order.price).label('revenue')
        )
        .where(and_(
            Order.completed_at.between(start, end),
            Order.status == "COMPLETED"
        ))
        .group_by(func.date(Order.completed_at))
        .order_by(func.date(Order.completed_at))
    )
    
    daily_stats = [
        {
            "date": str(r[0]),
            "orders": r[1],
            "revenue": float(r[2] or 0)
        }
        for r in daily.fetchall()
    ]
    
    return success_response(data={
        "period": {
            "start": start.date().isoformat(),
            "end": end.date().isoformat()
        },
        "total_revenue": float(total),
        "daily": daily_stats
    })


@router.get("/cleaners")
async def get_cleaner_performance(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """清潔員績效"""
    
    # 所有清潔員統計
    result = await db.execute(
        select(Cleaner).order_by(Cleaner.total_jobs.desc()).limit(limit)
    )
    cleaners = result.scalars().all()
    
    cleaner_list = []
    for c in cleaners:
        # 計算完成率
        completion_rate = (c.accepted_jobs / c.total_jobs * 100) if c.total_jobs > 0 else 0
        
        # 獲取最近完成的訂單
        recent_orders = await db.execute(
            select(func.count(Order.id))
            .where(and_(
                Order.cleaner_id == c.id,
                Order.status == "COMPLETED"
            ))
        )
        completed_count = recent_orders.scalar() or 0
        
        cleaner_list.append({
            "id": c.id,
            "name": c.name,
            "phone": c.phone,
            "status": c.status,
            "total_jobs": c.total_jobs,
            "accepted_jobs": c.accepted_jobs,
            "completed_jobs": completed_count,
            "completion_rate": round(completion_rate, 1),
            "rating": float(c.rating or 5.0)
        })
    
    return success_response(data=cleaner_list)


@router.get("/properties")
async def get_property_stats(
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    """房源統計"""
    
    result = await db.execute(
        select(
            Property.id,
            Property.name,
            Property.address,
            func.count(Order.id).label('total_orders'),
            func.sum(
                func.case((Order.status == "COMPLETED", Order.price), else_=0)
            ).label('total_revenue'),
            func.avg(Order.price).label('avg_price')
        )
        .outerjoin(Order, Order.property_id == Property.id)
        .group_by(Property.id, Property.name, Property.address)
        .order_by(func.count(Order.id).desc())
        .limit(limit)
    )
    
    properties = []
    for r in result.fetchall():
        properties.append({
            "id": r[0],
            "name": r[1],
            "address": r[2],
            "total_orders": r[3] or 0,
            "total_revenue": float(r[4] or 0),
            "avg_price": float(r[5] or 0)
        })
    
    return success_response(data=properties)
