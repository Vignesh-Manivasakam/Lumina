import uuid
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from starlette.responses import JSONResponse

SESSION_HEADER = "X-Session-ID"

class SessionIsolationMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces multi-tenant session isolation.
    Validates X-Session-ID header as a valid UUID v4 string.
    Injects request.state.session_id for downstream route handlers.
    """

    EXEMPT_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc", "/mcp")

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in self.EXEMPT_PREFIXES):
            return await call_next(request)

        session_id = request.headers.get(SESSION_HEADER)

        if session_id:
            try:
                # Validate UUID v4 format
                val = uuid.UUID(session_id, version=4)
                request.state.session_id = str(val)
            except ValueError:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid X-Session-ID UUID format."}
                )
        else:
            # Issue a new session UUID v4 if omitted
            request.state.session_id = str(uuid.uuid4())

        response = await call_next(request)
        response.headers[SESSION_HEADER] = request.state.session_id
        return response
