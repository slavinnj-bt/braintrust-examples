"""
ADK Web + Braintrust Tracing - Force New Sessions on Restart

SOLUTION: Generate a unique server instance ID on startup. If the browser's
instance ID doesn't match, force a new session to avoid broken traces.

Result: Clean break on restart - no duplicate/orphaned traces.
"""

import os
import time
import uuid
from pathlib import Path
from typing import Dict, Optional, Any
from urllib.parse import urlparse, parse_qs
from datetime import datetime

# Load environment first
env_file = Path(__file__).parent / "agents" / "research_agent" / ".env"
if env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(env_file)
    print(f"Loaded environment from {env_file}")

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from google.adk.cli.fast_api import get_fast_api_app
from braintrust import init_logger, current_span
from braintrust_adk import setup_adk

# Initialize Braintrust
project_name = os.environ.get("BRAINTRUST_PROJECT", "adk-web-research-agent")
braintrust_api_key = os.environ.get("BRAINTRUST_API_KEY")

if not braintrust_api_key:
    print("WARNING: BRAINTRUST_API_KEY not set - tracing will be disabled")
    logger = None
    tracing_enabled = False
else:
    setup_adk(project_name=project_name)
    print(f"setup_adk() called - ADK operations will be traced")

    logger = init_logger(project=project_name, api_key=braintrust_api_key)
    print(f"Braintrust logger initialized - session/turn spans will be created")
    tracing_enabled = True

# CRITICAL: Generate unique server instance ID on startup
SERVER_INSTANCE_ID = str(uuid.uuid4())
SERVER_START_TIME = datetime.now()

print(f"\n{'='*60}")
print(f"Server Instance ID: {SERVER_INSTANCE_ID}")
print(f"Started at: {SERVER_START_TIME.isoformat()}")
print(f"{'='*60}\n")
print("On server restart, all new requests will start fresh sessions")
print("(prevents duplicate/orphaned traces)")
print()

# Session storage
session_spans: Dict[str, Any] = {}
session_turn_counts: Dict[str, int] = {}
session_last_access: Dict[str, float] = {}
session_metadata: Dict[str, Dict[str, Any]] = {}

SESSION_EXPIRY_SECONDS = 3600
INSTANCE_COOKIE_NAME = "adk_server_instance"


def cleanup_expired_sessions():
    """Remove sessions inactive for > 1 hour."""
    if not session_spans:
        return

    current_time = time.time()
    expired_keys = [
        k for k, last_access in session_last_access.items()
        if current_time - last_access > SESSION_EXPIRY_SECONDS
    ]

    for session_key in expired_keys:
        if session_key in session_spans:
            try:
                span = session_spans[session_key]
                span.log(output={"status": "expired", "reason": "inactivity_timeout"})
                span.end()
                print(f"Expired session: {session_key}")
            except Exception as e:
                print(f"Error ending expired span: {e}")

        session_spans.pop(session_key, None)
        session_turn_counts.pop(session_key, None)
        session_last_access.pop(session_key, None)
        session_metadata.pop(session_key, None)


def get_session_key(app_name: str, user_id: str, session_id: str) -> str:
    """Create unique session key."""
    return f"{app_name}:{user_id}:{session_id}"


def get_or_create_session_span(session_key: str, metadata: Dict[str, Any]):
    """Get existing session span or create a new one."""
    if not logger:
        return None

    session_last_access[session_key] = time.time()

    if session_key in session_spans:
        span = session_spans[session_key]
        print(f"  REUSING session span (ID: {span.id[:8]}...)")
        return span

    print(f"  CREATING NEW session span")

    # Store metadata for correlation
    session_metadata[session_key] = metadata

    session_span = logger.start_span(
        name="adk_session",
        input={
            "session_key": session_key,
            "created_at": datetime.now().isoformat(),
            "server_instance_id": SERVER_INSTANCE_ID,
            **metadata
        },
        span_attributes={
            "type": "task",
            "session.id": metadata.get("session_id"),
            "session.user_id": metadata.get("user_id"),
            "session.app_name": metadata.get("app_name"),
            "server.instance_id": SERVER_INSTANCE_ID,
        }
    )

    session_spans[session_key] = session_span
    session_turn_counts[session_key] = 0

    print(f"  STORED session span (ID: {session_span.id[:8]}...)")
    print(f"  Tagged with session.id={metadata.get('session_id')}")
    print(f"  Tagged with server.instance_id={SERVER_INSTANCE_ID[:8]}...")

    return session_span


