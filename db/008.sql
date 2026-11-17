-- Provedor Evolution estritamente experimental.
-- Mantém todos os demais provedores e dados existentes.
ALTER TABLE notificacao_assinaturas
  DROP CONSTRAINT notificacao_assinaturas_provedor_check;
ALTER TABLE notificacao_assinaturas
  ADD CONSTRAINT notificacao_assinaturas_provedor_check
  CHECK (provedor IN ('mock','meta','evolution'));
ALTER TABLE notificacoes
  DROP CONSTRAINT notificacoes_provedor_check;
ALTER TABLE notificacoes
  ADD CONSTRAINT notificacoes_provedor_check
  CHECK (provedor IN ('mock','meta','evolution'));
