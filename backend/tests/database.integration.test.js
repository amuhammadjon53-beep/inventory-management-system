const test = require("node:test");
const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
const mongoose = require("mongoose");
const connectDB = require("../config/db");
const Product = require("../models/Product");

const uri = process.env.TEST_MONGODB_URI;

test("connection rejects a missing URI", async () => {
  await assert.rejects(connectDB(""), /Set MONGODB_URI/);
});

test("connection rejects invalid configuration without exposing credentials", async () => {
  for (const value of [42, {}, [], "   "]) {
    await assert.rejects(connectDB(value), /Set MONGODB_URI/);
  }
  await assert.rejects(connectDB("https://example.invalid"), /must start with mongodb/);
});

test("connection reports an unreachable MongoDB server", async () => {
  await assert.rejects(
    connectDB("mongodb://127.0.0.1:1/inventory_test_unreachable"),
    { name: "MongooseServerSelectionError" }
  );
  await mongoose.disconnect();
});

test("MongoDB saves and retrieves Product after reconnecting", {
  skip: !uri && "Set TEST_MONGODB_URI to a disposable test database",
  timeout: 30000
}, async () => {
  let id;
  try {
    const connection = await connectDB(uri);
    await connection.db.command({ ping: 1 });
    const product = new Product({
      name: `Week 10 review ${randomUUID()}`,
      category: "Supplies",
      price: "12.99",
      quantity: 2
    });
    id = product._id;
    await product.save();
    const createdAt = product.createdAt.getTime();
    assert.ok(product.updatedAt instanceof Date);
    await mongoose.disconnect();
    await connectDB(uri);
    const stored = await Product.findById(id);
    assert.ok(stored);
    assert.equal(stored.name, product.name);
    assert.equal(stored.category, "Supplies");
    assert.equal(stored.price, "12.99");
    assert.equal(stored.quantity, 2);
    assert.equal(stored.createdAt.getTime(), createdAt);
    const raw = await Product.findById(id).lean();
    assert.equal(raw.price._bsontype, "Decimal128");
    assert.equal(raw.price.toString(), "12.99");
  } finally {
    try {
      if (id) {
        if (mongoose.connection.readyState !== 1) await connectDB(uri);
        await Product.deleteOne({ _id: id });
        assert.equal(await Product.countDocuments({ _id: id }), 0);
      }
    } finally {
      await mongoose.disconnect();
    }
  }
});

test("invalid Product save is rejected and writes no record", {
  skip: !uri && "Set TEST_MONGODB_URI to a disposable test database",
  timeout: 15000
}, async () => {
  const product = new Product({
    name: `Invalid review ${randomUUID()}`,
    category: "Supplies",
    price: "-1.00",
    quantity: -1
  });
  try {
    await connectDB(uri);
    await assert.rejects(product.save(), { name: "ValidationError" });
    assert.equal(await Product.countDocuments({ _id: product._id }), 0);
  } finally {
    try {
      if (mongoose.connection.readyState === 1) {
        await Product.deleteOne({ _id: product._id });
      }
    } finally {
      await mongoose.disconnect();
    }
  }
});

test("all six required categories survive a MongoDB round trip", {
  skip: !uri && "Set TEST_MONGODB_URI to a disposable test database",
  timeout: 30000
}, async () => {
  const categories = ["General", "Food and Drink", "Clothing", "Electronics", "Supplies", "Other"];
  assert.deepEqual(Product.schema.path("category").enumValues, categories);
  const ids = [];
  try {
    await connectDB(uri);
    for (const category of categories) {
      const product = new Product({
        name: `Category review ${randomUUID()}`,
        category,
        price: "0.10",
        quantity: 0
      });
      ids.push(product._id);
      await product.save();
      const stored = await Product.findById(product._id);
      assert.equal(stored.category, category);
      assert.equal(stored.price, "0.10");
      assert.equal(stored.quantity, 0);
    }
  } finally {
    try {
      if (ids.length && mongoose.connection.readyState === 1) {
        await Product.deleteMany({ _id: { $in: ids } });
        assert.equal(await Product.countDocuments({ _id: { $in: ids } }), 0);
      }
    } finally {
      await mongoose.disconnect();
    }
  }
});
