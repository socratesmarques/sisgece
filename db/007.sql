-- Opt-in exclusivo para novos registros. Não autoriza telefones legados.
CREATE TABLE notificacao_assinaturas (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    solicitacao integer NOT NULL UNIQUE REFERENCES solicitacoes(id),
    destinatario text NOT NULL CHECK (destinatario IN ('solicitante','responsavel')),
    provedor text NOT NULL CHECK (provedor IN ('mock','meta')),
    consentimento_versao text NOT NULL,
    consentido_em timestamptz NOT NULL DEFAULT clock_timestamp(),
    verificado_em timestamptz,
    revogado_em timestamptz,
    desafio_hash text UNIQUE,
    desafio_expira timestamptz
);
CREATE TABLE notificacoes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    solicitacao integer NOT NULL REFERENCES solicitacoes(id),
    evento bigint NOT NULL REFERENCES eventos(id),
    assinatura bigint NOT NULL REFERENCES notificacao_assinaturas(id),
    telefone text NOT NULL CHECK (telefone ~ '^\+[1-9][0-9]{7,14}$'),
    canal text NOT NULL DEFAULT 'whatsapp' CHECK (canal='whatsapp'),
    provedor text NOT NULL CHECK (provedor IN ('mock','meta')),
    template_tipo text NOT NULL,
    template_nome text NOT NULL,
    template_id text,
    template_idioma text NOT NULL DEFAULT 'pt_BR',
    estado text NOT NULL DEFAULT 'pending' CHECK (estado IN
        ('pending','processing','sent','delivered','failed','cancelled','uncertain')),
    status_origem text NOT NULL,
    etapa_origem text,
    criado_em timestamptz NOT NULL DEFAULT clock_timestamp(),
    expira_em timestamptz NOT NULL DEFAULT (clock_timestamp()+interval '24 hours'),
    enviado_em timestamptz,
    entregue_em timestamptz,
    tentativas integer NOT NULL DEFAULT 0 CHECK(tentativas>=0),
    proxima_tentativa timestamptz NOT NULL DEFAULT clock_timestamp(),
    reserva_token text,
    reserva_ate timestamptz,
    despacho_em timestamptz,
    externo_id text,
    resultado text,
    UNIQUE(evento,canal,assinatura)
);
CREATE INDEX notificacoes_pendentes ON notificacoes(provedor,proxima_tentativa,id) WHERE estado='pending';
CREATE INDEX notificacoes_reservas ON notificacoes(reserva_ate) WHERE estado='processing';
CREATE UNIQUE INDEX notificacoes_externo ON notificacoes(provedor,externo_id) WHERE externo_id IS NOT NULL;
CREATE TABLE notificacao_webhooks (
    chave text PRIMARY KEY,
    recebido_em timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE notificacao_ritmo (
    chave text PRIMARY KEY,
    disponivel_em timestamptz NOT NULL
);
-- Recebimentos mínimos permitem reconciliar webhook anterior à resposta HTTP.
CREATE TABLE notificacao_entregas (
    externo_id text NOT NULL,
    estado text NOT NULL CHECK(estado IN ('sent','delivered','read','failed')),
    quando timestamptz NOT NULL,
    erro_codigo integer,
    PRIMARY KEY(externo_id,estado)
);
