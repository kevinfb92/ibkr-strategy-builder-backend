# ibkr-strategy-builder-backend

A Python backend using FastAPI to serve REST endpoints and WebSocket live updates for the IBKR Strategy Builder frontend.

## Features
- FastAPI for REST API and WebSocket
- Sample endpoints for health check and echo
- Standard tools: pytest, black, flake8

## Quickstart
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the server:
   ```bash
   uvicorn app.main:app --reload
   ```
3. Test endpoints:
   - GET `/health`
   - POST `/echo`
   - WebSocket `/ws`

## Development
- Format code: `black .`
- Lint code: `flake8 .`
- Run tests: `pytest`

---

Replace sample endpoints with your business logic as needed.
