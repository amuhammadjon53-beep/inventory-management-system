require("dotenv").config();
const express = require("express");
const cors = require("cors");
const connectDB = require("./config/db");

const app = express();
const PORT = 3000;

const productRoutes = require("./routes/productRoutes");

app.use(cors());
app.use(express.json());

app.get("/", (req, res) => {
    res.send("Inventory Management System API is running!");
});

app.use("/api/products", productRoutes);

async function startServer() {
    try {
        await connectDB();
        console.log("MongoDB connected successfully!");

        app.listen(PORT, () => {
            console.log(`Server is running on http://localhost:${PORT}`);
        });
    } catch (error) {
        console.error("Failed to connect to MongoDB:", error.message);
        process.exit(1);
    }
}

startServer();
