INSERT INTO metric_definitions (name, description, unit, metric_type)
SELECT * FROM (VALUES
  ('pca_x',  'PCA embedding X coordinate (mutation-vector)', NULL, 'derived'),
  ('pca_y',  'PCA embedding Y coordinate (mutation-vector)', NULL, 'derived'),
  ('tsne_x', 't-SNE embedding X coordinate (mutation-vector)', NULL, 'derived'),
  ('tsne_y', 't-SNE embedding Y coordinate (mutation-vector)', NULL, 'derived')
) AS v(name, description, unit, metric_type)
WHERE NOT EXISTS (
  SELECT 1 FROM metric_definitions md
  WHERE md.name = v.name AND md.metric_type = v.metric_type
);