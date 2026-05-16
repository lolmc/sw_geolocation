USE SolarWindsOrion;  -- or whatever your SolarWinds database is called
GO

/*
================================================================================
  Staging Table: dbo.StagingGeocodes
  ================================================================================
  WHY WE NEED THIS
  ----------------
  The old script hardcoded every site lat/lng inside big CASE/THEN blocks.
  That means every new site required editing SQL. That is slow, error-prone,
  and means your coordinates live in two places (the SQL file and wherever
  someone originally typed them).

  This staging table fixes that.
  We load our geocoded data (from Python's CSV output) into this table FIRST.
  Then one single MERGE statement copies it into SolarWinds' WorldMapPoints.

  THINK OF IT LIKE A WAITING ROOM:
  - The staging table is the waiting room.
  - The Python script puts addresses and coordinates in there.
  - The MERGE statement then moves them into the final destination correctly,
    handling updates, deletions, and inserts all at once.

  HOW TO USE
  ----------
  1. Run geocode_uk.py to get your gc_data.csv with lat/lng columns.
  2. Use SQL Server Management Studio (or a Python script with pyodbc/pymssql)
     to load gc_data.csv into this staging table.
     
     Example bulk load command:
     
     BULK INSERT dbo.StagingGeocodes
     FROM 'C:\path\to\gc_data.csv'
     WITH (
         FIRSTROW = 2,
         FIELDTERMINATOR = ',',
         ROWTERMINATOR = '\n',
         TABLOCK
     );

  3. Run the MERGE statement below.
  4. Clear the staging table (optional, depends on your workflow).

  QUARTERLY REFRESH
  -----------------
  When you download the latest Code-Point Open data and re-geocode your list,
  just truncate this table, re-load the CSV, and run the MERGE again.
  The MERGE will automatically update changed coordinates and mark stale
  records correctly.
================================================================================
*/

-- Only create the table if it doesn't already exist.
IF OBJECT_ID('dbo.StagingGeocodes', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.StagingGeocodes
    (
        SiteName        NVARCHAR(255)   NULL,   -- e.g. 'Worthing Office'
        Postcode        NVARCHAR(10)    NULL,   -- e.g. 'PL0 1PF'
        AddressLine     NVARCHAR(500)   NULL,   -- Full readable address
        Latitude        DECIMAL(18, 6)  NULL,   -- Vertical map pin
        Longitude       DECIMAL(18, 6)  NULL,   -- Horizontal map pin
        Description     NVARCHAR(255)   NULL,   -- Label that appears on the map
        GeocodeSource   NVARCHAR(50)    NULL,   -- 'codepoint_open', 'nominatim', etc.
        GeocodeDate     DATETIME2       NULL,   -- When we looked it up

        -- Link back to SolarWinds Nodes by name.
        -- If you already have NodeIDs, add a NodeID column instead.
        LinkedNodeName  NVARCHAR(255)   NULL
    );
    
    -- Make postcode lookups fast.
    CREATE INDEX IX_StagingGeocodes_Postcode
        ON dbo.StagingGeocodes (Postcode);
    
    PRINT 'Created dbo.StagingGeocodes staging table.';
END
ELSE
BEGIN
    PRINT 'dbo.StagingGeocodes already exists.';
END
GO


/*
================================================================================
  MERGE: Update SolarWinds WorldMapPoints from StagingGeocodes
  ================================================================================
  This replaces the old hardcoded MERGE completely.
  
  It does FIVE things in one go:
  1. DELETE old map points that are no longer in the staging list.
  2. DELETE map points where coordinates have gone blank (e.g. a bad postcode).
  3. UPDATE existing map points if lat/lng or description changed.
  4. INSERT new map points for new sites.
  5. Leave untouched map points alone (saves time and avoids re-drawing the map).

  IMPORTANT:
  - This script uses SiteName to join Nodes to WorldMapPoints.
  - If your SolarWinds environment uses a different column (e.g. 'Location'
    instead of 'Site'), change the JOIN condition below.
================================================================================
*/

MERGE dbo.WorldMapPoints AS target
USING (
    -- Build the source dataset from staging + nodes.
    SELECT
        n.NodeID,
        n.EntityType,
        s.Latitude,
        s.Longitude,
        s.Description
    FROM Nodes n
    INNER JOIN dbo.StagingGeocodes s
        ON LOWER(LTRIM(RTRIM(n.Site))) = LOWER(LTRIM(RTRIM(s.SiteName)))
    WHERE s.Latitude IS NOT NULL
      AND s.Longitude IS NOT NULL
) AS source (NodeID, EntityType, Latitude, Longitude, Description)
ON target.InstanceID = source.NodeID

-- 1. Map points that are no longer in our staging list = remove them from the map.
WHEN NOT MATCHED BY source THEN
    DELETE

-- 2. Map points where staging now has NULL coordinates = remove them
--    (e.g. someone moved and we couldn't find the new postcode).
WHEN MATCHED
    AND (source.Latitude IS NULL OR source.Longitude IS NULL)
THEN
    DELETE

-- 3. Map points that already exist but need updating.
WHEN MATCHED
    AND (
        source.Latitude <> target.Latitude
        OR (source.Latitude IS NOT NULL AND target.Latitude IS NULL)
        OR source.Longitude <> target.Longitude
        OR (source.Longitude IS NOT NULL AND target.Longitude IS NULL)
        OR source.Description <> target.StreetAddress
        OR (source.Description IS NOT NULL AND target.StreetAddress IS NULL)
    )
THEN
    UPDATE SET
        Latitude = source.Latitude,
        Longitude = source.Longitude,
        StreetAddress = source.Description

-- 4. New map points for sites we haven't seen before.
WHEN NOT MATCHED BY target
    AND source.EntityType IN ('Orion.Nodes', 'Orion.VIM.Hosts', 'Orion.VIM.VCenters')
    AND source.Latitude IS NOT NULL
    AND source.Longitude IS NOT NULL
THEN
    INSERT (Instance, InstanceID, Latitude, Longitude, StreetAddress)
    VALUES ('Orion.Nodes', source.NodeID, source.Latitude, source.Longitude, source.Description);

-- 5. Print how many rows were affected.
PRINT 'WorldMapPoints merge complete.';
GO


/*
================================================================================
  VIEW: vw_StagingGeocodeSummary
  ================================================================================
  A helper view so you can quickly see the last time you refreshed coordinates
  and which source each coordinate came from.
================================================================================
*/

IF OBJECT_ID('dbo.vw_StagingGeocodeSummary', 'V') IS NOT NULL
    DROP VIEW dbo.vw_StagingGeocodeSummary;
GO

CREATE VIEW dbo.vw_StagingGeocodeSummary
AS
SELECT
    SiteName,
    Postcode,
    Latitude,
    Longitude,
    GeocodeSource,
    GeocodeDate,
    CASE
        WHEN Latitude BETWEEN 49.8 AND 60.8 AND Longitude BETWEEN -8.6 AND 1.8
        THEN 'Inside UK bounding box'
        ELSE 'WARNING: Outside UK bounding box'
    END AS SanityCheck
FROM dbo.StagingGeocodes
WHERE Latitude IS NOT NULL;
GO

PRINT 'Created/updated dbo.vw_StagingGeocodeSummary view.';
GO
