require('dotenv').config({ path: require('path').join(__dirname, '../.env'), quiet: true });
const pool = require('../src/config/database');
async function cadastrar() {
    const nome = (process.env.STUDENT_NAME || '').trim();
    const matricula = (process.env.STUDENT_ENROLLMENT || '').trim();
    try {
        if (!nome || nome.length > 200 || !matricula || matricula.length > 80) {
            throw new Error('Informe STUDENT_NAME (até 200 caracteres) e STUDENT_ENROLLMENT (até 80).');
        }
        const resultado = await pool.query(
            `INSERT INTO estudantes (nome, matricula, curso, turma) VALUES ($1, $2, $3, $4)
             ON CONFLICT (matricula) DO NOTHING RETURNING id`,
            [nome, matricula, process.env.STUDENT_COURSE || null, process.env.STUDENT_CLASS || null]
        );
        console.log(resultado.rowCount ? 'Estudante cadastrado.' : 'Matrícula existente; dados preservados.');
    } catch (erro) {
        console.error('Cadastro não concluído:', erro.code || erro.message);
        process.exitCode = 1;
    } finally { await pool.end(); }
}
cadastrar();
