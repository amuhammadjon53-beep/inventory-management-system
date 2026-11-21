const mongoose = require("mongoose");
const { randomBytes, scrypt, timingSafeEqual } = require("node:crypto");
const { promisify } = require("node:util");

const deriveKey = promisify(scrypt);
const options = { N: 131072, r: 8, p: 1, maxmem: 256 * 1024 * 1024 };
const hashPattern = /^scrypt\$131072\$8\$1\$([a-f0-9]{32})\$([a-f0-9]{128})$/;

function stringOnly(value) {
  if (value != null && typeof value !== "string") {
    throw new TypeError("Expected a string");
  }
  return value;
}

function publicUser(doc, result) {
  result.id = doc._id.toString();
  delete result._id;
  delete result.password;
  delete result.__v;
  return result;
}

const userSchema = new mongoose.Schema({
  name: { type: String, set: value => stringOnly(value)?.trim(), required: true, maxlength: 100 },
  email: {
    type: String, set: value => stringOnly(value)?.trim().toLowerCase(), required: true,
    maxlength: 254, match: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
    unique: true
  },
  password: {
    type: String, set: stringOnly, required: true, select: false,
    validate: {
      validator(value) {
        if (!this.isModified("password")) return hashPattern.test(value);
        return typeof value === "string" && value.length >= 12 &&
          value.length <= 128 && value.trim().length > 0 && !value.startsWith("scrypt$");
      },
      message: "Password must contain 12 to 128 characters and must not be a precomputed hash"
    }
  }
}, {
  timestamps: true,
  strict: "throw",
  toJSON: { transform: publicUser },
  toObject: { transform: publicUser }
});

userSchema.pre("save", async function () {
  // Also enforce validation if a caller tries save({ validateBeforeSave: false }).
  await this.validate();
  if (!this.isModified("password")) return;
  const salt = randomBytes(16).toString("hex");
  const key = await deriveKey(this.password, salt, 64, options);
  this.password = `scrypt$131072$8$1$${salt}$${key.toString("hex")}`;
});

userSchema.methods.comparePassword = async function (candidate) {
  if (typeof candidate !== "string" || candidate.length > 128) return false;
  const match = hashPattern.exec(this.password || "");
  if (!match) return false;
  const actual = await deriveKey(candidate, match[1], 64, options);
  return timingSafeEqual(actual, Buffer.from(match[2], "hex"));
};

// These operations bypass save middleware. Require document.save()/User.create().
// Raw collection/driver operations remain outside Mongoose's protection.
for (const operation of ["insertMany", "bulkWrite", "updateOne", "updateMany",
  "findOneAndUpdate", "replaceOne", "findOneAndReplace"]) {
  userSchema.pre(operation, function () {
    throw new Error("Use User.create() or document.save() for user writes");
  });
}

module.exports = mongoose.model("User", userSchema);
