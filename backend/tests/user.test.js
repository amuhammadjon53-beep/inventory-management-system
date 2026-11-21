const { test } = require("node:test");
const assert = require("node:assert/strict");
const { randomUUID } = require("node:crypto");
const mongoose = require("mongoose");
const connectDB = require("../config/db");
const User = require("../models/User");

const password = "Example test password 123!"; // Disposable fixture, not a database credential.
const valid = () => ({ name: "Abdullah Test", email: `auth-${randomUUID()}@example.test`, password });
const hashPattern = /^scrypt\$131072\$8\$1\$[a-f0-9]{32}\$[a-f0-9]{128}$/;

test("User normalizes name and email", async () => {
  const user = new User({ ...valid(), name: "  Abdullah  ", email: "  ABDULLAH@EXAMPLE.TEST  " });
  await user.validate();
  assert.equal(user.name, "Abdullah");
  assert.equal(user.email, "abdullah@example.test");
});

test("User rejects missing, invalid and non-string fields", async () => {
  for (const invalid of [
    { name: "" }, { name: "   " }, { name: "a".repeat(101) }, { name: 123 },
    { email: "" }, { email: "broken-email" }, { email: "a b@example.test" }, { email: [] },
    { password: "" }, { password: "short" }, { password: " ".repeat(12) },
    { password: "a".repeat(129) }, { password: 123456789012 },
    { password: "scrypt$131072$8$1$" + "a".repeat(32) + "$" + "b".repeat(128) }
  ]) {
    await assert.rejects(new User({ ...valid(), ...invalid }).validate(), { name: "ValidationError" });
  }
});

test("User JSON and object serialization never expose passwords", () => {
  const user = new User(valid());
  assert.equal(user.toJSON().password, undefined);
  assert.equal(user.toObject().password, undefined);
  assert.equal(user.toJSON().id, user._id.toString());
});

test("User rejects unknown fields", () => {
  assert.throws(() => new User({ ...valid(), role: "admin" }), { name: "StrictModeError" });
});

test("User comparison fails safely without a selected hash", async () => {
  assert.equal(await new User(valid()).comparePassword(password), false);
});

test("User blocks write methods that bypass password hashing", async () => {
  for (const query of [
    () => User.insertMany([valid()]),
    () => User.bulkWrite([{ insertOne: { document: valid() } }]),
    () => User.updateOne({}, { password }),
    () => User.updateMany({}, { password }),
    () => User.findOneAndUpdate({}, { password }),
    () => User.replaceOne({}, valid()),
    () => User.findOneAndReplace({}, valid())
  ]) {
    await assert.rejects(query(), /Use User.create\(\) or document.save\(\)/);
  }
});

const uri = process.env.TEST_MONGODB_URI;
test("User database integration (inventory_management_test only)", {
  skip: !uri && "Set TEST_MONGODB_URI to inventory_management_test",
  timeout: 120000
}, async t => {
  // Never fall back to the application's MONGODB_URI or drop the database.
  let database;
  try { database = new URL(uri).pathname.slice(1); } catch { /* reject below */ }
  assert.equal(database, "inventory_management_test", "Refusing to test outside inventory_management_test");
  const ids = [];
  const makeUser = async (values = {}) => {
    const user = new User({ ...valid(), ...values });
    ids.push(user._id);
    await user.save();
    return user;
  };
  try {
    try { await connectDB(uri); } catch { throw new Error("Test database connection failed; check credentials and Atlas Network Access"); }
    await User.init(); // Wait for the real unique email index before duplicate/race tests.
    await t.test("creates a user and persists timestamps and a salted password hash", async () => {
      const user = await makeUser();
      const raw = await User.collection.findOne({ _id: user._id });
      assert.match(raw.password, hashPattern);
      assert.notEqual(raw.password, password);
      assert.ok(raw.createdAt instanceof Date);
      assert.ok(raw.updatedAt instanceof Date);
      const second = await makeUser();
      assert.notEqual(second.password, raw.password);
    });
    await t.test("rejects duplicate emails after case and whitespace normalization", async () => {
      const user = await makeUser();
      await assert.rejects(makeUser({ email: `  ${user.email.toUpperCase()}  ` }), { code: 11000 });
      assert.equal(await User.countDocuments({ email: user.email }), 1);
    });
    await t.test("unique database index prevents concurrent registration races", async () => {
      const email = valid().email;
      const results = await Promise.allSettled([makeUser({ email }), makeUser({ email })]);
      assert.equal(results.filter(result => result.status === "fulfilled").length, 1);
      assert.equal(results.find(result => result.status === "rejected").reason.code, 11000);
    });
    await t.test("retrieves users without exposing hashes; verifies correct and wrong passwords", async () => {
      const user = await makeUser();
      const found = await User.findOne({ email: user.email });
      assert.equal(found.name, user.name);
      assert.equal(found.password, undefined);
      assert.equal((await User.findById(user._id).lean()).password, undefined);
      const login = await User.findOne({ email: user.email }).select("+password");
      assert.equal(await login.comparePassword(password), true);
      assert.equal(await login.comparePassword("incorrect password"), false);
      assert.equal(await login.comparePassword(null), false);
      assert.equal(login.toJSON().password, undefined);
    });
    await t.test("invalid users never reach MongoDB, even with validation disabled by caller", async () => {
      const user = new User({ ...valid(), password: "short" });
      ids.push(user._id);
      await assert.rejects(user.save(), { name: "ValidationError" });
      await assert.rejects(user.save({ validateBeforeSave: false }), { name: "ValidationError" });
      assert.equal(await User.countDocuments({ _id: user._id }), 0);
    });
    await t.test("profile saves do not rehash passwords and password changes are hashed", async () => {
      const user = await makeUser();
      const initialHash = user.password;
      user.name = "Updated User";
      await user.save();
      assert.equal(user.password, initialHash);
      const profile = await User.findById(user._id); // Password excluded.
      profile.name = "Updated without selecting password";
      await profile.save();
      const login = await User.findById(user._id).select("+password");
      assert.equal(login.password, initialHash);
      login.password = "A different test password 456!";
      await login.save();
      assert.match(login.password, hashPattern);
      assert.notEqual(login.password, initialHash);
      assert.equal(await login.comparePassword(password), false);
      assert.equal(await login.comparePassword("A different test password 456!"), true);
    });
  } finally {
    try {
      if (mongoose.connection.readyState === 1 && ids.length) {
        await User.deleteMany({ _id: { $in: ids } });
        assert.equal(await User.countDocuments({ _id: { $in: ids } }), 0);
      }
    } finally { await mongoose.disconnect(); }
  }
});
