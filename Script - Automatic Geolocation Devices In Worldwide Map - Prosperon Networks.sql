MERGE dbo.WorldMapPoints AS target
USING  
  ( SELECT n.NodeID  
      ,n.EntityType  
      ,case 
                                             when Site='Worthing' then 50.813104
                                             when Site='Barcelona' then 41.429853
                                             when Site='Athens' then 37.972463
                                             else null
                 end as Latitude  
      ,case 
                                             when Site='Worthing' then -0.372101
                                             when Site='Barcelona' then 2.193909
                                             when Site='Athens' then 23.726816
                                             else null 
                 end as Longitude
      ,case 
                                             when Site='Worthing' then 'Worthing Office'
                                             when Site='Barcelona' then 'Catalonia office'
                                             when Site='Athens' then 'Greece office'
                                             else null 
                 end as [Description]
   FROM Nodes n  
   LEFT JOIN WorldMapPoints wm ON n.NodeID=wm.InstanceID 
  ) AS source (NodeID, EntityType, Latitude, Longitude, [Description]) ON (target.InstanceID = source.NodeID)  

WHEN NOT MATCHED BY source  
THEN DELETE  

WHEN MATCHED  
  AND (source.Latitude IS NULL or source.Longitude IS NULL)  
THEN DELETE  
WHEN MATCHED  
  AND source.Latitude <> target.Latitude   
  OR (source.Latitude IS NOT NULL AND target.Latitude IS NULL)  
  OR source.Longitude <> target.Longitude  
  OR (source.Longitude IS NOT NULL AND target.Longitude IS NULL)  
  OR source.[Description] <> target.StreetAddress  
  OR (source.[Description] IS NOT NULL AND target.StreetAddress IS NULL)  
THEN  
UPDATE SET Latitude = source.Latitude, Longitude = source.Longitude, StreetAddress = source.[Description]  
 
WHEN NOT MATCHED BY target  
  AND source.EntityType IN ('Orion.Nodes','Orion.VIM.Hosts','Orion.VIM.VCenters')  

  AND source.Latitude IS NOT NULL  
  AND source.Longitude IS NOT NULL  
THEN  
INSERT (Instance, InstanceID, Latitude, Longitude, StreetAddress)  
VALUES ('Orion.Nodes', source.NodeID, source.Latitude, source.Longitude, source.[Description])  
;
