
const express = require("express");

const router = express.Router();

router.get("/", (req, res) => {
    res.json([
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
    ]);
});

module.exports = router;
