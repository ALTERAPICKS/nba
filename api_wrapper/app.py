from fastapi import FastAPI
from nba_client import get_team_dashboard
from cache import cached_response

app = FastAPI(title="ALTERAPICKS NBA API")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/team-dashboard/{team_id}")
@cached_response(ttl=3600)
def team_dashboard(team_id: int, last_n_games: int = 5):
    return get_team_dashboard(team_id, last_n_games)

