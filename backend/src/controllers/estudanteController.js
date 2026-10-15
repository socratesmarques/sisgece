const pool = require('../config/database');

async function listarEstudantes(req, res) {
    try {
        const resultado = await pool.query(
            'SELECT * FROM estudantes ORDER BY id'
        );

        res.json(resultado.rows);
    } catch (erro) {
        console.error(erro);

        res.status(500).json({
            erro: 'Erro ao buscar estudantes'
        });
    }
}

async function buscarPorMatricula(req, res) {
    try {
        const { matricula } = req.params;

        const resultado = await pool.query(
            'SELECT * FROM estudantes WHERE matricula = $1',
            [matricula]
        );

        if (resultado.rows.length === 0) {
            return res.status(404).json({
                erro: 'Estudante não encontrado'
            });
        }

        res.json(resultado.rows[0]);

    } catch (erro) {
        console.error(erro);

        res.status(500).json({
            erro: 'Erro ao buscar estudante'
        });
    }
}

module.exports = {
    listarEstudantes,
    buscarPorMatricula
};