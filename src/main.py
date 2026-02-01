"""Main entry point for the ecommerce negotiation agent."""

import asyncio
import json
import threading
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # Load .env into environment variables

from agents import Runner
import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
from src.api.middleware import RequestLoggingMiddleware
from src.db.base import init_db
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

# Initialize global trace store
trace_store = TraceStore()
set_trace_store(trace_store)

# Serve Next.js static export in production
# Must be after API routes so API endpoints take priority
frontend_path = Path(__file__).parent.parent / "frontend" / "out"
if frontend_path.exists():
    from fastapi.responses import FileResponse

    @app.get("/")
    async def serve_home():
        """Serve the landing page."""
        return FileResponse(frontend_path / "index.html")

    @app.get("/dashboard")
    @app.get("/dashboard/")
    async def serve_dashboard():
        """Serve the dashboard page."""
        return FileResponse(frontend_path / "dashboard" / "index.html")

    @app.get("/sellers")
    @app.get("/sellers/")
    async def serve_sellers_page():
        """Serve the sellers page."""
        return FileResponse(frontend_path / "sellers" / "index.html")

    # Serve static assets (JS, CSS, images)
    app.mount("/_next", StaticFiles(directory=frontend_path / "_next"), name="next_assets")

    # Catch-all for other static files
    @app.get("/{path:path}")
    async def serve_static(path: str):
        """Serve static files or fallback to 404."""
        file_path = frontend_path / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        # Try with index.html for directory routes
        index_path = file_path / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        # Return 404 page
        not_found = frontend_path / "404.html"
        if not_found.exists():
            return FileResponse(not_found, status_code=404)
        return FileResponse(frontend_path / "index.html")


class NegotiationRunner:
    """Main runner for the negotiation workflow."""

    def __init__(self):
        self.store = StateStore(settings.database_path)
        self.whatsapp = create_whatsapp_client(
            settings.whatsapp_bridge_url,
            settings.whatsapp_bridge_ws_url,
        )
        self.hooks = ObservabilityHooks(trace_store)

    async def initialize(self):
        """Initialize the runner and dependencies."""
        await self.store.initialize()
        logger.info("Database initialized (aiosqlite)", path=str(settings.database_path))

        # Initialize SQLAlchemy tables
        await init_db(settings.database_path)
        logger.info("Database initialized (SQLAlchemy)", path=str(settings.database_path))

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
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    server.run()


async def main():
    """Main entry point."""
    # Start API server in background thread
    api_thread = threading.Thread(target=run_api_server, daemon=True)
    api_thread.start()
    logger.info("API server started", url="http://localhost:8000")

    runner = NegotiationRunner()
    await runner.initialize()
    await runner.interactive_mode()


if __name__ == "__main__":
    asyncio.run(main())
