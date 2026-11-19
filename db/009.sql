-- Convite opcional de avaliação ao fim do processo; não ativa contas legadas.
ALTER TABLE notificacao_assinaturas
  ADD COLUMN avaliacao_consentida boolean NOT NULL DEFAULT false;

CREATE TABLE notificacao_avaliacoes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    notificacao bigint NOT NULL UNIQUE REFERENCES notificacoes(id),
    solicitacao integer NOT NULL REFERENCES solicitacoes(id),
    assinatura bigint NOT NULL REFERENCES notificacao_assinaturas(id),
    evento bigint NOT NULL REFERENCES eventos(id),
    codigo text NOT NULL UNIQUE CHECK (codigo ~ '^[A-F0-9]{16}$'),
    criado_em timestamptz NOT NULL DEFAULT clock_timestamp(),
    expira_em timestamptz NOT NULL DEFAULT (clock_timestamp() + interval '7 days'),
    cancelado_em timestamptz,
    nota smallint CHECK (nota BETWEEN 1 AND 5),
    respondido_em timestamptz,
    mensagem_id_hash text UNIQUE
);
CREATE INDEX notificacao_avaliacoes_pendentes
  ON notificacao_avaliacoes (codigo, expira_em)
  WHERE nota IS NULL AND cancelado_em IS NULL;
