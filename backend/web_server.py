import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "backend.web_app:app",
        host=os.getenv("MINIOPENCLAW_HOST", "0.0.0.0"),
        port=int(os.getenv("MINIOPENCLAW_PORT", "8000")),
        reload=False,
    )
