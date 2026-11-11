-- Recibos existentes recebem um prazo de transição de 30 dias.
ALTER TABLE solicitacoes ADD COLUMN consulta_expira timestamptz NOT NULL DEFAULT (now() + interval '30 days');
ALTER TABLE solicitacoes ADD COLUMN impressao text;
CREATE INDEX solicitacoes_duplicacao ON solicitacoes(impressao, criado_em);
CREATE INDEX sessoes_expira ON sessoes(expira);
CREATE INDEX sessoes_funcionario ON sessoes(funcionario);
