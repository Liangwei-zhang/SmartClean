"""監控端點 — 需要 Bearer Token"""
from fastapi import APIRouter, Depends, Response
from app.core.auth      import require_bearer
from app.core.monitoring import Metrics

router = APIRouter()

@router.get("/metrics", dependencies=[Depends(require_bearer)])
async def prometheus_metrics():
    stats = Metrics.get_stats()
    lines = ["# HELP smartclean_http_requests_total Total HTTP requests",
             "# TYPE smartclean_http_requests_total counter"]
    for endpoint, data in stats.get("endpoints", {}).items():
        lines.append(f'smartclean_http_requests_total{{endpoint="{endpoint}"}} {data.get("requests",0)}')
    lines += ["", "# HELP smartclean_ws_connections_total WebSocket connections",
              "# TYPE smartclean_ws_connections_total gauge",
              f'smartclean_ws_connections_total {stats.get("websocket",{}).get("total_connections",0)}']
    return Response(content="\n".join(lines), media_type="text/plain")

@router.get("/metrics/simple", dependencies=[Depends(require_bearer)])
async def simple_metrics():
    stats = Metrics.get_stats()
    return {"requests": sum(d.get("requests",0) for d in stats.get("endpoints",{}).values()),
            "errors": sum(d.get("errors",0) for d in stats.get("endpoints",{}).values()),
            "websocket_connections": stats.get("websocket",{}).get("total_connections",0),
            "endpoints": stats.get("endpoints",{}), "timestamp": stats.get("timestamp")}
