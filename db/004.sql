ALTER TABLE solicitacoes DROP CONSTRAINT solicitacoes_status_check,
    ADD CONSTRAINT solicitacoes_status_check CHECK (
        status IN ('PENDENTE','APROVADA','REPROVADA')
        OR (status='RECEBIDA' AND tipo='Entrada' AND etapa IS NULL)
    ),
    ALTER COLUMN etapa DROP NOT NULL;
