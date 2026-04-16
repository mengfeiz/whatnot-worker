"""
Whatnot Seller API Client — GraphQL wrapper for the official Whatnot Seller API.

Status: Developer Preview. API access is invite-only.
Token prefix: wn_access_tk_ (production) / wn_access_tk_test_ (staging)
"""

import os
from typing import Any

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
API_TOKEN = os.getenv("WHATNOT_API_TOKEN", "")
API_BASE = os.getenv("WHATNOT_API_BASE", "https://api.whatnot.com/seller-api/graphql")
# Use staging for testing: https://api.stage.whatnot.com/seller-api/graphql
REQUEST_TIMEOUT = int(os.getenv("WHATNOT_API_TIMEOUT", "30"))
MAX_RPS = 8  # stay under 10/sec limit with margin


class WhatnotAPIError(Exception):
    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message)
        self.errors = errors or []


# ---------------------------------------------------------------------------
# Core client
# ---------------------------------------------------------------------------
class WhatnotClient:
    def __init__(self, token: str | None = None, base_url: str | None = None):
        self.token = token or API_TOKEN
        self.base_url = base_url or API_BASE
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
            },
            timeout=REQUEST_TIMEOUT,
        )

    def _execute(self, query: str, variables: dict | None = None) -> dict:
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = self._client.post("", json=payload)
        body = resp.json()

        if "errors" in body:
            raise WhatnotAPIError(
                body["errors"][0].get("message", "GraphQL error"),
                errors=body["errors"],
            )

        return body.get("data", {})

    # ------------------------------------------------------------------
    # Products / Inventory
    # ------------------------------------------------------------------
    def list_products(self, first: int = 20, after: str | None = None) -> dict:
        """List products in the seller's store."""
        query = """
        query ListProducts($first: Int!, $after: String) {
          products(first: $first, after: $after) {
            pageInfo { hasNextPage endCursor }
            edges {
              node {
                id
                title
                status
                description
                category { name }
                variants {
                  id
                  title
                  price { amount currency }
                  inventory
                  sku
                }
                createdAt
                updatedAt
              }
            }
          }
        }
        """
        variables = {"first": first}
        if after:
            variables["after"] = after
        return self._execute(query, variables)

    def get_product(self, product_id: str) -> dict:
        """Get a single product by ID."""
        query = """
        query GetProduct($id: ID!) {
          product(id: $id) {
            id
            title
            status
            description
            category { name }
            variants {
              id
              title
              price { amount currency }
              inventory
              sku
            }
            images { url alt }
            createdAt
            updatedAt
          }
        }
        """
        return self._execute(query, {"id": product_id})

    def create_product(
        self,
        title: str,
        description: str = "",
        category_id: str | None = None,
        variants: list[dict] | None = None,
        images: list[str] | None = None,
    ) -> dict:
        """Create a new product listing."""
        query = """
        mutation CreateProduct($input: CreateProductInput!) {
          createProduct(input: $input) {
            product {
              id
              title
              status
              variants { id title price { amount } inventory }
            }
          }
        }
        """
        input_data: dict[str, Any] = {"title": title, "description": description}
        if category_id:
            input_data["categoryId"] = category_id
        if variants:
            input_data["variants"] = variants
        if images:
            input_data["images"] = images

        return self._execute(query, {"input": input_data})

    def update_inventory(self, variant_id: str, quantity: int) -> dict:
        """Update inventory for a specific variant."""
        query = """
        mutation UpdateInventory($variantId: ID!, $quantity: Int!) {
          updateInventory(variantId: $variantId, quantity: $quantity) {
            variant {
              id
              inventory
            }
          }
        }
        """
        return self._execute(query, {"variantId": variant_id, "quantity": quantity})

    def update_product_price(self, variant_id: str, price_cents: int) -> dict:
        """Update price for a specific variant."""
        query = """
        mutation UpdatePrice($variantId: ID!, $price: Int!) {
          updateVariantPrice(variantId: $variantId, price: $price) {
            variant {
              id
              price { amount currency }
            }
          }
        }
        """
        return self._execute(query, {"variantId": variant_id, "price": price_cents})

    def delete_product(self, product_id: str) -> dict:
        """Delete a product."""
        query = """
        mutation DeleteProduct($id: ID!) {
          deleteProduct(id: $id) {
            success
          }
        }
        """
        return self._execute(query, {"id": product_id})

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def list_orders(self, first: int = 20, after: str | None = None) -> dict:
        """List orders."""
        query = """
        query ListOrders($first: Int!, $after: String) {
          orders(first: $first, after: $after) {
            pageInfo { hasNextPage endCursor }
            edges {
              node {
                id
                status
                total { amount currency }
                items {
                  product { id title }
                  variant { id title }
                  quantity
                  price { amount currency }
                }
                createdAt
                updatedAt
              }
            }
          }
        }
        """
        variables = {"first": first}
        if after:
            variables["after"] = after
        return self._execute(query, variables)

    def get_order(self, order_id: str) -> dict:
        """Get order details."""
        query = """
        query GetOrder($id: ID!) {
          order(id: $id) {
            id
            status
            total { amount currency }
            items {
              product { id title }
              variant { id title }
              quantity
              price { amount currency }
            }
            shippingAddress { name street1 street2 city state zip country }
            trackingNumber
            carrier
            createdAt
            updatedAt
          }
        }
        """
        return self._execute(query, {"id": order_id})

    def add_tracking(self, order_id: str, tracking_number: str, carrier: str = "") -> dict:
        """Add tracking info to an order."""
        query = """
        mutation AddTracking($orderId: ID!, $trackingNumber: String!, $carrier: String) {
          addTracking(orderId: $orderId, trackingNumber: $trackingNumber, carrier: $carrier) {
            order {
              id
              status
              trackingNumber
              carrier
            }
          }
        }
        """
        return self._execute(query, {
            "orderId": order_id,
            "trackingNumber": tracking_number,
            "carrier": carrier,
        })

    # ------------------------------------------------------------------
    # Categories (for listing)
    # ------------------------------------------------------------------
    def list_categories(self) -> dict:
        """List available product categories."""
        query = """
        query ListCategories {
          categories {
            id
            name
            subcategories { id name }
          }
        }
        """
        return self._execute(query)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def introspect(self) -> dict:
        """Full schema introspection for discovering available types/queries."""
        query = """
        query IntrospectQuery {
          __schema {
            queryType { name }
            mutationType { name }
            types {
              name kind
              fields { name type { name kind } }
            }
          }
        }
        """
        return self._execute(query)

    def test_connection(self) -> dict:
        """Verify API token works."""
        try:
            result = self.list_products(first=1)
            return {"connected": True, "has_products": len(result.get("products", {}).get("edges", [])) > 0}
        except WhatnotAPIError as e:
            return {"connected": False, "error": str(e)}


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json
    import sys

    if not API_TOKEN:
        print("Set WHATNOT_API_TOKEN environment variable")
        sys.exit(1)

    client = WhatnotClient()

    if len(sys.argv) < 2:
        print("Usage: python api_client.py <command> [args]")
        print("Commands: test, products, orders, categories, introspect")
        sys.exit(0)

    cmd = sys.argv[1]
    match cmd:
        case "test":
            print(json.dumps(client.test_connection(), indent=2))
        case "products":
            print(json.dumps(client.list_products(), indent=2))
        case "orders":
            print(json.dumps(client.list_orders(), indent=2))
        case "categories":
            print(json.dumps(client.list_categories(), indent=2))
        case "introspect":
            print(json.dumps(client.introspect(), indent=2))
        case _:
            print(f"Unknown command: {cmd}")
