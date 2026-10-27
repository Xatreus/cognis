import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from app.observability.logging import configure_logging
from app.schemas.evaluations import EvaluationRequest, EvaluationResponse
from app.engine.evaluator import run_demo_evaluation
from app.services.task_service import create_task as create_task_service

configure_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('Cognis API starting')
    yield
    logger.info('Cognis API stopping')

app = FastAPI(title='Cognis', version='0.1.0', lifespan=lifespan)

class TaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=1000)

@app.get('/health/live', tags=['health'])
def liveness():
    return {'status': 'alive'}

@app.get('/health/ready', tags=['health'])
def readiness():
    return {'status': 'ready'}

@app.get('/health', tags=['health'], include_in_schema=False)
def health_check():
    return {'status': 'ok'}

@app.post('/tasks', tags=['tasks'])
def create_task(request: TaskRequest):
    return create_task_service(request.task)

@app.post('/evaluations', response_model=EvaluationResponse, tags=['evaluations'])
def create_evaluation(request: EvaluationRequest):
    try:
        return run_demo_evaluation(include_traces=request.include_traces)
    except Exception as exc:
        logger.exception('Evaluation execution failed')
        raise HTTPException(status_code=500, detail='Evaluation execution failed') from exc

@app.get('/', include_in_schema=False)
def root():
    return JSONResponse({'service': 'Cognis', 'docs': '/docs', 'health': '/health/ready'})
