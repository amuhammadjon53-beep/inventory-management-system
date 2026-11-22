
const { test } = require("node:test");
const assert = require("node:assert/strict");
const mongoose = require("mongoose");
const { randomUUID } = require("node:crypto");
const request = require("supertest");

const app = require("../server");
const connectDB = require("../config/db");
const User = require("../models/User");

test("Authentication API integration tests", async (t) => {
    const testUri = process.env.TEST_MONGODB_URI;

    assert.ok(testUri, "TEST_MONGODB_URI must be configured");

    const databaseName = new URL(testUri).pathname.slice(1);

    assert.equal(
        databaseName,
        "inventory_management_test",
        "Tests must use the isolated test database"
    );

    assert.ok(process.env.JWT_SECRET, "JWT_SECRET must be configured");

    await connectDB(testUri);

    const email = `auth-test-${randomUUID()}@example.com`;
    const password = "TestPassword123!";
    let token;

    try {
        await t.test("Register a new user", async () => {
            const response = await request(app)
                .post("/api/auth/register")
                .send({
                    name: "StockWise Test User",
                    email,
                    password
                });

            assert.equal(response.status, 201);
            assert.equal(response.body.success, true);
            assert.ok(response.body.token);

            token = response.body.token;
        });

        await t.test("Reject duplicate email registration", async () => {
            const response = await request(app)
                .post("/api/auth/register")
                .send({
                    name: "Another Test User",
                    email,
                    password
                });

            assert.equal(response.status, 409);
            assert.equal(response.body.success, false);
        });

        await t.test("Login with correct credentials", async () => {
            const response = await request(app)
                .post("/api/auth/login")
                .send({
                    email,
                    password
                });

            assert.equal(response.status, 200);
            assert.equal(response.body.success, true);
            assert.ok(response.body.token);
        });

        await t.test("Reject incorrect password", async () => {
            const response = await request(app)
                .post("/api/auth/login")
                .send({
                    email,
                    password: "WrongPassword123!"
                });

            assert.equal(response.status, 401);
            assert.equal(response.body.success, false);
        });

        await t.test("Reject access without a token", async () => {
            const response = await request(app)
                .get("/api/products");

            assert.equal(response.status, 401);
            assert.equal(response.body.success, false);
        });

        await t.test("Reject an invalid token", async () => {
            const response = await request(app)
                .get("/api/products")
                .set("Authorization", "Bearer invalid-token");

            assert.equal(response.status, 401);
            assert.equal(response.body.success, false);
        });

        await t.test("Allow access with a valid token", async () => {
            const response = await request(app)
                .get("/api/products")
                .set("Authorization", `Bearer ${token}`);

            assert.equal(response.status, 200);
            assert.equal(response.body.success, true);
            assert.ok(Array.isArray(response.body.data));
        });

    } finally {
        // Remove only the user created by this test.
        await User.deleteOne({ email });

        await mongoose.disconnect();
    }
});
