-- Run this in Supabase SQL Editor to create the tables

CREATE TABLE stock (
    id BIGSERIAL PRIMARY KEY,
    barcode TEXT NOT NULL,
    name TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 0,
    expiry_date DATE NOT NULL,
    cost_price NUMERIC(8,2) DEFAULT 0,
    sell_price NUMERIC(8,2) DEFAULT 0,
    added_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE sales (
    id BIGSERIAL PRIMARY KEY,
    barcode TEXT NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    sold_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE waste (
    id BIGSERIAL PRIMARY KEY,
    barcode TEXT NOT NULL,
    name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    reason TEXT DEFAULT 'expired',
    cost_price NUMERIC(8,2) DEFAULT 0,
    total_loss NUMERIC(8,2) DEFAULT 0,
    logged_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE shrinkage (
    id BIGSERIAL PRIMARY KEY,
    barcode TEXT NOT NULL,
    missing INTEGER NOT NULL,
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX idx_stock_barcode ON stock(barcode);
CREATE INDEX idx_stock_expiry ON stock(expiry_date);
CREATE INDEX idx_sales_sold_at ON sales(sold_at);
CREATE INDEX idx_waste_logged_at ON waste(logged_at);
