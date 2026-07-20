from __future__ import annotations

import argparse
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path

from app.workbench_drafts import default_repo_from_origin, fetch_issue_with_gh
from app.workbench_http import make_handler
from app.workbench_runtime import WorkbenchServer

def run_server(host: str, port: int, open_browser: bool) -> None:
    forge_root = Path.cwd().resolve()
    workbench = WorkbenchServer(
        issue_fetcher=fetch_issue_with_gh,
        default_repo=default_repo_from_origin(forge_root),
        forge_root=forge_root,
    )
    server = ThreadingHTTPServer((host, port), make_handler(workbench))
    url = f"http://{host}:{server.server_port}/"
    print(f"AXIOM_FORGE_WORKBENCH: {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAXIOM_FORGE_WORKBENCH: STOP", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Start the local Axiom Forge workbench.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="Open the workbench in the default browser.")
    args = parser.parse_args(argv)

    run_server(args.host, args.port, args.open)
    return 0
