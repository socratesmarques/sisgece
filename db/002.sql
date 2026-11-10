ALTER TABLE administradores ADD COLUMN perfil text NOT NULL DEFAULT 'coordenação' CHECK(perfil IN ('coordenação','recepção','portaria','superusuário'));
ALTER TABLE solicitacoes ALTER estudante_id DROP NOT NULL,
 ADD COLUMN declarado jsonb NOT NULL DEFAULT '{}',
 ADD COLUMN protocolo text UNIQUE,
 ADD COLUMN segredo text,
 ADD COLUMN mensagem text,
 ADD COLUMN etapa text NOT NULL DEFAULT 'aguardando' CHECK(etapa IN ('aguardando','recepção confirmada','saída concluída'));
UPDATE solicitacoes s SET declarado=jsonb_build_object('aluno',e.nome,'matricula',e.matricula,'responsavel',(SELECT nome FROM responsaveis WHERE id=s.responsavel_id),'origem','legado'), protocolo='LEG-'||s.id FROM estudantes e WHERE e.id=s.estudante_id;
CREATE TABLE eventos(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, solicitacao integer REFERENCES solicitacoes, autor integer REFERENCES administradores, acao text NOT NULL, nota text, quando timestamptz NOT NULL DEFAULT clock_timestamp());
CREATE INDEX eventos_solicitacao ON eventos(solicitacao,id DESC);
INSERT INTO eventos(solicitacao,acao,quando) SELECT id,'Registro legado',criado_em FROM solicitacoes;
INSERT INTO eventos(solicitacao,autor,acao,nota,quando) SELECT id,administrador_id,status,observacao_coordenacao,analisado_em FROM solicitacoes WHERE analisado_em IS NOT NULL;
CREATE TABLE sessoes(token text PRIMARY KEY, funcionario integer NOT NULL REFERENCES administradores, expira timestamptz NOT NULL);
CREATE TABLE limites(chave text PRIMARY KEY, janela bigint NOT NULL, quantidade integer NOT NULL);
