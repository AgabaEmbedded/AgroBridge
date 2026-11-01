"""Ask the AgroBridge /debug/ask endpoint from a terminal.

Examples:
    python debug_client.py "What causes yellow maize leaves?"
    python debug_client.py --top-k 6 "How do I prevent Newcastle disease?"
    python debug_client.py            # interactive prompt (blank line or "quit" exits)
    python debug_client.py --conversation farm-42 "my name is Sunday"
    python debug_client.py --conversation farm-42 --reset

The client sends a conversation id on every request, so the app keeps short-term memory
for the session. Interactive mode generates one id per run; reuse it across runs with
--conversation. --reset clears that id's remembered turns before the first question.

Local requests need no token. For remote calls, set DEBUG_API_TOKEN in `.env` (server)
and export the same value here via --token or the DEBUG_API_TOKEN environment variable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from typing import Any


def ask(
    url: str,
    question: str,
    top_k: int | None,
    token: str,
    conversation: str,
    reset: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"question": question, "conversation_id": conversation}
    if top_k is not None:
        payload["top_k"] = top_k
    if reset:
        payload["reset_history"] = True
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Debug-Token"] = token

    request = urllib.request.Request(
        url.rstrip("/") + "/debug/ask",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("detail", body)
        except json.JSONDecodeError:
            detail = body
        raise SystemExit(f"HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Cannot reach {url}: {exc.reason}. Start the server with `python app.py`."
        ) from None


def print_result(result: dict[str, Any]) -> None:
    timings = result.get("timings", {})
    print(f"\nstage: {result.get('stage')} | total: {result.get('total_ms')} ms "
          f"(retrieval {timings.get('retrieval_ms')} ms, llm {timings.get('llm_ms')} ms)")
    print(f"history: {result.get('history_used', 0)} prior message(s) sent to the model")
    index = result.get("index", {})
    print(f"index: {index.get('collection')} -> {index.get('chunks')} chunks")

    hits = result.get("hits", [])
    used = sum(1 for hit in hits if hit.get("used"))
    print(f"retrieved: {len(hits)} chunk(s), {used} above the relevance threshold")
    for position, hit in enumerate(hits, start=1):
        marker = "*" if hit.get("used") else "-"
        print(f"  {marker} [{position}] {hit.get('source')} chunk {hit.get('chunk')} "
              f"distance={hit.get('distance')}")
        preview = " ".join(str(hit.get("preview", "")).split())
        if preview:
            print(f"        {preview[:160]}")

    print("\nanswer:\n" + str(result.get("answer", "")).strip() + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Query AgroBridge's debug endpoint.")
    parser.add_argument("question", nargs="*", help="question to ask; omit for interactive mode")
    parser.add_argument("--url", default=os.getenv("AGROBRIDGE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--token", default=os.getenv("DEBUG_API_TOKEN", ""))
    parser.add_argument(
        "--conversation",
        default=None,
        help="conversation id to reuse memory across runs (default: fresh per run)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="clear this conversation's remembered turns before asking",
    )
    parser.add_argument("--json", action="store_true", help="print the raw JSON response")
    args = parser.parse_args()

    conversation = args.conversation or f"debug-{uuid.uuid4().hex[:10]}"
    pending_reset = args.reset

    def run_one(question: str) -> None:
        nonlocal pending_reset
        result = ask(args.url, question, args.top_k, args.token, conversation, pending_reset)
        pending_reset = False
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print_result(result)

    one_shot = " ".join(args.question).strip()
    if one_shot:
        print(f"conversation: {conversation} (reuse with --conversation)", file=sys.stderr)
        try:
            run_one(one_shot)
        except SystemExit as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0

    print(f"AgroBridge debug client -> {args.url}")
    print(f"conversation: {conversation} (reuse with --conversation; blank line or 'quit' exits)")
    while True:
        try:
            question = input("\nquestion> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not question or question.lower() in {"quit", "exit"}:
            return 0
        try:
            run_one(question)
        except SystemExit as exc:
            print(exc)
            continue


if __name__ == "__main__":
    sys.exit(main())
