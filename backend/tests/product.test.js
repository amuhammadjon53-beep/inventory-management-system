const test = require("node:test");
const assert = require("node:assert/strict");
const mongoose = require("mongoose");
const Product = require("../models/Product");

const valid = () => ({ name: "Notebook", category: "Supplies", price: "1500.50", quantity: 20 });

async function validationError(product) {
  try {
    await product.validate();
    return undefined;
  } catch (error) {
    return error;
  }
}

// Validation runs without connecting to MongoDB.
test("valid product, trimmed text, generated ID and JSON price", async () => {
  const product = new Product({ ...valid(), name: " Notebook " });
  assert.equal((await validationError(product)), undefined);
  assert.equal(product.name, "Notebook");
  assert.ok(product._id instanceof mongoose.Types.ObjectId);
  assert.equal(product.get("price", null, { getters: false })._bsontype, "Decimal128");
  const json = product.toJSON();
  assert.equal(json.price, "1500.50");
  assert.equal(json.id, String(product._id));
  assert.equal(json._id, undefined);
});

test("each business field is required", async () => {
  for (const field of ["name", "category", "price", "quantity"]) {
    const data = valid();
    delete data[field];
    assert.ok((await validationError(new Product(data)))?.errors[field], field);
  }
});

test("blank or excessive names are rejected", async () => {
  for (const name of ["", "   ", "a".repeat(101)]) {
    assert.ok((await validationError(new Product({ ...valid(), name })))?.errors.name);
  }
});

test("categories match the existing frontend", async () => {
  for (const category of ["General", "Food and Drink", "Clothing", "Electronics", "Supplies", "Other"]) {
    assert.equal((await validationError(new Product({ ...valid(), category }))), undefined);
  }
  for (const category of ["", "   ", "Unknown"]) {
    assert.ok((await validationError(new Product({ ...valid(), category })))?.errors.category);
  }
});

test("negative, malformed and overly precise prices are rejected", async () => {
  for (const price of [-1, "-0.01", "abc", "1.234", "", "   ", NaN, Infinity, "NaN", "Infinity", {}, true]) {
    assert.ok((await validationError(new Product({ ...valid(), price })))?.errors.price, String(price));
  }
});

test("whole and fractional prices are preserved", async () => {
  for (const price of [0, 1500, "0.00", "0.10", "12.99"]) {
    const product = new Product({ ...valid(), price });
    assert.equal((await validationError(product)), undefined);
    assert.equal(product.toJSON().price, String(price));
  }
});

test("invalid stock counts are rejected", async () => {
  for (const quantity of [-1, 1.5, NaN, Infinity, 2147483648]) {
    assert.ok((await validationError(new Product({ ...valid(), quantity })))?.errors.quantity);
  }
});

test("zero and maximum stock are valid", async () => {
  for (const quantity of [0, 2147483647]) {
    assert.equal((await validationError(new Product({ ...valid(), quantity }))), undefined);
  }
});

test("document edits are validated again", async () => {
  const product = new Product(valid());
  product.quantity = -5;
  assert.ok((await validationError(product))?.errors.quantity);
  product.quantity = 5;
  product.price = "-2.00";
  assert.ok((await validationError(product))?.errors.price);
});

test("unknown fields are rejected and timestamps configured", async () => {
  assert.throws(() => new Product({ ...valid(), unexpected: true }), /strict mode/i);
  assert.equal(Product.schema.options.timestamps, true);
  assert.ok(Product.schema.path("createdAt"));
  assert.ok(Product.schema.path("updatedAt"));
  assert.equal(Product.collection.name, "products");
});
