
# API Response Format

## Overview

All backend API endpoints use a consistent JSON response structure.

## Successful Response

```json
{
  "success": true,
  "message": "Operation successful",
  "data": {}
}
```

## Error Response

```json
{
  "success": false,
  "message": "Error description",
  "data": null
}
```

## Fields

- `success`: Indicates whether the request was successful.
- `message`: Provides information about the result.
- `data`: Contains the requested data or null if an error occurs.

## Team Agreement

This response format was agreed upon by all three team members during Week 9.
