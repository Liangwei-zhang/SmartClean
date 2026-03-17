"""統計 API — 管理員認證"""
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from datetime import datetime, timedelta

from app.core.auth     import require_admin, TokenData
from app.core.database import get_db
from app.core.response import success_response
from app.models.models import Order, OrderStatus, Property, Cleaner

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def get_stats(db: AsyncSession = Depends(get_db), _: TokenData = Depends(require_admin)):
    total_orders     = await db.scalar(select(func.count(Order.id)))     or 0
    open_orders      = await db.scalar(select(func.count(Order.id)).where(Order.status==OrderStatus.OPEN))  or 0
    completed_orders = await db.scalar(select(func.count(Order.id)).where(Order.status==OrderStatus.COMPLETED)) or 0
    total_properties = await db.scalar(select(func.count(Property.id))) or 0
    total_cleaners   = await db.scalar(select(func.count(Cleaner.id)))  or 0
    online_cleaners  = await db.scalar(select(func.count(Cleaner.id)).where(Cleaner.status=="online")) or 0
    total_revenue    = await db.scalar(select(func.sum(Order.price)).where(Order.status==OrderStatus.COMPLETED)) or 0
    return success_response(data={
        "orders": {"total": total_orders, "open": open_orders, "completed": completed_orders},
        "properties": total_properties,
        "cleaners": {"total": total_cleaners, "online": online_cleaners},
        "revenue": float(total_revenue)
    })


@router.get("/dashboard")
async def get_dashboard(days: int = Query(30, ge=1, le=365),
                         db: AsyncSession = Depends(get_db),
                         _: TokenData = Depends(require_admin)):
    start = datetime.utcnow() - timedelta(days=days)

    order_trend_rows = (await db.execute(
        select(func.date(Order.created_at).label("date"), func.count(Order.id).label("count"))
        .where(Order.created_at >= start)
        .group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at))
    )).fetchall()

    rev_rows = (await db.execute(
        select(func.date(Order.completed_at).label("date"), func.sum(Order.price).label("revenue"))
        .where(and_(Order.completed_at >= start, Order.status == OrderStatus.COMPLETED))
        .group_by(func.date(Order.completed_at)).order_by(func.date(Order.completed_at))
    )).fetchall()

    status_rows = (await db.execute(
        select(Order.status, func.count(Order.id)).group_by(Order.status)
    )).fetchall()

    top_cleaners_rows = (await db.execute(
        select(Cleaner.id, Cleaner.name, Cleaner.total_jobs, Cleaner.accepted_jobs, Cleaner.rating)
        .where(Cleaner.total_jobs > 0).order_by(Cleaner.total_jobs.desc()).limit(10)
    )).fetchall()

    top_props_rows = (await db.execute(
        select(Property.id, Property.name, func.count(Order.id).label("oc"), func.sum(Order.price).label("rev"))
        .join(Order, Order.property_id == Property.id)
        .group_by(Property.id, Property.name)
        .order_by(func.count(Order.id).desc()).limit(10)
    )).fetchall()

    from sqlalchemy import extract
    hourly_rows = (await db.execute(
        select(extract("hour", Order.checkout_time).label("hour"), func.count(Order.id).label("count"))
        .where(Order.checkout_time.isnot(None))
        .group_by(extract("hour", Order.checkout_time)).order_by("hour")
    )).fetchall()

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_orders    = await db.scalar(select(func.count(Order.id)).where(Order.created_at >= today_start)) or 0
    today_completed = await db.scalar(select(func.count(Order.id)).where(and_(Order.completed_at >= today_start, Order.status == OrderStatus.COMPLETED))) or 0
    today_revenue   = await db.scalar(select(func.sum(Order.price)).where(and_(Order.completed_at >= today_start, Order.status == OrderStatus.COMPLETED))) or 0

    total_orders  = await db.scalar(select(func.count(Order.id))) or 0
    total_revenue = await db.scalar(select(func.sum(Order.price)).where(Order.status == OrderStatus.COMPLETED)) or 0

    return success_response(data={
        "summary":  {"period_days": days, "total_orders": total_orders, "total_revenue": float(total_revenue),
                     "avg_order_value": round(float(total_revenue)/total_orders, 2) if total_orders else 0},
        "today":    {"orders": today_orders, "completed": today_completed, "revenue": float(today_revenue)},
        "order_trend":  [{"date": str(r[0]), "count": r[1]} for r in order_trend_rows],
        "revenue_trend": [{"date": str(r[0]), "revenue": float(r[1] or 0)} for r in rev_rows],
        "status_distribution": [{"status": str(r[0].value if hasattr(r[0],"value") else r[0]), "count": r[1]} for r in status_rows],
        "top_cleaners":  [{"id":r[0],"name":r[1],"total_jobs":r[2],"accepted_jobs":r[3],"rating":float(r[4] or 5.0)} for r in top_cleaners_rows],
        "top_properties": [{"id":r[0],"name":r[1],"order_count":r[2],"total_revenue":float(r[3] or 0)} for r in top_props_rows],
        "hourly_distribution": [{"hour": int(r[0] or 0), "count": r[1]} for r in hourly_rows],
    })


