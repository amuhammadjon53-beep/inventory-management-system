const mongoose = require("mongoose");

async function connectDB(uri = process.env.MONGODB_URI) {
  if (typeof uri !== "string" || !uri.trim()) {
    throw new Error("Set MONGODB_URI before connecting to MongoDB.");
  }

  if (!/^mongodb(?:\+srv)?:\/\//.test(uri.trim())) {
    throw new Error("MONGODB_URI must start with mongodb:// or mongodb+srv://.");
  }

  await mongoose.connect(uri.trim(), { serverSelectionTimeoutMS: 5000 });
  return mongoose.connection;
}

module.exports = connectDB;
