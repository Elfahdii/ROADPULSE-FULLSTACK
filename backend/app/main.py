from __future__ import annotations
from contextlib import asynccontextmanager
import shutil
import threading
import uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .config import FRONTEND_ORIGIN, UPLOAD_DIR, EVIDENCE_DIR
from .schemas import JobView
from .video_analysis import analyze_video
from .model_service import detector
from .geo import gps_tool_status
from .storage import get_survey, init_db, list_surveys, save_survey


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Pay the model import/initialization cost once during backend startup so
    # the first user analysis begins immediately after its upload is saved.
    detector.warmup()
    yield


app = FastAPI(title='RoadPulse API', version='2.0.0', lifespan=lifespan)
origins = [o.strip() for o in FRONTEND_ORIGIN.split(',') if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ['http://localhost:5173'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.mount('/evidence', StaticFiles(directory=str(EVIDENCE_DIR)), name='evidence')
init_db()

_jobs = {}
_lock = threading.Lock()

def set_job(job_id, **changes):
    with _lock:
        _jobs[job_id].update(changes)

def save_upload(upload: UploadFile, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('wb') as f:
        shutil.copyfileobj(upload.file, f)

def run_job(job_id: str, video_path: Path, original_filename: str, gps_path: Path | None, motion_path: Path | None):
    def progress(p, message):
        set_job(job_id, progress=float(p), message=message)

    try:
        set_job(job_id, status='running', progress=3.0, message='Loading model and video…')
        result = analyze_video(
            video_path=video_path,
            gps_json=gps_path,
            motion_json=motion_path,
            job_id=job_id,
            original_filename=original_filename,
            progress_cb=progress,
        )
        save_survey(job_id, result)
        set_job(job_id, status='completed', progress=100.0, message='Analysis complete', result=result)
    except Exception as e:
        set_job(job_id, status='failed', error=str(e), message='Analysis failed')

@app.get('/api/health')
def health():
    model = detector.load()
    return {
        'ok': True,
        'model_loaded': model is not None,
        'model_warmed_up': detector.warmed_up,
        'model_error': detector.error,
        'model_warmup_error': detector.warmup_error,
        'model_classes': getattr(model, 'names', None) if model is not None else None,
        'gps_capabilities': gps_tool_status(),
    }

@app.post('/api/jobs/analysis')
def create_analysis_job(
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    gps_json: UploadFile | None = File(None),
    motion_json: UploadFile | None = File(None),
):
    if not video.filename:
        raise HTTPException(400, 'A road video is required.')

    job_id = str(uuid.uuid4())
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(video.filename).suffix or '.mp4'
    video_path = job_dir / f'video{suffix}'
    save_upload(video, video_path)

    gps_path = None
    motion_path = None
    if gps_json:
        gps_path = job_dir / 'gps.json'
        save_upload(gps_json, gps_path)
    if motion_json:
        motion_path = job_dir / 'motion.json'
        save_upload(motion_json, motion_path)

    with _lock:
        _jobs[job_id] = {
            'job_id': job_id,
            'status': 'queued',
            'progress': 0.0,
            'message': 'Queued',
            'error': None,
            'result': None,
        }

    background_tasks.add_task(
        run_job,
        job_id,
        video_path,
        video.filename,
        gps_path,
        motion_path,
    )
    return {'job_id': job_id}

@app.get('/api/jobs/{job_id}', response_model=JobView)
def get_job(job_id: str):
    with _lock:
        job = _jobs.get(job_id)
        if job:
            return dict(job)

    # Completed surveys survive backend restarts. If the in-memory job is gone,
    # serve the persisted result as a completed job.
    persisted = get_survey(job_id)
    if persisted:
        return {
            'job_id': job_id,
            'status': 'completed',
            'progress': 100.0,
            'message': 'Analysis complete',
            'error': None,
            'result': persisted['result'],
        }
    raise HTTPException(404, 'Job not found')


@app.get('/api/surveys')
def surveys(limit: int = 100):
    return {'surveys': list_surveys(limit=limit)}


@app.get('/api/surveys/{survey_id}')
def survey_detail(survey_id: str):
    survey = get_survey(survey_id)
    if not survey:
        raise HTTPException(404, 'Survey not found')
    return survey
