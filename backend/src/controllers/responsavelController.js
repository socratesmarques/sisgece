const pool = require('../config/database');

async function buscarPorCpf(req, res) {
    try {
        const { cpf } = req.params;

        const resultado = await pool.query(
            `
            SELECT
                r.id AS responsavel_id,
                r.nome AS responsavel_nome,
                r.cpf,
                e.id AS estudante_id,
                e.nome AS estudante_nome,
                e.matricula,
                e.curso,
                e.turma
            FROM responsaveis r
            JOIN responsavel_estudante re
                ON re.responsavel_id = r.id
            JOIN estudantes e
                ON e.id = re.estudante_id
            WHERE r.cpf = $1
            `,
            [cpf]
        );

        if (resultado.rows.length === 0) {
            return res.status(404).json({
                erro: 'Responsável não encontrado'
            });
        }

        res.json(resultado.rows);

    } catch (erro) {
        console.error(erro);

        res.status(500).json({
            erro: 'Erro ao buscar responsável'
        });
    }
}

module.exports = {
    buscarPorCpf
};