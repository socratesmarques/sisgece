-- Personalização auditável das mensagens enviadas pela Evolution API.
-- Sem alterações em solicitações existentes; migração idempotente via versoes.
CREATE TABLE notificacao_modelos (
    tipo text PRIMARY KEY CHECK (tipo IN (
        'cadastro','aprovar','reprovar','recepção','portaria',
        'reabrir análise','corrigir recepção','corrigir portaria'
    )),
    corpo text NOT NULL CHECK (char_length(corpo) BETWEEN 10 AND 1500),
    ativo boolean NOT NULL DEFAULT true,
    versao integer NOT NULL DEFAULT 1 CHECK (versao > 0),
    alterado_por integer REFERENCES administradores(id),
    alterado_em timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE notificacao_modelos_historico (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tipo text NOT NULL REFERENCES notificacao_modelos(tipo),
    versao integer NOT NULL CHECK (versao > 0),
    corpo text NOT NULL,
    ativo boolean NOT NULL,
    acao text NOT NULL CHECK (acao IN ('salvar','restaurar')),
    autor integer NOT NULL REFERENCES administradores(id),
    quando timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE(tipo, versao)
);
CREATE INDEX notificacao_modelos_historico_ultimos
    ON notificacao_modelos_historico(tipo, id DESC);

-- Congela o texto selecionado no momento do evento: edições futuras não alteram fila existente.
ALTER TABLE notificacoes ADD COLUMN corpo_personalizado text;
