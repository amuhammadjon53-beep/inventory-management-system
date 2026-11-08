const express = require("express");
const cors = require("cors");

const app = express();
const PORT = 3000;

const productRoutes = require("./routes/productRoutes");

app.use(cors());
app.use(express.json());

app.get("/", (req, res) => {
    res.send("Inventory Management System API is running!");
});

app.use("/api/products", productRoutes);

app.listen(PORT, () => {
    console.log(`Server is running on http://localhost:${PORT}`);
});
