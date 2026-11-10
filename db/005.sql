ALTER TABLE administradores ALTER COLUMN email DROP NOT NULL, ADD COLUMN usuario text UNIQUE;
DO $$
DECLARE
    conta record;
    base text;
    candidato text;
    tentativa integer;
BEGIN
    FOR conta IN SELECT id,email FROM administradores ORDER BY id LOOP
        base := left(regexp_replace(lower(split_part(conta.email,'@',1)), '[^a-z0-9._-]', '', 'g'),48);
        IF base = '' THEN base := 'funcionario'; END IF;
        candidato := base;
        tentativa := 1;
        WHILE EXISTS (SELECT 1 FROM administradores WHERE usuario=candidato) LOOP
            tentativa := tentativa + 1;
            candidato := base || '-' || tentativa;
        END LOOP;
        UPDATE administradores SET usuario=candidato WHERE id=conta.id;
    END LOOP;
END $$;
ALTER TABLE administradores ALTER COLUMN usuario SET NOT NULL,
    ADD CHECK (usuario ~ '^[a-z0-9._-]{1,64}$');
