-- Run this in Supabase SQL Editor to add storeroom features

-- Storeroom zones
CREATE TABLE zones (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    code TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    color TEXT DEFAULT '#22c55e',
    position_x NUMERIC(5,1) DEFAULT 0,
    position_y NUMERIC(5,1) DEFAULT 0,
    width NUMERIC(5,1) DEFAULT 100,
    height NUMERIC(5,1) DEFAULT 60,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add zone and reorder fields to stock
ALTER TABLE stock ADD COLUMN IF NOT EXISTS zone_code TEXT DEFAULT '';
ALTER TABLE stock ADD COLUMN IF NOT EXISTS location_note TEXT DEFAULT '';

-- Reorder thresholds per product
CREATE TABLE reorder_rules (
    id BIGSERIAL PRIMARY KEY,
    barcode TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    min_quantity INTEGER NOT NULL DEFAULT 10,
    supplier_note TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert some default zones (owner customises these)
INSERT INTO zones (name, code, description, color, position_x, position_y, width, height) VALUES
    ('Zone A', 'A', 'Drinks & Beverages', '#3b82f6', 10, 10, 120, 70),
    ('Zone B', 'B', 'Crisps & Snacks', '#f59e0b', 140, 10, 120, 70),
    ('Zone C', 'C', 'Cleaning & Household', '#8b5cf6', 10, 90, 120, 70),
    ('Zone D', 'D', 'Chilled & Dairy Backup', '#06b6d4', 140, 90, 120, 70),
    ('Zone E', 'E', 'Confectionery & Sweets', '#ec4899', 270, 10, 120, 70),
    ('Zone F', 'F', 'Tobacco & Misc', '#64748b', 270, 90, 120, 70);

CREATE INDEX idx_stock_zone ON stock(zone_code);
CREATE INDEX idx_reorder_barcode ON reorder_rules(barcode);
