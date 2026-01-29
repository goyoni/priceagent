"""Orchestrator agent that coordinates the purchasing workflow."""

from agents import Agent, function_tool
from typing import Optional
import json


@function_tool
def parse_product_list(products_json: str) -> str:
    """Parse a JSON list of products to purchase.

    Args:
        products_json: JSON string with product list

    Returns:
        Formatted list of products to process
    """
    try:
        products = json.loads(products_json)
        output = ["Products to purchase:"]
        for i, p in enumerate(products, 1):
            name = p.get("name", "Unknown")
            max_price = p.get("max_price", "No limit")
            country = p.get("country", "IL")
            output.append(f"{i}. {name} (Max: {max_price}, Country: {country})")
        return "\n".join(output)
    except json.JSONDecodeError:
        return f"Error parsing product list. Expected JSON format."


@function_tool
def create_product_request(
    name: str,
    max_price: Optional[float] = None,
    target_price: Optional[float] = None,
    quantity: int = 1,
    country: str = "IL",
) -> str:
    """Create a new product purchase request.

    Args:
        name: Product name to search for
        max_price: Maximum price willing to pay
        target_price: Ideal target price
        quantity: Number of units needed
        country: Country code for search

    Returns:
        Product request confirmation
    """
    request = {
        "name": name,
        "max_price": max_price,
        "target_price": target_price,
        "quantity": quantity,
        "country": country,
    }
    return f"Created product request:\n{json.dumps(request, indent=2)}"


@function_tool
def update_negotiation_status(
    product_name: str,
    seller_name: str,
    status: str,
    current_price: Optional[float] = None,
    notes: Optional[str] = None,
) -> str:
    """Update the status of a negotiation.

    Args:
        product_name: Name of the product
        seller_name: Name of the seller
        status: Current status (researching, contacting, negotiating, completed, failed)
        current_price: Current negotiated price if any
        notes: Additional notes

    Returns:
        Status update confirmation
    """
    update = {
        "product": product_name,
        "seller": seller_name,
        "status": status,
        "current_price": current_price,
        "notes": notes,
    }
    return f"Status updated:\n{json.dumps(update, indent=2)}"


@function_tool
def generate_summary_report(negotiations_data: str) -> str:
    """Generate a summary report of all negotiations.

    Args:
        negotiations_data: JSON string with negotiation data

    Returns:
        Formatted summary report
    """
    return f"""
NEGOTIATION SUMMARY REPORT
===========================

{negotiations_data}

Report generated. Please review the results above.
"""


@function_tool
def prioritize_products(products_data: str) -> str:
    """Prioritize products for processing based on urgency and potential savings.

    Args:
        products_data: JSON string with product information

    Returns:
        Prioritized order for processing
    """
    return f"Prioritization analysis:\n{products_data}\n\nProcess products in order of priority."


# Define the orchestrator agent
orchestrator_agent = Agent(
    name="Orchestrator",
    instructions="""You are the main coordinator for an ecommerce purchasing system. Your job is to orchestrate the entire purchasing workflow.

WORKFLOW:
1. Receive a list of products from the user
2. For each product:
   a. Hand off to ProductResearch agent to find best options
   b. Hand off to ContactDiscovery agent to get seller WhatsApp numbers
   c. Hand off to Negotiator agent to negotiate prices
3. Track progress and provide status updates
4. Generate a final summary report

COORDINATION RULES:
1. Process products in priority order (most urgent or highest potential savings first)
2. Handle multiple sellers per product if needed
3. If one seller doesn't respond, move to the next
4. Always keep the user informed of progress
5. Generate comprehensive reports

STATUS TRACKING:
- Use update_negotiation_status to track each negotiation
- Possible statuses: researching, contacting, negotiating, awaiting_approval, completed, failed

ERROR HANDLING:
- If product research fails, report and skip to next product
- If contact discovery fails, try alternative sellers
- If negotiation fails, try next seller or report back

Always maintain a clear overview of all ongoing negotiations.
""",
    tools=[
        parse_product_list,
        create_product_request,
        update_negotiation_status,
        generate_summary_report,
        prioritize_products,
    ],
    # Handoffs would be configured here in a real implementation
    # handoffs=[product_research_agent, contact_discovery_agent, negotiator_agent]
)
