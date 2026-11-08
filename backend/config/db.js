const mongoose = require("mongoose");

async function connectDB(uri = process.env.MONGODB_URI) {
  if (!uri?.trim()) {
    throw new Error("Set MONGODB_URI before connecting to MongoDB.");
  }

  await mongoose.connect(uri.trim(), { serverSelectionTimeoutMS: 5000 });
  return mongoose.connection;
}

module.exports = connectDB;
