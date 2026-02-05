"""Main entry point for the ecommerce negotiation agent."""

import asyncio
import json
import os
import subprocess
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # Load .env into environment variables

from agents import Runner
import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Global reference to Next.js subprocess
nextjs_process = None

from src.agents.orchestrator import orchestrator_agent
from src.agents.product_research import product_research_agent
from src.agents.contact_discovery import contact_discovery_agent
from src.agents.negotiator import negotiator_agent
from src.state.store import StateStore
from src.state.models import ProductRequest, PurchaseSession
from src.bridge.whatsapp_client import create_whatsapp_client
from src.config.settings import settings
from src.observability import ObservabilityHooks, TraceStore, set_trace_store
from src.api.routes.traces import router as traces_router
from src.api.routes.agent import router as agent_router
from src.api.routes.sellers import router as sellers_router
from src.api.routes.analytics import router as analytics_router
from src.api.routes.geo import router as geo_router
from src.api.routes.shopping_list import router as shopping_list_router
from src.api.routes.logs import router as logs_router
from src.api.routes.criteria import router as criteria_router
from src.api.middleware import RequestLoggingMiddleware
from src.db.base import init_db
from src.db import models as db_models  # noqa: F401 - Import to register models with Base
from src.logging import configure_production_logging

# Configure structured logging for production
configure_production_logging()

logger = structlog.get_logger()

# Create FastAPI app for observability dashboard
app = FastAPI(title="Agent Observability API")

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Add CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "*"],  # Allow all in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(traces_router)
app.include_router(agent_router)
app.include_router(sellers_router)
app.include_router(analytics_router)
app.include_router(geo_router)
app.include_router(shopping_list_router)
app.include_router(logs_router)
app.include_router(criteria_router)


@app.get("/health")
async def health_check():
    """Health check endpoint for Railway/container orchestration."""
    return {"status": "healthy"}


@app.get("/debug/db")
async def debug_db():
    """Debug endpoint to check database configuration."""
    from src.config.settings import settings
    from src.db.base import get_database_url

    db_url = get_database_url()
    # Mask password in URL for security
    masked_url = db_url
    if "@" in db_url:
        # postgres://user:pass@host -> postgres://user:***@host
        parts = db_url.split("@")
        prefix = parts[0]
        if ":" in prefix:
            prefix_parts = prefix.rsplit(":", 1)
            masked_url = f"{prefix_parts[0]}:***@{parts[1]}"

    result = {
        "database_url_configured": bool(settings.database_url),
        "is_postgres": settings.is_postgres,
        "resolved_url": masked_url[:50] + "..." if len(masked_url) > 50 else masked_url,
    }

    # Try to connect
    try:
        from sqlalchemy import text
        from src.db.session import get_db_session
        async with get_db_session() as session:
            await session.execute(text("SELECT 1"))
            result["connection"] = "ok"
    except Exception as e:
        result["connection"] = "failed"
        result["error"] = str(e)

    return result


