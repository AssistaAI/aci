"""RQ queue management for background job processing."""

from typing import Any

# TODO: Add RQ to dependencies in pyproject.toml:
# rq>=1.15.0
# redis>=5.0.0

try:
    from redis import Redis
    from rq import Queue
    from rq.job import Job
except ImportError as e:
    raise ImportError(
        "RQ and Redis are required for the triggers module. "
        "Add 'rq>=1.15.0' and 'redis>=5.0.0' to pyproject.toml dependencies."
    ) from e

from .settings import settings
from .normalize import NormalizedEvent
from .logging import log_event_enqueued, get_triggers_logger

logger = get_triggers_logger()

# Global Redis connection
_redis_conn = None
_queue = None


def get_redis_connection() -> Redis:
    """Get or create Redis connection."""
    global _redis_conn
    if _redis_conn is None:
        _redis_conn = Redis.from_url(settings.redis_url)
    return _redis_conn


def get_triggers_queue() -> Queue:
    """Get or create RQ queue for triggers."""
    global _queue
    if _queue is None:
        redis_conn = get_redis_connection()
        _queue = Queue(name="triggers", connection=redis_conn)
    return _queue


def enqueue_event(normalized_event: NormalizedEvent, delay: int = 0) -> Job:
    """
    Enqueue a normalized event for background processing.
    
    Args:
        normalized_event: The normalized event to process
        delay: Optional delay in seconds before processing
        
    Returns:
        RQ Job instance
    """
    queue = get_triggers_queue()
    
    # Convert dataclass to dict for JSON serialization
    event_data = {
        "provider": normalized_event.provider,
        "type": normalized_event.type,
        "subject_id": normalized_event.subject_id,
        "ts": normalized_event.ts.isoformat(),
        "data": normalized_event.data
    }
    
    # Enqueue the job
    job = queue.enqueue(
        "aci.triggers.worker.process_normalized_event",
        event_data,
        job_timeout="5m",  # 5 minute timeout
        retry=3,  # Retry failed jobs 3 times
        job_id=f"{normalized_event.provider}:{normalized_event.subject_id}:{normalized_event.ts.timestamp()}",
        delay=delay
    )
    
    log_event_enqueued(
        provider=normalized_event.provider,
        event_type=normalized_event.type,
        event_id=normalized_event.subject_id,
        job_id=job.id,
        delay=delay
    )
    
    logger.info(
        f"Event enqueued for processing: {normalized_event.type} "
        f"for {normalized_event.subject_id} (job_id: {job.id})"
    )
    
    return job


def enqueue_multiple_events(normalized_events: list[NormalizedEvent], delay: int = 0) -> list[Job]:
    """
    Enqueue multiple normalized events for background processing.
    
    Args:
        normalized_events: List of normalized events to process
        delay: Optional delay in seconds before processing
        
    Returns:
        List of RQ Job instances
    """
    jobs = []
    for event in normalized_events:
        job = enqueue_event(event, delay=delay)
        jobs.append(job)
    
    logger.info(f"Enqueued {len(jobs)} events for processing")
    return jobs


def get_job_status(job_id: str) -> dict[str, Any]:
    """
    Get the status of a background job.
    
    Args:
        job_id: The RQ job ID
        
    Returns:
        Dictionary with job status information
    """
    redis_conn = get_redis_connection()
    job = Job.fetch(job_id, connection=redis_conn)
    
    return {
        "id": job.id,
        "status": job.get_status(),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "ended_at": job.ended_at.isoformat() if job.ended_at else None,
        "result": job.result,
        "exc_info": job.exc_info,
        "meta": job.meta,
        "retry_attempts": job.retries_left if hasattr(job, 'retries_left') else None,
    }


def get_queue_stats() -> dict[str, Any]:
    """
    Get statistics about the triggers queue.
    
    Returns:
        Dictionary with queue statistics
    """
    queue = get_triggers_queue()
    
    return {
        "name": queue.name,
        "length": len(queue),
        "started_jobs": len(queue.started_job_registry),
        "finished_jobs": len(queue.finished_job_registry),
        "failed_jobs": len(queue.failed_job_registry),
        "scheduled_jobs": len(queue.scheduled_job_registry),
        "deferred_jobs": len(queue.deferred_job_registry),
    }


def clear_failed_jobs() -> int:
    """
    Clear all failed jobs from the queue.
    
    Returns:
        Number of jobs cleared
    """
    queue = get_triggers_queue()
    failed_registry = queue.failed_job_registry
    job_count = len(failed_registry)
    failed_registry.clear()
    
    logger.info(f"Cleared {job_count} failed jobs from triggers queue")
    return job_count


def requeue_failed_jobs() -> int:
    """
    Requeue all failed jobs.
    
    Returns:
        Number of jobs requeued
    """
    queue = get_triggers_queue()
    failed_registry = queue.failed_job_registry
    job_ids = list(failed_registry.get_job_ids())
    
    requeued_count = 0
    for job_id in job_ids:
        try:
            queue.requeue(job_id)
            requeued_count += 1
        except Exception as e:
            logger.error(f"Failed to requeue job {job_id}: {e}")
    
    logger.info(f"Requeued {requeued_count} failed jobs")
    return requeued_count