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

        const estudante = await pool.query(
            'SELECT id FROM estudantes WHERE id = $1',
            [estudante_id]
        );

        if (estudante.rows.length === 0) {
            return res.status(404).json({
                erro: 'Estudante não encontrado'
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

module.exports = {
    criarSolicitacao
};