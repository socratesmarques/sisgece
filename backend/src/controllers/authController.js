const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');

const pool = require('../config/database');

async function login(req, res) {
    try {
        const { email, senha } = req.body;

        if (!email || !senha) {
            return res.status(400).json({
                erro: 'Email e senha são obrigatórios'
            });
        }

        const resultado = await pool.query(
            `
            SELECT
                id,
                nome,
                email,
                senha_hash,
                ativo
            FROM administradores
            WHERE email = $1
            `,
            [email]
        );

        if (resultado.rows.length === 0) {
            return res.status(401).json({
                erro: 'Email ou senha inválidos'
            });
        }

        const administrador = resultado.rows[0];

        if (!administrador.ativo) {
            return res.status(403).json({
                erro: 'Administrador desativado'
            });
        }

        const senhaCorreta = await bcrypt.compare(
            senha,
            administrador.senha_hash
        );

        if (!senhaCorreta) {
            return res.status(401).json({
                erro: 'Email ou senha inválidos'
            });
        }

        const token = jwt.sign(
            {
                id: administrador.id,
                email: administrador.email
            },
            process.env.JWT_SECRET,
            {
                expiresIn: '8h'
            }
        );

        res.json({
            mensagem: 'Login realizado com sucesso',

            administrador: {
                id: administrador.id,
                nome: administrador.nome,
                email: administrador.email
            },

            token
        });

    } catch (erro) {
        console.error(erro);

        res.status(500).json({
            erro: 'Erro ao realizar login'
        });
    }
}

module.exports = {
    login
};