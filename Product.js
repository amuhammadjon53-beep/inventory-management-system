const mongoose = require("mongoose");

const categories = [
  "General", "Food and Drink", "Clothing", "Electronics", "Supplies", "Other"
];

function parsePrice(value) {
  if (value == null) return value;
  const text = String(value);
  if (!/^\d+(\.\d{1,2})?$/.test(text)) {
    throw new Error("Price must be non-negative with at most two decimal places");
  }
  return mongoose.Types.Decimal128.fromString(text);
}

const productSchema = new mongoose.Schema({
  name: {
    type: String,
    required: true,
    trim: true,
    maxlength: 100
  },
  category: {
    type: String,
    required: true,
    trim: true,
    enum: categories
  },
  price: {
    type: mongoose.Schema.Types.Decimal128,
    required: true,
    set: parsePrice,
    get: value => value == null ? value : value.toString()
  },
  quantity: {
    type: Number,
    required: true,
    min: 0,
    max: 2147483647,
    validate: {
      validator: Number.isInteger,
      message: "Quantity must be a whole number"
    }
  }
}, {
  timestamps: true,
  strict: "throw",
  toJSON: {
    getters: true,
    versionKey: false,
    transform(doc, result) {
      result.id = result._id.toString();
      delete result._id;
      return result;
    }
  }
});

module.exports = mongoose.model("Product", productSchema);
