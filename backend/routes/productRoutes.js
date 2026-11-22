const express = require("express");
const Product = require("../models/Product");
const authMiddleware = require("../middleware/authMiddleware");

const router = express.Router();
router.use(authMiddleware);

// GET all products from MongoDB
router.get("/", async (req, res) => {
    try {
        const products = await Product.find();

        res.json({
            success: true,
            message: "Products retrieved successfully",
            data: products
        });
    } catch (error) {
        console.error("GET products error:", error);

        res.status(500).json({
            success: false,
            message: "Failed to retrieve products",
            data: null
        });
    }
});

// POST a new product to MongoDB
router.post("/", async (req, res) => {
    try {
        const newProduct = new Product(req.body);
        const savedProduct = await newProduct.save();

        res.status(201).json({
            success: true,
            message: "Product created successfully",
            data: savedProduct
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
