const express = require('express');

const {
    listarEstudantes,
    buscarPorMatricula
} = require('../controllers/estudanteController');

const router = express.Router();

router.get('/', listarEstudantes);

router.get('/:matricula', buscarPorMatricula);

module.exports = router;