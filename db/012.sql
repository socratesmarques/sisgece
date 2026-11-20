-- A personalização integral é versionada sem alterar mensagens antigas na fila.
-- false = corpo legado (com cabeçalho/rodapé acrescentados pelo código antigo).
-- true = texto completo, com partes opcionais inseridas somente por marcadores.
ALTER TABLE notificacao_modelos
    ADD COLUMN mensagem_completa boolean NOT NULL DEFAULT false;

ALTER TABLE notificacoes
    ADD COLUMN mensagem_completa boolean NOT NULL DEFAULT false;
