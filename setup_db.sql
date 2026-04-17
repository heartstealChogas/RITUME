-- Run this once in the Supabase SQL Editor (Dashboard → SQL Editor)
-- before starting the server for the first time.

CREATE TABLE IF NOT EXISTS comparisons (
    id          SERIAL PRIMARY KEY,
    branch_name TEXT,
    file_date   TEXT,
    status      TEXT,
    seq         TEXT,
    name        TEXT,
    barcode     TEXT,
    po_qty      INTEGER,
    inv_no      TEXT,
    inv_qty     INTEGER,
    qty_diff    INTEGER
);

CREATE TABLE IF NOT EXISTS branches (
    id       TEXT PRIMARY KEY,
    name     TEXT NOT NULL,
    path_po  TEXT,
    path_inv TEXT
);
