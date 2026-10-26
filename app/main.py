from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.services.task_service import create_task as create_task_service

app = FastAPI(title="AgentForge")


class TaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=1000)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/tasks")
def create_task(request: TaskRequest):
    return create_task_service(request.task)
