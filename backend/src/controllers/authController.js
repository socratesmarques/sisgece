const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const pool = require('../config/database');
const { secret, production } = require('../config/runtime');
// Hash válido para igualar o custo de comparação quando a conta não existe.
const dummyHash = bcrypt.hashSync('conta-inexistente-sisgece', 12);
const cookieOptions = { httpOnly: true, secure: production, sameSite: 'strict', path: '/' };

async function login(req, res, next) {
    const { email, senha } = req.body || {};
    if (typeof email !== 'string' || email.length > 254 || !email.trim().includes('@') ||
        typeof senha !== 'string' || !senha || Buffer.byteLength(senha) > 72) {
        return res.status(400).json({ erro: 'Informe email e senha válidos' });
    }
    try {
        const resultado = await pool.query(
            'SELECT id, nome, email, senha_hash, ativo FROM administradores WHERE email = $1',
            [email.trim().toLowerCase()]
        );
        const administrador = resultado.rows[0];
        const correta = await bcrypt.compare(senha, administrador?.senha_hash || dummyHash);
        if (!correta || !administrador?.ativo) {
            return res.status(401).json({ erro: 'Email ou senha inválidos' });
        }
        const token = jwt.sign({ id: administrador.id }, secret, {
            expiresIn: '1h', algorithm: 'HS256', issuer: 'sisgece', audience: 'sisgece-admin'
        });
        res.cookie('sisgece_session', token, { ...cookieOptions, maxAge: 3600000 });
        res.json({ administrador: { id: administrador.id, nome: administrador.nome, email: administrador.email } });
    } catch (erro) { next(erro); }
}
function logout(req, res) {
    res.clearCookie('sisgece_session', cookieOptions);
    res.status(204).end();
}
module.exports = { login, logout };
