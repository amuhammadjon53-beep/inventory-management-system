
const express = require("express");

const router = express.Router();

const products = [
    {
        id: 1,
        name: "Laptop",
        price: 500,
        quantity: 10
    },
    {
        id: 2,
        name: "Keyboard",
        price: 30,
        quantity: 25
    }
];

router.get("/", (req, res) => {
    res.json({
        success: true,
        message: "Produts retrieved successfully",
        data: products
    });
});

//Post a new Product

router.post("/", (req, res) => {

    const { name, price, quantity } = req.body;

    const newProduct = {
        id: products.length + 1,
        name,
        price,
        quantity
    };

    products.push(newProduct);
    res.status(201).json({
        success: true,
        message: "Product created successfully",
        data: newProduct
    });
});

module.exports = router;
