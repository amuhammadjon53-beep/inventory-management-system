# StockWise — Inventory Management System

## Project Overview

StockWise is a full-stack web application designed to help small businesses manage products, monitor stock levels, and record inventory movements.

## Problem Statement

Small businesses may rely on manual records or spreadsheets to track their inventory. StockWise aims to make inventory management more organized and efficient.

## Target Users

- Small business owners
- Shop employees
- Inventory administrators

## Planned Features

- User registration and login
- Inventory dashboard
- Add, view, update, and delete products
- Search and filter products
- Track stock coming in and going out
- Low-stock alerts
- Protected features for authorized users

## Technology Stack

- Frontend: React, HTML, CSS, JavaScript
- Backend: Node.js and Express
- Database: MongoDB (planned integration)
- Version control: Git and GitHub

## Team Members

1. Muhammad — Backend Developer
2. Abdullah — Database and Quality Lead
3. Khalid — Frontend Developer

## Project Structure

- `frontend/` — Frontend application
- `backend/` — Backend API
- `docs/` — Project documentation

## Backend API

The backend currently provides HTTP endpoints for products.

### Base URL

`http://localhost:3000`

### Available Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/products` | Retrieve all products |
| POST | `/api/products` | Create a new product |

### Product JSON Structure

```json
{
  "id": 1,
  "name": "Laptop",
  "price": 500,
  "quantity": 10
}
```

### Example POST Request

```json
{
  "name": "Mouse",
  "price": 25,
  "quantity": 15
}
```

The backend generates the product ID automatically.

### GET Response Format

```json
{
  "success": true,
  "message": "Products retrieved successfully",
  "data": [
    {
      "id": 1,
      "name": "Laptop",
      "price": 500,
      "quantity": 10
    }
  ]
}
```

## Running the Backend

### 1. Open the backend folder

```bash
cd backend
```

### 2. Install dependencies

```bash
npm install
```

### 3. Start the server

```bash
node server.js
```

The server will run at:

`http://localhost:3000`

### 4. Test the API

Open this URL in your browser to retrieve products:

`http://localhost:3000/api/products`

To create a product, send a POST request to:

`http://localhost:3000/api/products`

Use JSON as the request body.

## Development Status

- Express backend configured.
- GET products endpoint implemented and tested.
- POST products endpoint implemented and tested.
- CORS middleware configured.
- Frontend integration in progress.
- MongoDB integration planned.

## Important Note

Products are currently stored in a temporary JavaScript array. Data is reset when the backend server restarts. MongoDB persistence will be implemented in a later development stage.
