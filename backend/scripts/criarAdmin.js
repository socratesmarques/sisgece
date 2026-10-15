require('dotenv').config();

const bcrypt = require('bcryptjs');
const pool = require('../src/config/database');

async function criarAdmin() {
    try {
        const nome = 'Coordenador';
        const email = 'coordenador@ifce.edu.br';
        const senha = '123456';

        const senhaHash = await bcrypt.hash(senha, 10);

        const resultado = await pool.query(
            `
            INSERT INTO administradores (
                nome,
                email,
                senha_hash
            )
            VALUES ($1, $2, $3)
            RETURNING id, nome, email
            `,
            [
                nome,
                email,
                senhaHash
            ]
        );

        console.log('Administrador criado:');
        console.log(resultado.rows[0]);

    } catch (erro) {
        console.error(erro);
    } finally {
        await pool.end();
    }
}

criarAdmin();