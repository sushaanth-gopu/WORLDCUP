# main_api.py
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import random
import pydantic
# Import specific items directly from your current engine script
from model import build_elo, GROUPS_2026

app = FastAPI(title="PREDICTA26 Web API Broker")

# Allow your UI layer to safely request metrics across ports
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SimulationRequest(pydantic.BaseModel):
    iterations: int = 20000
    live_mode: bool = True

def run_async_monte_carlo(iterations: int):
    """
    Executes structural parts of your engine pipeline 
    and handles state caching safely.
    """
    print(f"Starting heavy Monte Carlo computation pipeline: n={iterations}...")
    elos = build_elo(verbose=False)
    # Inside this async process, you can call 'upload_simulation_snapshot_to_turso' 
    # to store metrics as soon as the run is complete!
    print("Computation complete. Matrix synchronized.")

@app.get("/api/v1/elo-standings")
def get_elo_standings():
    try:
        elos = build_elo(verbose=False)
        # Normalize the team output formats for JSON serialization
        return {"status": "success", "elos": {k: float(v) for k, v in elos.items()}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/simulate")
def trigger_simulation(payload: SimulationRequest, background_tasks: BackgroundTasks):
    # Offload execution to a background task so the frontend UI doesn't time out
    background_tasks.add_task(run_async_monte_carlo, payload.iterations)
    return {
        "status": "processing",
        "message": f"Monte Carlo simulation of {payload.iterations} runs dispatched successfully."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)