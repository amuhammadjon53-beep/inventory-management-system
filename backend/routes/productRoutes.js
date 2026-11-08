const express = require("express");
const Product = require("../models/Product");

const router = express.Router();

// Temporary in-memory storage for the demo
const products = [
    new Product({
        name: "Laptop",
        category: "Electronics",
        price: "500.00",
        quantity: 10
    }).toJSON(),

    new Product({
        name: "Keyboard",
        category: "Electronics",
        price: "30.00",
        quantity: 25
    }).toJSON()
];

// GET all products
router.get("/", (req, res) => {
    res.json({
        success: true,
        message: "Products retrieved successfully",
        data: products
    });
});

// POST a new product with model validation
router.post("/", async (req, res) => {
    try {
        const newProduct = new Product(req.body);

        await newProduct.validate();

        const productData = newProduct.toJSON();
        products.push(productData);

        res.status(201).json({
            success: true,
            message: "Product created successfully",
            data: productData
        });
    } catch (error) {
        res.status(400).json({
            success: false,
            message: error.message,
            data: null
        });
    }
});

module.exports = router;
