from datetime import datetime
from pydantic import BaseModel, Field, field_validator

class RegisterRequest(BaseModel): email: str; password: str=Field(min_length=8); tenant_name: str|None=Field(default=None, min_length=1, max_length=100)
class LoginRequest(BaseModel): email: str; password: str=Field(min_length=8)
class AuthResponse(BaseModel): token: str
class StepDefinition(BaseModel):
    name: str=Field(min_length=1, max_length=200)
    action: str=Field(min_length=1, max_length=100)
    provider_idempotency_key: str|None=Field(default=None, max_length=255)
    retries: int=Field(default=3, ge=1, le=20)
    timeout_seconds: int=Field(default=300, ge=1, le=86400)
    backoff_seconds: int=Field(default=2, ge=1, le=3600)
class WorkflowCreate(BaseModel):
    name: str=Field(min_length=1, max_length=200)
    input: dict = Field(default_factory=dict)
    steps: list[StepDefinition]=Field(min_length=1, max_length=100)
    idempotency_key: str|None=Field(default=None, max_length=255)
class StepOut(BaseModel): id:int; position:int; name:str; status:str; attempts:int; error:str|None=None; output:dict|None=None
class WorkflowOut(BaseModel): id:str; name:str; status:str; input:dict; created_at:datetime; started_at:datetime|None; completed_at:datetime|None; error:str|None; steps:list[StepOut]