@app.on_event("startup")
async def startup_event():
    """Initialize database and start Next.js on application startup."""
    global nextjs_process
    from src.config.settings import settings

    # Start Next.js subprocess in production
    if settings.environment == "production":
        frontend_dir = Path(__file__).parent.parent / "frontend"
        if not frontend_dir.exists():
            frontend_dir = Path("/app/frontend")  # Docker path

        logger.info("Starting Next.js subprocess", frontend_dir=str(frontend_dir))

        try:
            # Set PORT=3000 for Next.js, regardless of Railway's PORT
            nextjs_env = os.environ.copy()
            nextjs_env["PORT"] = "3000"

            nextjs_process = subprocess.Popen(
                ["npm", "run", "start"],
                cwd=str(frontend_dir),
                env=nextjs_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )

            # Wait for Next.js to be ready (non-blocking check)
            import httpx
            for i in range(30):
                try:
                    async with httpx.AsyncClient() as client:
                        response = await client.get("http://localhost:3000", timeout=2.0)
                        if response.status_code < 500:
                            logger.info("Next.js started successfully", attempts=i+1)
                            break
                except Exception:
                    pass

                # Check if process died
                if nextjs_process.poll() is not None:
                    stdout, _ = nextjs_process.communicate()
                    logger.error(
                        "Next.js process died during startup",
                        return_code=nextjs_process.returncode,
                        output=stdout.decode() if stdout else None,
                    )
                    break

                await asyncio.sleep(1)
            else:
                logger.warning("Next.js may not be fully ready after 30 seconds")

        except Exception as e:
            logger.error("Failed to start Next.js", error=str(e))

    # Initialize database
    try:
        await init_db()
        logger.info(
            "Database initialized on startup",
            is_postgres=settings.is_postgres,
            database_url=settings.database_url[:30] + "..." if settings.database_url else None,
        )
    except Exception as e:
        logger.error(
            "Failed to initialize database",
            error=str(e),
            is_postgres=settings.is_postgres,
        )
        # Don't raise - allow health check to work, app can still serve static content
        # Database-dependent endpoints will fail gracefully


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up Next.js subprocess on shutdown."""
    global nextjs_process
    if nextjs_process and nextjs_process.poll() is None:
        logger.info("Stopping Next.js subprocess")
        nextjs_process.terminate()
        try:
            nextjs_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            nextjs_process.kill()


# Initialize global trace store
trace_store = TraceStore()
set_trace_store(trace_store)

# Reverse proxy to Next.js frontend (runs on port 3000)
# This allows FastAPI to serve both API and frontend from a single port
import httpx
from starlette.requests import Request
from starlette.responses import StreamingResponse, Response

NEXTJS_URL = "http://localhost:3000"

@app.api_route("/{path:path}", methods=["GET", "HEAD"])
async def proxy_to_nextjs(request: Request, path: str):
    """Proxy non-API requests to Next.js server."""
    # Don't proxy API routes (they're handled by routers above)
    # These are the actual API prefixes, not frontend pages
    api_prefixes = (
        "agent/",       # /agent/*
        "traces/",      # /traces/*
        "api/",         # /api/sellers/*, /api/criteria/*, etc.
        "health",       # /health
        "debug/",       # /debug/*
    )
    if path.startswith(api_prefixes):
        # This shouldn't happen since routers are registered first, but just in case
        return Response(status_code=404)

    # Build the target URL
    target_url = f"{NEXTJS_URL}/{path}"
    if request.query_params:
        target_url += f"?{request.query_params}"

    try:
        async with httpx.AsyncClient() as client:
            # Forward the request to Next.js
            response = await client.request(
                method=request.method,
                url=target_url,
                headers={k: v for k, v in request.headers.items() if k.lower() not in ("host", "content-length")},
                timeout=30.0,
            )

            # Stream the response back
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers={k: v for k, v in response.headers.items() if k.lower() not in ("content-encoding", "transfer-encoding", "content-length")},
                media_type=response.headers.get("content-type"),
            )
    except httpx.ConnectError:
        # Next.js not running - return a helpful error
        return Response(
            content="Frontend server not running. Start Next.js with: cd frontend && npm run start",
            status_code=503,
            media_type="text/plain",
        )

# Also proxy the root path
@app.get("/")
async def proxy_root(request: Request):
    """Proxy root to Next.js."""
    return await proxy_to_nextjs(request, "")


class NegotiationRunner:
    """Main runner for the negotiation workflow."""

    def __init__(self):
        self.store = StateStore()
        self.whatsapp = create_whatsapp_client(
            settings.whatsapp_bridge_url,
            settings.whatsapp_bridge_ws_url,
        )
        self.hooks = ObservabilityHooks(trace_store)

    async def initialize(self):
        """Initialize the runner and dependencies."""
        # Initialize SQLAlchemy tables (includes all models: traces, sellers, negotiations, etc.)
        await init_db()
        logger.info("Database initialized", is_postgres=settings.is_postgres)

    async def run_single_agent(self, agent_name: str, prompt: str) -> str:
        """Run a single agent with a prompt.

        Args:
            agent_name: Name of the agent (orchestrator, research, contact, negotiator)
            prompt: The task prompt for the agent

        Returns:
            Agent's response
        """
        agents = {
            "orchestrator": orchestrator_agent,
            "research": product_research_agent,
            "contact": contact_discovery_agent,
            "negotiator": negotiator_agent,
        }

        agent = agents.get(agent_name)
        if not agent:
            return f"Unknown agent: {agent_name}"

        logger.info("Running agent", agent=agent_name)

        # Start trace for observability
        await self.hooks.start_trace(input_prompt=prompt)

        try:
            result = await Runner.run(agent, prompt, hooks=self.hooks)
            await self.hooks.end_trace(final_output=result.final_output)
            return result.final_output
        except Exception as e:
            await self.hooks.end_trace(error=str(e))
            raise

    async def process_products(self, products: list[dict]) -> PurchaseSession:
        """Process a list of products through the full workflow.

        Args:
            products: List of product dictionaries with name, max_price, country

        Returns:
            PurchaseSession with results
        """
        # Create product requests
        product_requests = [
            ProductRequest(
                name=p["name"],
                max_price=p.get("max_price"),
                target_price=p.get("target_price"),
                quantity=p.get("quantity", 1),
                country=p.get("country", "IL"),
            )
            for p in products
        ]

        # Create session
        session = PurchaseSession(products=product_requests)
        await self.store.save_session(session)

        logger.info("Created purchase session", session_id=session.id, products=len(products))

        # Process each product
        for product in product_requests:
            logger.info("Processing product", name=product.name, country=product.country)

            # 1. Research phase
            research_prompt = f"""
            Find the best purchase options for: {product.name}
            Country: {product.country}
            Max price: {product.max_price or 'No limit'}
            Target price: {product.target_price or 'Best available'}
            """

            research_result = await self.run_single_agent("research", research_prompt)
            logger.info("Research complete", product=product.name)

            # 2. Contact discovery (would parse research_result in real implementation)
            # contact_result = await self.run_single_agent("contact", ...)

            # 3. Negotiation (would use discovered contacts)
            # negotiation_result = await self.run_single_agent("negotiator", ...)

        return session

    async def interactive_mode(self):
        """Run in interactive CLI mode."""
        logger.info("Starting interactive mode")

        print("\n" + "=" * 60)
        print("  ECOMMERCE NEGOTIATION AGENT")
        print("=" * 60)
        print("\nDashboard: http://localhost:8000/dashboard")
        print("\nCommands:")
        print("  <product>        - Research a product (default)")
        print("  n, negotiate <p> - Full negotiation workflow")
        print("  status           - Check WhatsApp status")
        print("  quit             - Exit")
        print()

        while True:
            try:
                user_input = input("\n> ").strip()

                if not user_input:
                    continue

                if user_input.lower() == "quit":
                    print("Goodbye!")
                    break

                if user_input.lower() == "status":
                    status = await self.whatsapp.check_health()
                    print(f"WhatsApp Status: {status}")
                    continue

                # Full negotiation workflow
                if user_input.lower().startswith("negotiate "):
                    query = user_input[10:]
                    print(f"Starting negotiation for: {query}")
                    result = await self.run_single_agent("orchestrator", f"Negotiate the best price for: {query}")
                    print(result)
                    continue

                if user_input.lower().startswith("n "):
                    query = user_input[2:]
                    print(f"Starting negotiation for: {query}")
                    result = await self.run_single_agent("orchestrator", f"Negotiate the best price for: {query}")
                    print(result)
                    continue

                # Default: treat as product research query
                print(f"Researching: {user_input}")
                result = await self.run_single_agent("research", f"Search for: {user_input}")
                print(result)

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                logger.error("Error processing input", error=str(e))
                print(f"Error: {e}")


def run_api_server():
    """Run the FastAPI server in a separate thread."""
    port = int(os.environ.get("PORT", 8000))
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


async def main():
    """Main entry point."""
    from src.config.settings import settings

    # In production, just run uvicorn directly (no interactive mode)
    if settings.environment == "production":
        port = int(os.environ.get("PORT", 8000))
        logger.info("Starting production server", port=port)
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
        return

    # Development: Start API server in background thread + interactive mode
    api_thread = threading.Thread(target=run_api_server, daemon=True)
    api_thread.start()
    logger.info("API server started", url="http://localhost:8000")

    runner = NegotiationRunner()
    await runner.initialize()
    await runner.interactive_mode()


if __name__ == "__main__":
    asyncio.run(main())
