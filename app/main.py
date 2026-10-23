from fastapi import FastAPI

app = FastAPI(title="cognis")


@app.get("/health")
def health_check():
    return {"status": "ok"}
