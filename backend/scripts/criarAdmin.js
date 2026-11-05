require('dotenv').config({ path: require('path').join(__dirname, '../.env') });

const bcrypt = require('bcryptjs');
const pool = require('../src/config/database');

async function criarAdmin() {
    const nome = (process.env.ADMIN_NAME || 'Coordenador').trim();
    const email = (process.env.ADMIN_EMAIL || '').trim().toLowerCase();
    const senha = process.env.ADMIN_PASSWORD || '';

    if (!nome || !email || !email.includes('@') || senha.length < 12) {
        console.error('Informe ADMIN_EMAIL válido e ADMIN_PASSWORD com pelo menos 12 caracteres.');
        process.exitCode = 1;
        await pool.end();
        return;
    }

    try {
        const senhaHash = await bcrypt.hash(senha, 12);
        const resultado = await pool.query(
            `INSERT INTO administradores (nome, email, senha_hash)
             VALUES ($1, $2, $3)
             ON CONFLICT (email) DO NOTHING
             RETURNING id, nome, email`,
            [nome, email, senhaHash]
        );

        if (resultado.rowCount === 0) {
            console.log('Administrador já cadastrado; senha existente preservada.');
        } else {
            console.log('Administrador criado:', resultado.rows[0].email);
        }
    } catch (erro) {
        console.error('Falha ao criar administrador:', erro.message);
        process.exitCode = 1;
    } finally {
        await pool.end();
    }
}

criarAdmin();