@router.get("/revenue")
async def get_revenue(start_date: str=None, end_date: str=None,
                       db: AsyncSession=Depends(get_db), _: TokenData=Depends(require_admin)):
    start = datetime.fromisoformat(start_date) if start_date else datetime.utcnow() - timedelta(days=30)
    end   = datetime.fromisoformat(end_date)   if end_date   else datetime.utcnow()
    total = await db.scalar(select(func.sum(Order.price)).where(and_(Order.completed_at.between(start,end), Order.status==OrderStatus.COMPLETED))) or 0
    daily = (await db.execute(select(func.date(Order.completed_at).label("date"), func.count(Order.id).label("count"), func.sum(Order.price).label("revenue")).where(and_(Order.completed_at.between(start,end), Order.status==OrderStatus.COMPLETED)).group_by(func.date(Order.completed_at)).order_by(func.date(Order.completed_at)))).fetchall()
    return success_response(data={"period": {"start": start.date().isoformat(), "end": end.date().isoformat()}, "total_revenue": float(total),
                                   "daily": [{"date": str(r[0]), "orders": r[1], "revenue": float(r[2] or 0)} for r in daily]})


@router.get("/cleaners")
async def get_cleaner_performance(limit: int=Query(20, ge=1, le=100),
    db: AsyncSession=Depends(get_db), _: TokenData=Depends(require_admin)):
    cleaners = (await db.execute(select(Cleaner).order_by(Cleaner.total_jobs.desc()).limit(limit))).scalars().all()
    out = []
    for c in cleaners:
        completed = await db.scalar(select(func.count(Order.id)).where(and_(Order.cleaner_id==c.id, Order.status==OrderStatus.COMPLETED))) or 0
        rate = (c.accepted_jobs / c.total_jobs * 100) if c.total_jobs else 0
        out.append({"id":c.id,"name":c.name,"phone":c.phone,"status":c.status,"total_jobs":c.total_jobs,
                    "accepted_jobs":c.accepted_jobs,"completed_jobs":completed,"completion_rate":round(rate,1),"rating":float(c.rating or 5.0)})
    return success_response(data=out)


@router.get("/properties")
async def get_property_stats(limit: int=Query(20, ge=1, le=100),
    db: AsyncSession=Depends(get_db), _: TokenData=Depends(require_admin)):
    rows = (await db.execute(
        select(Property.id, Property.name, Property.address,
               func.count(Order.id).label("total_orders"), func.sum(Order.price).label("total_revenue"))
        .outerjoin(Order, Order.property_id==Property.id)
        .group_by(Property.id, Property.name, Property.address)
        .order_by(func.count(Order.id).desc()).limit(limit)
    )).fetchall()
    return success_response(data=[{"id":r[0],"name":r[1],"address":r[2],"total_orders":r[3] or 0,
        "total_revenue":float(r[4] or 0),"avg_price":round(float(r[4] or 0)/r[3],2) if r[3] else 0} for r in rows])
