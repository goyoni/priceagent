"""Contact discovery agent for finding seller WhatsApp numbers."""

from agents import Agent, function_tool
import re
from typing import Optional

from src.tools.scraping.registry import ScraperRegistry


@function_tool
async def scrape_seller_website(url: str) -> str:
    """Scrape a seller's website to find contact information.

    Args:
        url: The seller's website URL

    Returns:
        Any contact information found on the page
    """
    # Use playwright to scrape
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)

            content = await page.content()
            await browser.close()

            # Look for contact patterns
            contacts = []

            # Phone patterns (Israeli)
            phone_patterns = [
                r"05\d[\s-]?\d{3}[\s-]?\d{4}",
                r"\+972[\s-]?5\d[\s-]?\d{3}[\s-]?\d{4}",
            ]
            for pattern in phone_patterns:
                matches = re.findall(pattern, content)
                contacts.extend([f"Phone: {m}" for m in matches[:3]])

            # WhatsApp links
            wa_matches = re.findall(r'wa\.me/(\d+)', content)
            contacts.extend([f"WhatsApp: +{m}" for m in wa_matches[:3]])

            # Email
            email_matches = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', content)
            contacts.extend([f"Email: {m}" for m in email_matches[:3]])

            if contacts:
                return "Contact information found:\n" + "\n".join(set(contacts))
            return "No contact information found on this page."

    except Exception as e:
        return f"Failed to scrape website: {str(e)}"


@function_tool
async def verify_whatsapp_number(phone_number: str) -> str:
    """Verify if a phone number is registered on WhatsApp.

    Args:
        phone_number: Phone number to verify (with country code)

    Returns:
        Whether the number is on WhatsApp
    """
    from src.tools.whatsapp_tool import verify_whatsapp_number as verify

    return await verify(phone_number)


@function_tool
def normalize_phone_number(phone: str, country: str = "IL") -> str:
    """Normalize a phone number to international format.

    Args:
        phone: Raw phone number
        country: Country code for prefix

    Returns:
        Normalized phone number
    """
    # Remove all non-digits
    digits = re.sub(r'\D', '', phone)

    country_prefixes = {
        "IL": "972",
        "US": "1",
        "UK": "44",
    }

    prefix = country_prefixes.get(country, "972")

    # If starts with country prefix, just add +
    if digits.startswith(prefix):
        return f"+{digits}"

    # If starts with 0, replace with country prefix
    if digits.startswith("0"):
        return f"+{prefix}{digits[1:]}"

    # Otherwise, assume it needs the prefix
    return f"+{prefix}{digits}"


@function_tool
def request_manual_contact_input(
    seller_name: str,
    seller_url: str,
    product_name: str,
) -> str:
    """Request manual input of contact information when automated methods fail.

    Args:
        seller_name: Name of the seller
        seller_url: URL of the seller's website
        product_name: Product being purchased

    Returns:
        Instructions for manual input
    """
    return f"""
MANUAL CONTACT REQUIRED

Could not find WhatsApp contact for: {seller_name}
Website: {seller_url}
Product: {product_name}

Please provide the seller's WhatsApp number manually through the dashboard.
The negotiation will resume once contact information is provided.
"""


# Define the contact discovery agent
contact_discovery_agent = Agent(
    name="ContactDiscovery",
    instructions="""You are a contact discovery specialist. Your job is to find seller WhatsApp numbers for negotiation.

For each seller:
1. Use scrape_seller_website to search their website for phone numbers
2. Look for:
   - WhatsApp links (wa.me/...)
   - Mobile phone numbers (for Israel: starts with 05)
   - Contact pages, "About Us", or "צור קשר" sections
3. Use normalize_phone_number to format numbers correctly
4. Use verify_whatsapp_number to confirm the number is on WhatsApp
5. If no number found, use request_manual_contact_input

Return verified WhatsApp numbers ready for negotiation.
If multiple numbers are found, verify each and return all valid ones.
""",
    tools=[
        scrape_seller_website,
        verify_whatsapp_number,
        normalize_phone_number,
        request_manual_contact_input,
    ],
)
