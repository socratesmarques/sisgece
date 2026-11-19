-- Entradas aprovadas passam pela recepção, sem etapa de portaria.
-- Mantém registros históricos já existentes inalterados.
ALTER TABLE solicitacoes DROP CONSTRAINT solicitacoes_etapa_check;
ALTER TABLE solicitacoes ADD CONSTRAINT solicitacoes_etapa_check
  CHECK (etapa IN (
    'aguardando',
    'recepção confirmada',
    'saída concluída',
    'aguardando recepção',
    'entrada concluída'
  ));
