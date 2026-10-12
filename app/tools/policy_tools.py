"""Store policy lookup for the support agent. In a real system this would be a RAG
retriever over the policy docs; a dict keeps the demo self-contained."""

from __future__ import annotations

POLICIES = {
    "shipping": "Standard shipping is free on orders over $50 and takes 3-5 business days. "
    "Express (1-2 business days) costs $14.99. We ship to all 50 US states.",
    "returns": "Most items can be returned within 30 days of delivery in original condition. "
    "Refunds go to the original payment method 3-5 business days after we receive the item. "
    "Refunds over $500 are reviewed by a person before approval.",
    "warranty": "Electronics carry a 1-year manufacturer warranty. Gold and platinum members get an extra year.",
    "price_match": "We match the price of major US retailers within 14 days of purchase. Marketplace sellers are excluded.",
    "loyalty": "Tiers: standard, gold (spend $1,000/yr) and platinum (spend $3,000/yr). "
    "Gold earns 2x points and free express shipping; platinum earns 3x points and priority support.",
    "payment": "We accept Visa, Mastercard, Amex, PayPal and Apple Pay. Buy-now-pay-later is available on orders over $150.",
    "contact": "Human support is available 8am-10pm ET by chat or at 1-800-555-0199.",
}


def get_store_policy(topic: str) -> dict:
    """Look up an official store policy.

    Args:
        topic: One of: shipping, returns, warranty, price_match, loyalty, payment, contact.

    Returns:
        dict with status and the policy text.
    """
    key = topic.strip().lower().replace(" ", "_").replace("-", "_")
    if key in POLICIES:
        return {"status": "success", "topic": key, "policy": POLICIES[key]}
    return {"status": "not_found", "message": f"Unknown topic '{topic}'.", "available_topics": sorted(POLICIES)}
