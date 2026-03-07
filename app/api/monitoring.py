"""
監控指標導出 (無外部依賴)
"""
from fastapi import APIRouter, Response
import time

from app.core.monitoring import Metrics

router = APIRouter()


@router.get("/metrics")
async def prometheus_metrics():
    """Prometheus 格式指標 (簡化版)"""
    stats = Metrics.get_stats()
    
    lines = []
    lines.append("# HELP smartclean_http_requests_total Total HTTP requests")
    lines.append("# TYPE smartclean_http_requests_total counter")
    
    if "endpoints" in stats:
        for endpoint, data in stats["endpoints"].items():
            requests = data.get("requests", 0)
            lines.append(f'smartclean_http_requests_total{{endpoint="{endpoint}"}} {requests}')
    
    lines.append("")
    lines.append("# HELP smartclean_ws_connections_total Total WebSocket connections")
    lines.append("# TYPE smartclean_ws_connections_total gauge")
    lines.append(f'smartclean_ws_connections_total {stats.get("websocket", {}).get("total_connections", 0)}')
    
    lines.append("")
    lines.append("# HELP smartclean_ws_messages_total Total WebSocket messages")
    lines.append("# TYPE smartclean_ws_messages_total gauge")
    lines.append(f'smartclean_ws_messages_total {stats.get("websocket", {}).get("total_messages", 0)}')
    
    return Response(content="\n".join(lines), media_type="text/plain")


@router.get("/metrics/simple")
async def simple_metrics():
    """簡化指標"""
    stats = Metrics.get_stats()
    
    return {
        "requests": sum(d.get("requests", 0) for d in stats.get("endpoints", {}).values()),
        "errors": sum(d.get("errors", 0) for d in stats.get("endpoints", {}).values()),
        "websocket_connections": stats.get("websocket", {}).get("total_connections", 0),
        "websocket_messages": stats.get("websocket", {}).get("total_messages", 0),
        "endpoints": stats.get("endpoints", {}),
        "timestamp": stats.get("timestamp")
    }
