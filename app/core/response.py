from fastapi.responses import ORJSONResponse as BaseORJSONResponse


class ORJSONResponse(BaseORJSONResponse):
    """ORJSON 響應 - C 級別極速序列化"""
    media_type = "application/json"
    
    def __init__(self, content, status_code=200, **kwargs):
        super().__init__(content=content, status_code=status_code, **kwargs)


def success_response(data=None, message: str = "Success", **kwargs):
    """標準成功響應"""
    content = {"success": True, "message": message}
    if data is not None:
        content["data"] = data
    content.update(kwargs)
    return ORJSONResponse(content)


def error_response(message: str, status_code: int = 400, **kwargs):
    """標準錯誤響應"""
    content = {"success": False, "message": message}
    content.update(kwargs)
    return ORJSONResponse(content, status_code=status_code)
