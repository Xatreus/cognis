def create_task(task: str) -> dict:
    return {
        "message": "Task received",
        "task": task,
        "status": "pending",
    }
