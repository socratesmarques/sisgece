'use strict';
const form = document.getElementById('login-form');
const erro = document.getElementById('erro');
sessionStorage.removeItem('token');
sessionStorage.removeItem('administrador');
form.addEventListener('submit', async event => {
    event.preventDefault();
    erro.textContent = '';
    const button = form.querySelector('button');
    button.disabled = true;
    try {
        const resposta = await fetch('/auth/login', {
            method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: document.getElementById('email').value,
                senha: document.getElementById('senha').value })
        });
        const dados = await resposta.json();
        if (!resposta.ok) throw new Error(dados.erro || 'Erro ao realizar login');
        window.location.href = '/pages/admin-dashboard.html';
    } catch (error) { erro.textContent = error.message || 'Não foi possível conectar ao servidor'; }
    finally { button.disabled = false; }
});
