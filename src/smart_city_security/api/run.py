from __future__ import annotations

import os

import uvicorn

from .app import create_app


def main() -> None:
    token = os.environ.get("SMART_CITY_ADMIN_TOKEN")
    if not token:
        raise ValueError("SMART_CITY_ADMIN_TOKEN environment variable is not set")

    uvicorn.run(create_app(admin_token=token), host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
