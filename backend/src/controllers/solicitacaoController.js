const pool = require('../config/database');

async function criarSolicitacao(req, res) {
    try {
        const {
            estudante_id,
            responsavel_id,
            tipo,
            justificativa,
            data_solicitada,
            horario_solicitado
        } = req.body;

        if (!estudante_id || !tipo || !justificativa) {
            return res.status(400).json({
                erro: 'Estudante, tipo e justificativa são obrigatórios'
            });
        }

        const resultado = await pool.query(
            `
            INSERT INTO solicitacoes (
                estudante_id,
                responsavel_id,
                tipo,
                justificativa,
                data_solicitada,
                horario_solicitado
            )
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            `,
            [
                estudante_id,
                responsavel_id || null,
                tipo,
                justificativa,
                data_solicitada || null,
                horario_solicitado || null
            ]
        );

        res.status(201).json({
            mensagem: 'Solicitação criada com sucesso',
            solicitacao: resultado.rows[0]
        });

    } catch (erro) {
        console.error(erro);

        res.status(500).json({
            erro: 'Erro ao criar solicitação'
        });
    }
}

async function listarSolicitacoes(req, res) {
    try {
        const resultado = await pool.query(`
            SELECT
                s.id,
                s.tipo,
                s.justificativa,
                s.data_solicitada,
                s.horario_solicitado,
                s.status,
                s.criado_em,

                e.id AS estudante_id,
                e.nome AS estudante_nome,
                e.matricula,

                r.id AS responsavel_id,
                r.nome AS responsavel_nome

            FROM solicitacoes s

            JOIN estudantes e
                ON e.id = s.estudante_id

            LEFT JOIN responsaveis r
                ON r.id = s.responsavel_id

            ORDER BY s.criado_em DESC
        `);

        res.json(resultado.rows);

    } catch (erro) {
        console.error(erro);

        res.status(500).json({
            erro: 'Erro ao listar solicitações'
        });
    }
}

async function listarPendentes(req, res) {
    try {
        const resultado = await pool.query(`
            SELECT
                s.id,
                s.tipo,
                s.justificativa,
                s.data_solicitada,
                s.horario_solicitado,
                s.status,
                s.criado_em,

                e.nome AS estudante_nome,
                e.matricula,

                r.nome AS responsavel_nome

            FROM solicitacoes s

            JOIN estudantes e
                ON e.id = s.estudante_id

            LEFT JOIN responsaveis r
                ON r.id = s.responsavel_id

            WHERE s.status = 'PENDENTE'

            ORDER BY s.criado_em ASC
        `);

        res.json(resultado.rows);

    } catch (erro) {
        console.error(erro);

        res.status(500).json({
            erro: 'Erro ao listar solicitações pendentes'
        });
    }
}

async function aprovarSolicitacao(req, res) {
    try {
        const { id } = req.params;
        const { observacao } = req.body;
        
        const administrador_id = req.administrador.id;

        const resultado = await pool.query(
            `
            UPDATE solicitacoes

            SET
                status = 'APROVADA',
                administrador_id = $1,
                observacao_coordenacao = $2,
                analisado_em = CURRENT_TIMESTAMP

            WHERE id = $3
              AND status = 'PENDENTE'

            RETURNING *
            `,
            [
                administrador_id || null,
                observacao || null,
                id
            ]
        );

        if (resultado.rows.length === 0) {
            return res.status(404).json({
                erro: 'Solicitação não encontrada ou já analisada'
            });
        }

        res.json({
            mensagem: 'Solicitação aprovada',
            solicitacao: resultado.rows[0]
        });

    } catch (erro) {
        console.error(erro);

        res.status(500).json({
            erro: 'Erro ao aprovar solicitação'
        });
    }
}

async function reprovarSolicitacao(req, res) {
    try {
        const { id } = req.params;
        const { observacao } = req.body;

        const administrador_id = req.administrador.id;

        const resultado = await pool.query(
            `
            UPDATE solicitacoes

            SET
                status = 'REPROVADA',
                administrador_id = $1,
                observacao_coordenacao = $2,
                analisado_em = CURRENT_TIMESTAMP

            WHERE id = $3
              AND status = 'PENDENTE'

            RETURNING *
            `,
            [
                administrador_id || null,
                observacao || null,
                id
            ]
        );

        if (resultado.rows.length === 0) {
            return res.status(404).json({
                erro: 'Solicitação não encontrada ou já analisada'
            });
        }

        res.json({
            mensagem: 'Solicitação reprovada',
            solicitacao: resultado.rows[0]
        });

    } catch (erro) {
        console.error(erro);

        res.status(500).json({
            erro: 'Erro ao reprovar solicitação'
        });
    }
}

module.exports = {
    criarSolicitacao,
    listarSolicitacoes,
    listarPendentes,
    aprovarSolicitacao,
    reprovarSolicitacao
};