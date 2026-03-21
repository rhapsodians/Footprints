-- ============================================================
-- Footprints v2.0 — ETF Universe Changes
-- Generated: 2026-03-21
-- Apply on Mac first, then replicate on PythonAnywhere
-- ============================================================

-- ------------------------------------------------------------
-- 1. SECTOR RECLASSIFICATIONS
-- ------------------------------------------------------------

-- ISWD.L: GLOBAL → BASE (broad developed-world fund, Islamic screen is a filter not a theme)
UPDATE etf_meta SET sector = 'BASE' WHERE ticker = 'ISWD.L';

-- IAUP.L: MINING → COMM (gold producers behave as commodity proxy, not diversified miner)
UPDATE etf_meta SET sector = 'COMM' WHERE ticker = 'IAUP.L';

-- IUCS.L: CONS → CSTAP (Consumer Staples — counter-cyclical, distinct from discretionary)
UPDATE etf_meta SET sector = 'CSTAP' WHERE ticker = 'IUCS.L';

-- WCOD.L: CONS → CDISC (Consumer Discretionary — cyclical, distinct from staples)
UPDATE etf_meta SET sector = 'CDISC' WHERE ticker = 'WCOD.L';

-- CNX1.L: US → TECH (NASDAQ-100 is growth/mega-cap tech proxy, not broad US market)
UPDATE etf_meta SET sector = 'TECH' WHERE ticker = 'CNX1.L';

-- INRG.L: stays in ENERGY (covers full energy spectrum including clean)
-- IHYG.L: stays in BOND (kept simple)
-- No changes needed for the above two.

-- ------------------------------------------------------------
-- 2. config.py SECTOR_LABEL additions required
--    Add these to the SECTOR_LABEL dict:
--      'CSTAP': 'Consumer Staples',
--      'CDISC': 'Consumer Discretionary',
--    Remove (or keep for backwards compat):
--      'CONS': 'Consumer',
-- ------------------------------------------------------------

-- ------------------------------------------------------------
-- 3. DELETE AMGAGG.L
--    (duplicate of AGHG.L index, unhedged, pension mapping mismatch)
-- ------------------------------------------------------------

DELETE FROM pension_etf_map WHERE ticker = 'AMGAGG.L';
DELETE FROM signal_log       WHERE ticker = 'AMGAGG.L';
DELETE FROM signals          WHERE ticker = 'AMGAGG.L';
DELETE FROM prices           WHERE ticker = 'AMGAGG.L';
DELETE FROM etf_meta         WHERE ticker = 'AMGAGG.L';

-- ------------------------------------------------------------
-- 4. REPOINT IL-AMUNDIABSLRETURN pension mapping
--    Was: AMGAGG.L (now deleted)
--    Now: LYCSH2.L (cash/overnight — best available LSE proxy)
-- ------------------------------------------------------------

-- fund_id for IL-AMUNDIABSLRETURN is 21 (verified from DB)
INSERT INTO pension_etf_map (fund_id, ticker) VALUES (21, 'LYCSH2.L');

-- ------------------------------------------------------------
-- 5. VERIFY
-- ------------------------------------------------------------

SELECT 'Sector changes' AS check_name;
SELECT ticker, sector, name FROM etf_meta 
WHERE ticker IN ('ISWD.L','IAUP.L','IUCS.L','WCOD.L','CNX1.L')
ORDER BY sector, ticker;

SELECT 'AMGAGG deleted' AS check_name;
SELECT COUNT(*) AS should_be_0 FROM etf_meta WHERE ticker = 'AMGAGG.L';

SELECT 'IL-AMUNDIABSLRETURN remapped' AS check_name;
SELECT pf.code, pem.ticker 
FROM pension_funds pf JOIN pension_etf_map pem ON pf.id = pem.fund_id
WHERE pf.code = 'IL-AMUNDIABSLRETURN';

SELECT 'LYCSH2.L pension mappings' AS check_name;
SELECT pf.code, pem.ticker 
FROM pension_funds pf JOIN pension_etf_map pem ON pf.id = pem.fund_id
WHERE pem.ticker = 'LYCSH2.L';
