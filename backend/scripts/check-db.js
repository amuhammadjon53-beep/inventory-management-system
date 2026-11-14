const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
const mongoose = require("mongoose");
const connectDB = require("../config/db");
const Product = require("../models/Product");

async function checkDatabase() {
  let productId;
  let stage = "connect";

  try {
    const connection = await connectDB();
    await connection.db.command({ ping: 1 });
    console.log("PASS: MongoDB connection and ping");

    stage = "save product";
    const name = `Database smoke test ${randomUUID()}`;
    const product = new Product({
      name,
      category: "Supplies",
      price: "12.99",
      quantity: 2
    });
    productId = product._id;
    await product.save();
    console.log("PASS: Product saved");

    stage = "reconnect and read product";
    await mongoose.disconnect();
    await connectDB();

    const saved = await Product.findById(productId);
    assert.ok(saved, "Saved product not found after reconnecting");
    assert.equal(saved.name, name);
    assert.equal(saved.category, "Supplies");
    assert.equal(saved.price, "12.99");
    assert.equal(saved.quantity, 2);
    assert.ok(saved.createdAt instanceof Date);
    assert.ok(saved.updatedAt instanceof Date);
    console.log("PASS: Product retrieved after reconnecting");

  } catch (error) {
    console.error(`FAIL (${stage}): ${error.name}`, error.code ?? "");
    if (stage === "connect") {
      console.error("Check MONGODB_URI, MongoDB availability and database access permissions.");
    }
    process.exitCode = 1;

  } finally {
    try {
      if (productId) {
        if (mongoose.connection.readyState !== 1) await connectDB();
        await Product.deleteOne({ _id: productId });
        assert.equal(await Product.countDocuments({ _id: productId }), 0);
        console.log("PASS: Test product cleaned up");
      }
    } catch (error) {
      console.error(`FAIL (cleanup): ${error.name}. Test product ID: ${productId}`);
      process.exitCode = 1;
    } finally {
      await mongoose.disconnect();
    }
  }
}

checkDatabase().catch(error => {
  console.error(`FAIL: ${error.name}`);
  process.exitCode = 1;
});
