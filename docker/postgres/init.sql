-- runs once when the data volume is created
CREATE EXTENSION IF NOT EXISTS vector;

-- separate database for pytest so tests never touch the real data
CREATE DATABASE resolvr_test;
\c resolvr_test
CREATE EXTENSION IF NOT EXISTS vector;
