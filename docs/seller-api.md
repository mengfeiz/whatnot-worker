# Whatnot Seller API Reference

**Status: Developer Preview — not accepting new applicants (as of 2026-04).**

Monitor: https://developers.whatnot.com/docs/getting-started/introduction

## Endpoints

- **Staging:** `POST https://api.stage.whatnot.com/seller-api/graphql`
- **Production:** `POST https://api.whatnot.com/seller-api/graphql`
- **GraphQL Playground:** https://api.stage.whatnot.com/seller-api/graphql

## Authentication

### Bearer Token
```
Authorization: Bearer <token>
Content-Type: application/json
```

- Staging token prefix: `wn_access_tk_test_`
- Production token prefix: `wn_access_tk_`

### OAuth2 Flow (for third-party apps)
1. Redirect user to Whatnot OAuth authorize endpoint
2. User approves → callback with authorization code
3. Exchange code for access token + refresh token
4. Refresh tokens expire in 1 year

**Scopes:**
| Scope | Access |
|-------|--------|
| `full_access` | Own account only, never via OAuth |
| `read:inventory` | Read products, variants, listings |
| `write:inventory` | Create/update/delete products, variants, listings |
| `read:orders` | Read orders |
| `write:orders` | Write tracking numbers etc. |
| `read:customers` | Read customer address, email, phone (BYOL only) |

## Rate Limits

- Global rate limit during Developer Preview
- **Max 10 requests/second**
- Use bulk operations where available
- Subject to change without notice

## Example Query

```graphql
query {
  products(first: 10) {
    edges {
      node {
        id
        title
        status
        variants {
          id
          price
          inventory
        }
      }
    }
  }
}
```

## Applying for Access

Email: api-access@whatnot.com (check current status)

During Developer Preview, access is invite-only. Monitor the developer portal for openings.

## Webhooks

Webhook docs not yet public (404). Expected to support:
- product.sold
- order.created
- order.updated

Check https://developers.whatnot.com/docs/seller-api/webhooks when available.
