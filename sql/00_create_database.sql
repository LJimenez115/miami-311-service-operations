-- Why: Run this once while connected to PostgreSQL's default `postgres` database
-- to create an isolated database for this project rather than mixing it with other work.
CREATE DATABASE miami_311_operations;
-- Why: Keeping this command separate prevents the data-loader transaction from trying
-- to create a database, which PostgreSQL correctly disallows inside a transaction.
