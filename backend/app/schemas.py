from typing import Any, Optional
from pydantic import BaseModel, Field

class JobView(BaseModel):
    job_id: str
    status: str
    progress: float = 0
    message: str = ''
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