def check_server_instance(request: Request) -> bool:
    """
    Check if request is from current server instance.
    Returns True if valid, False if server was restarted.
    """
    client_instance_id = request.cookies.get(INSTANCE_COOKIE_NAME)

    if not client_instance_id:
        # First time request, no cookie yet
        return True

    if client_instance_id != SERVER_INSTANCE_ID:
        # Cookie exists but doesn't match - server was restarted
        return False

    # Cookie matches current instance
    return True


def extract_session_info(request: Request, force_new: bool = False) -> tuple[str, str, str]:
    """
    Extract session info from referer header.

    If force_new=True, generates a new session_id instead of using the one from referer.
    """
    app_name = "research_assistant"
    user_id = "default_user"
    session_id = None

    if not force_new:
        # Try to extract existing session from referer
        referer = request.headers.get("referer", "")
        if referer:
            try:
                parsed = urlparse(referer)
                referer_params = parse_qs(parsed.query)

                if "session" in referer_params:
                    session_id = referer_params["session"][0]
                if "app" in referer_params:
                    app_name = referer_params["app"][0]
                if "userId" in referer_params:
                    user_id = referer_params["userId"][0]

                if session_id:
                    print(f"  Extracted session from referer: {session_id[:12]}...")
            except Exception as e:
                print(f"  WARNING: Error parsing referer: {e}")

    # Generate new session if forced or not found
    if force_new or not session_id:
        session_id = f"session_{uuid.uuid4()}"
        if force_new:
            print(f"  FORCED NEW SESSION (server restarted): {session_id[:12]}...")
        else:
            print(f"  Generated new session (no referer): {session_id[:12]}...")

    return app_name, user_id, session_id


class BraintrustSessionMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Checks if server was restarted (via instance cookie)
    2. Forces new session if restart detected
    3. Creates session/turn spans with proper tagging
    """

    async def dispatch(self, request: Request, call_next):
        cleanup_expired_sessions()

        is_run = "/run" in request.url.path
        is_sse = "/run_sse" in request.url.path

        print(f"\n{'='*80}")
        print(f"Request: {request.method} {request.url.path}")
        print(f"Type: {'SSE' if is_sse else 'Standard' if is_run else 'Other'}")

        if not (is_run or is_sse):
            print(f"  Skipping (not a run endpoint)")
            print(f"{'='*80}\n")
            return await call_next(request)

        if not tracing_enabled:
            print(f"  WARNING: Tracing disabled")
            print(f"{'='*80}\n")
            return await call_next(request)

        # Check if server was restarted
        is_valid_instance = check_server_instance(request)

        if not is_valid_instance:
            print(f"  SERVER RESTART DETECTED")
            print(f"  Client has old instance ID")
            print(f"  Forcing new session to avoid broken traces")

        # Extract session info (force new if server restarted)
        app_name, user_id, session_id = extract_session_info(request, force_new=not is_valid_instance)
        session_key = get_session_key(app_name, user_id, session_id)

        print(f"  Session key: {session_key}")

        # Get or create session span
        session_span = get_or_create_session_span(
            session_key,
            metadata={
                "app_name": app_name,
                "user_id": user_id,
                "session_id": session_id,
                "server_instance_id": SERVER_INSTANCE_ID,
            }
        )

        # Create turn span as child
        session_turn_counts[session_key] = session_turn_counts.get(session_key, 0) + 1
        turn_number = session_turn_counts[session_key]

        turn_span = session_span.start_span(
            name=f"turn_{turn_number}",
            input={
                "turn_number": turn_number,
                "session_key": session_key,
                "timestamp": datetime.now().isoformat()
            },
            span_attributes={
                "type": "task",
                "turn.number": turn_number,
                "session.id": session_id,
                "session.user_id": user_id,
                "session.app_name": app_name,
                "server.instance_id": SERVER_INSTANCE_ID,
            }
        )

        print(f"  Created turn {turn_number} (ID: {turn_span.id[:8]}...)")

        # Set as current
        turn_span.set_current()

        try:
            # Process the request
            print(f"  Calling ADK...")
            response = await call_next(request)
            print(f"  ADK call completed")

            # Tag ADK spans if possible
            try:
                adk_span = current_span()
                if adk_span and adk_span.id != turn_span.id:
                    adk_span.set_attributes({
                        "session.id": session_id,
                        "session.user_id": user_id,
                        "session.app_name": app_name,
                        "turn.number": turn_number,
                        "server.instance_id": SERVER_INSTANCE_ID,
                        "correlation.turn_span_id": turn_span.id,
                        "correlation.session_span_id": session_span.id if session_span else None,
                    })
                    print(f"  Tagged ADK span")
            except Exception as e:
                print(f"  WARNING: Could not tag ADK span: {e}")

            # Set instance cookie on response
            if isinstance(response, StreamingResponse):
                # For streaming, we'll wrap it
                return await self.wrap_streaming_response(
                    response, turn_span, session_key, not is_valid_instance
                )

            # For non-streaming, set cookie and end span
            response.set_cookie(
                key=INSTANCE_COOKIE_NAME,
                value=SERVER_INSTANCE_ID,
                max_age=SESSION_EXPIRY_SECONDS,
                httponly=True,
                samesite="lax"
            )

            turn_span.log(output={"status": "completed", "streaming": False})
            turn_span.end()
            print(f"  Turn span ended")

            if not is_valid_instance:
                print(f"\n  New session started after restart")
                print(f"  Old conversations will remain as separate traces")

            print(f"{'='*80}\n")

            return response

        except Exception as e:
            turn_span.log(output={"error": str(e), "error_type": type(e).__name__})
            turn_span.end()
            print(f"  ERROR: {e}")
            print(f"{'='*80}\n")
            raise

    async def wrap_streaming_response(
        self, response: StreamingResponse, turn_span, session_key: str, was_restart: bool
    ):
        """Wrap streaming response to set cookie and end span."""
        original_iterator = response.body_iterator
        chunk_count = 0

        async def wrapped_iterator():
            nonlocal chunk_count
            try:
                async for chunk in original_iterator:
                    chunk_count += 1
                    yield chunk
            finally:
                turn_span.log(output={"streaming": True, "chunks": chunk_count})
                turn_span.end()
                print(f"  Turn span ended (streaming, {chunk_count} chunks)")

                if was_restart:
                    print(f"\n  New session started after restart")

                print(f"{'='*80}\n")

        # Create new response with cookie
        new_response = StreamingResponse(
            wrapped_iterator(),
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type
        )

        # Set instance cookie
        new_response.set_cookie(
            key=INSTANCE_COOKIE_NAME,
            value=SERVER_INSTANCE_ID,
            max_age=SESSION_EXPIRY_SECONDS,
            httponly=True,
            samesite="lax"
        )

        return new_response


# Create the ADK FastAPI app
print("="*60)
print("Creating ADK FastAPI app (Force New Sessions on Restart)")
print("="*60)

agents_dir = Path(__file__).parent / "agents"
adk_app = get_fast_api_app(agents_dir=str(agents_dir), web=True)
adk_app.add_middleware(BraintrustSessionMiddleware)

print(f"ADK app created")
print(f"Middleware added")
print(f"Server instance tracking enabled")
print("="*60 + "\n")

app = adk_app


@app.on_event("shutdown")
async def shutdown_event():
    """End all active session spans on shutdown."""
    print("\n" + "="*60)
    print("Shutting down - ending active session spans")

    for session_key, span in list(session_spans.items()):
        try:
            span.log(output={
                "status": "server_shutdown",
                "server_instance_id": SERVER_INSTANCE_ID
            })
            span.end()
            print(f"  Ended session span: {session_key}")
        except Exception as e:
            print(f"  ERROR: ending span: {e}")

    session_spans.clear()
    session_turn_counts.clear()
    session_last_access.clear()
    session_metadata.clear()

    print("="*60 + "\n")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 3000))

    print(f"Starting ADK server on port {port}")
    print(f"Web UI: http://localhost:{port}/dev-ui/\n")

    print("Session Management:")
    print("  - Server instance tracking enabled")
    print("  - On restart: Forces new sessions automatically")
    print("  - Result: Clean traces, no duplicates or orphans")
    print(f"  - Session expiry: {SESSION_EXPIRY_SECONDS}s\n")

    print(f"Server Instance: {SERVER_INSTANCE_ID}\n")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=False
    )
