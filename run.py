import os
import warnings
import uvicorn

# Suppress urllib3 InsecureRequestWarning at process start so it applies to subprocesses
try:
    # Environment variable ensures child processes also inherit the warning filter
    # Use a broad suppression to avoid subprocess '-W' parsing issues; keep an in-process filter too
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    try:
        from urllib3.exceptions import InsecureRequestWarning
        warnings.filterwarnings("ignore", category=InsecureRequestWarning)
    except Exception:
        pass
except Exception:
    # Best-effort suppression; continue if urllib3 isn't available
    pass

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
